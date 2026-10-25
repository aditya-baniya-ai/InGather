"""Google Places (New): real places, exact pins, photos, ratings and opening hours. Optional: needs GOOGLE_MAPS_API_KEY.

Privacy: Google only sees a text query (the activity title or a venue name, plus the city) and the rounded (~1 km)
group midpoint as a location bias. Never a person's own location. Photos are fetched through our own endpoint, so the
API key never reaches a browser.
"""

import logging
import math
import threading
import time

import httpx

log = logging.getLogger(__name__)

BASE = "https://places.googleapis.com/v1"
FIELDS = ",".join(f"places.{f}" for f in (
    "id", "displayName", "formattedAddress", "location", "types", "primaryTypeDisplayName", "rating", "userRatingCount",
    "priceLevel", "currentOpeningHours.openNow", "regularOpeningHours.weekdayDescriptions", "nationalPhoneNumber",
    "websiteUri", "googleMapsUri", "editorialSummary", "photos", "businessStatus",
))
PRICE = {"PRICE_LEVEL_FREE": "Free", "PRICE_LEVEL_INEXPENSIVE": "$", "PRICE_LEVEL_MODERATE": "$$",
         "PRICE_LEVEL_EXPENSIVE": "$$$", "PRICE_LEVEL_VERY_EXPENSIVE": "$$$$"}
PRIVATE_TYPES = {"lodging", "hotel", "motel", "hostel", "bed_and_breakfast", "campground", "rv_park", "apartment_building",
                 "housing_complex", "night_club", "casino", "adult_entertainment_store", "liquor_store"}
# Google place type -> our public venue category; the first match wins.
CATEGORY = [
    (("food_court",), "food_hall"),
    (("cafe", "coffee_shop", "tea_house", "bakery", "cafeteria", "juice_shop", "dessert_shop", "ice_cream_shop"), "cafe"),
    (("library",), "library"),
    (("museum", "art_gallery", "cultural_center", "historical_landmark"), "museum"),
    (("park", "hiking_area", "national_park", "state_park", "garden", "botanical_garden", "dog_park", "playground", "beach"), "park"),
    (("convention_center", "event_venue", "conference_center", "coworking_space"), "conference_venue"),
    (("restaurant", "bar", "brewery", "pub", "wine_bar", "meal_takeaway", "pizza_restaurant", "sandwich_shop"), "restaurant"),
]
MAX_PHOTOS = 4


def km(a: tuple[float, float], b: tuple[float, float]) -> float:
    la1, lo1, la2, lo2 = map(math.radians, (*a, *b))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 12742 * math.asin(math.sqrt(min(1, h)))


def category(types: list[str]) -> str:
    for names, cat in CATEGORY:
        if any(t in names or t.endswith("_restaurant") and cat == "restaurant" for t in types):
            return cat
    return "public_venue"


def summarize(p: dict) -> dict | None:
    """A Places API result -> the details we store and show (or None for a closed or private place)."""
    loc, types = p.get("location") or {}, p.get("types") or []
    if p.get("businessStatus") not in (None, "OPERATIONAL") or PRIVATE_TYPES & set(types):
        return None
    if loc.get("latitude") is None or loc.get("longitude") is None or not p.get("id"):
        return None
    return {
        "id": p["id"],
        "name": ((p.get("displayName") or {}).get("text") or "")[:160],
        "address": (p.get("formattedAddress") or "")[:200] or None,
        "lat": round(float(loc["latitude"]), 6), "lng": round(float(loc["longitude"]), 6),
        "category": category(types),
        "type": ((p.get("primaryTypeDisplayName") or {}).get("text") or "")[:60] or None,
        "rating": p.get("rating"), "rating_count": p.get("userRatingCount"),
        "price": PRICE.get(p.get("priceLevel") or ""),
        "open_now": (p.get("currentOpeningHours") or {}).get("openNow"),
        "hours": [str(h)[:80] for h in ((p.get("regularOpeningHours") or {}).get("weekdayDescriptions") or [])][:7],
        "phone": (p.get("nationalPhoneNumber") or "")[:40] or None,
        "website": (p.get("websiteUri") or "")[:500] or None,
        "maps_url": (p.get("googleMapsUri") or "")[:500] or None,
        "summary": ((p.get("editorialSummary") or {}).get("text") or "")[:300] or None,
        "photos": [{"name": ph["name"], "author": ", ".join(a.get("displayName", "") for a in ph.get("authorAttributions") or [])[:80] or None}
                   for ph in (p.get("photos") or [])[:MAX_PHOTOS] if ph.get("name")],
    }


def search(query: str, key: str, near: tuple[float, float] | None = None, radius_km: float = 15, n: int = 10) -> list[dict]:
    """Text search, biased to a circle around `near`. Returns summarized places (closed/private ones dropped); [] on any failure."""
    if not key or not query.strip():
        return []
    body: dict = {"textQuery": query[:200], "maxResultCount": max(1, min(n, 20))}
    if near:
        body["locationBias"] = {"circle": {"center": {"latitude": near[0], "longitude": near[1]}, "radius": min(radius_km, 50) * 1000}}
    try:
        r = httpx.post(f"{BASE}/places:searchText", json=body, timeout=10,
                       headers={"X-Goog-Api-Key": key, "X-Goog-FieldMask": FIELDS})
        r.raise_for_status()
        return [s for s in (summarize(p) for p in r.json().get("places") or []) if s]
    except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
        log.warning("google places search failed: %s", type(exc).__name__)
        return []


def lookup(name: str, area: str | None, city: str, key: str, near: tuple[float, float] | None, max_km: float = 50) -> dict | None:
    """The one place a venue name + address refers to, if Google knows it near the group."""
    hits = search(f"{name}, {area or city}", key, near, n=1)
    hit = hits[0] if hits else None
    if hit and not near_enough(hit, near, max_km, city):
        return None
    return hit


def near_enough(place: dict, near: tuple[float, float] | None, max_km: float, city: str) -> bool:
    """Close to the group, or in the plan's own city (the middle can sit outside town when one person is far away)."""
    if not near or km(near, (place["lat"], place["lng"])) <= max_km:
        return True
    return bool(city) and f", {city.casefold()}," in f", {(place.get('address') or '').casefold()},"


_photo_cache: dict[tuple[str, int], tuple[float, str]] = {}
_photo_lock = threading.Lock()
PHOTO_TTL = 50 * 60  # Google photo URLs are short-lived


def photo_uri(name: str, key: str, width: int = 800) -> str | None:
    """A Places photo resource name -> a temporary, key-free googleusercontent URL (cached for under an hour)."""
    if not key or not name.startswith("places/") or "/photos/" not in name:
        return None
    with _photo_lock:
        hit = _photo_cache.get((name, width))
        if hit and hit[0] > time.monotonic():
            return hit[1]
    try:
        r = httpx.get(f"{BASE}/{name}/media", params={"maxWidthPx": width, "skipHttpRedirect": "true"},
                      headers={"X-Goog-Api-Key": key}, timeout=10)
        r.raise_for_status()
        uri = r.json().get("photoUri")
    except (httpx.HTTPError, ValueError) as exc:
        log.warning("google places photo failed: %s", type(exc).__name__)
        return None
    if not isinstance(uri, str) or not uri.startswith("https://"):
        return None
    with _photo_lock:
        if len(_photo_cache) > 2000:
            _photo_cache.clear()
        _photo_cache[(name, width)] = (time.monotonic() + PHOTO_TTL, uri)
    return uri

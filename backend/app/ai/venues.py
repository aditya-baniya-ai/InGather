"""Venue agent: finds 3 real public venues near the group's midpoint.

With a Google Maps key (fast, a few seconds): Google Places finds real nearby places with pins, photos, ratings and
hours; Muse Spark (no web search) picks the 3 that fit best and says why. Without one: Muse Spark + web_search grounding.

Privacy: the model only ever sees the city, the rounded (~1 km) group midpoint, the local meetup time, the activity
title and the interests the group shares. Never individual locations, names or plan text.

Trust: a venue is `verified` only if its source URL is one the grounded search actually returned (raw results or
url_citation annotations). If there is no key or the call fails, the fallback is generic public-place *kinds*, labeled
unverified; we never invent venue names.
"""

import json
import logging
import re
from dataclasses import dataclass, field
from typing import get_args
from urllib.parse import urlparse

from app.ai.intake import answer_text, nullable, obj, parse_json
from app.schemas import VenueCategory
from app.services import gplaces

log = logging.getLogger(__name__)

PUBLIC_CATEGORIES: tuple[str, ...] = get_args(VenueCategory)
MAX_OPTIONS = 3
BOOKING_HOSTS = ("opentable.com", "resy.com", "exploretock.com", "sevenrooms.com")
AGGREGATORS = ("yelp.", "tripadvisor.", "google.", "facebook.", "instagram.", "timeout.", "eater.")
PRIVATE_WORDS = re.compile(
    r"\b(home|house|apartment|apt|residence|residential|condo|dorm|hotel|motel|hostel|inn|airbnb|b&b|"
    r"bed and breakfast|suite|room \d+|private|members only|my place|backyard)\b",
    re.I,
)

SCHEMA = obj({
    "venues": {
        "type": "array",
        "items": obj({
            "name": {"type": "string"},
            "area": {"type": "string", "description": "Street address or neighborhood"},
            "category": {"type": "string", "enum": list(PUBLIC_CATEGORIES)},
            "why": {"type": "string", "description": "One sentence: fair travel, shared interests, quiet enough to talk, open then"},
            "description": {"type": "string", "description": "One short sentence on what the place is (cuisine, vibe, specialty)"},
            "latitude": nullable({"type": "number"}),
            "longitude": nullable({"type": "number"}),
            "image_url": nullable({"type": "string", "description": "https URL of a photo of the venue from its own site or listing, or null"}),
            "reservation_url": nullable({"type": "string"}),
            "source_url": nullable({"type": "string"}),
        }),
    }
})

INSTRUCTIONS = (
    "You are the InGather venue agent. Use web search to find exactly 3 REAL, currently operating PUBLIC venues "
    f"(categories: {', '.join(PUBLIC_CATEGORIES)}) close to the given coordinates in the given city, that suit the "
    "group's activity and shared interests and are OPEN at the given local time. Prefer places quiet enough to talk "
    "and easy for everyone to reach. Never suggest homes, hotels, private clubs or anything residential. "
    "Never mention latitude, longitude or coordinates in any text; say 'near the middle of your group' instead. "
    "Pick places that are a fair trip for EVERYONE in the group (close to the middle of all of them), not just one person. "
    "For each venue give its name, street address or neighborhood, category, a short description of what the place is, "
    "its latitude and longitude (from the listing or map you found; null if you don't know them), the https URL of a "
    "real photo of the venue from a page you found (null if none), one short sentence on why it fits "
    "(fair travel for everyone, shared interests, quiet enough to talk, open at that time), the URL of the web page "
    "you found it on as source_url, and reservation_url ONLY if you found a real booking link (OpenTable, Resy, Tock "
    "or the venue's own reservation page); otherwise null. Rank best first. If you cannot verify a venue, omit it."
)

FALLBACK = [
    ("A quiet public café near your group's midpoint", "cafe", "Cafés are public, easy to reach and quiet enough to talk."),
    ("A casual food hall or restaurant nearby", "food_hall", "Lots of choice for different tastes in a busy public space."),
    ("A public library or museum café", "library", "Calm, public and usually central. Check opening hours."),
]


MAX_KM_FROM_MIDDLE = 30  # pins farther than this from the group are dropped as unreliable


def _km(a: tuple[float, float], b: tuple[float, float]) -> float:
    import math

    la1, lo1, la2, lo2 = map(math.radians, (*a, *b))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 12742 * math.asin(math.sqrt(min(1, h)))


def _coords(v: dict, near: tuple[float, float] | None) -> tuple[float | None, float | None]:
    try:
        lat, lng = float(v.get("latitude")), float(v.get("longitude"))
    except (TypeError, ValueError):
        return None, None
    if not (-90 <= lat <= 90 and -180 <= lng <= 180) or (near and _km(near, (lat, lng)) > MAX_KM_FROM_MIDDLE):
        return None, None
    return round(lat, 6), round(lng, 6)


def _image(url) -> str | None:
    """A https photo URL, never a page, data: or javascript: link. The browser falls back to a stock photo if it fails."""
    if not _host(url) or len(url) > 500:
        return None
    return url.strip() if not re.search(r"\s", url.strip()) else None


@dataclass
class VenueRequest:
    city: str
    midpoint: tuple[float, float] | None  # already rounded to ~1 km
    local_time: str  # e.g. "Sunday 2027-01-17 18:00 (America/New_York)"
    activity: str
    interests: list[str] = field(default_factory=list)


@dataclass
class VenueResult:
    options: list[dict]
    source: str  # google|grounded|fallback


def _host(url: str | None) -> str | None:
    if not url or not isinstance(url, str):
        return None
    u = urlparse(url.strip())
    return u.hostname.lower().removeprefix("www.") if u.scheme == "https" and u.hostname else None


def norm_url(url: str) -> str:
    """Compare URLs by host + path + query, ignoring scheme, www, fragment and trailing slash."""
    u = urlparse(url.strip())
    return f"{(u.hostname or '').lower().removeprefix('www.')}{u.path.rstrip('/')}" + (f"?{u.query}" if u.query else "")


def _grounded_urls(resp) -> tuple[bool, set[str]]:
    """Whether a web search ran, and every URL it returned or the model cited."""
    searched, urls = False, set()
    for item in getattr(resp, "output", None) or []:
        if getattr(item, "type", None) == "web_search_call":
            searched = True
            for r in getattr(item, "results", None) or []:
                url = r.get("url") if isinstance(r, dict) else getattr(r, "url", None)
                if url:
                    urls.add(norm_url(url))
        if getattr(item, "type", None) == "message":
            for part in getattr(item, "content", None) or []:
                for ann in getattr(part, "annotations", None) or []:
                    url = ann.get("url") if isinstance(ann, dict) else getattr(ann, "url", None)
                    if url:
                        urls.add(norm_url(url))
    return searched, urls


def _reservation(url, source_host: str | None) -> str | None:
    """Keep only real booking links: a known booking platform, or the venue's own site (same host as the source)."""
    host = _host(url)
    if not host:
        return None
    if any(host == h or host.endswith("." + h) for h in BOOKING_HOSTS):
        return url.strip()[:500]
    if source_host and host == source_host and not any(s in host for s in AGGREGATORS):
        return url.strip()[:500]
    return None


def validate(raw: list, grounded: set[str], searched: bool, near: tuple[float, float] | None = None) -> list[dict]:
    """Public categories only, no homes/hotels, dedupe by name, max 3, verified only with a grounded source URL."""
    out, seen = [], set()
    for v in raw if isinstance(raw, list) else []:
        if not isinstance(v, dict):
            continue
        name = str(v.get("name") or "").strip()[:160]
        area = str(v.get("area") or "").strip()[:200] or None
        category = v.get("category")
        if not name or category not in PUBLIC_CATEGORIES:
            continue
        if PRIVATE_WORDS.search(name) or (area and PRIVATE_WORDS.search(area)):
            continue
        key = re.sub(r"\W+", "", name.casefold())
        if key in seen:
            continue
        seen.add(key)
        source = v.get("source_url")
        source = source.strip()[:500] if _host(source) else None
        verified = bool(searched and source and norm_url(source) in grounded)
        lat, lng = _coords(v, near) if verified else (None, None)
        out.append({
            "name": name, "area": area, "category": category,
            "why": strip_coordinates(str(v.get("why") or ""))[:400],
            "reservation_url": _reservation(v.get("reservation_url"), _host(source)) if verified else None,
            "source_url": source if verified else None,
            "verified": verified,
            "description": strip_coordinates(str(v.get("description") or ""))[:300],
            "latitude": lat, "longitude": lng,
            "image_url": _image(v.get("image_url")) if verified else None,
            "place": None,
        })
        if len(out) == MAX_OPTIONS:
            break
    return out


def fallback_options() -> list[dict]:
    return [{"name": n, "area": None, "category": c, "why": w, "reservation_url": None, "source_url": None, "verified": False,
             "description": "", "latitude": None, "longitude": None, "image_url": None, "place": None} for n, c, w in FALLBACK]


def _prompt(req: VenueRequest) -> str:
    near = f"around latitude {req.midpoint[0]:.2f}, longitude {req.midpoint[1]:.2f} (approximate group midpoint)" if req.midpoint else "central, easy to reach"
    return json.dumps({
        "city": req.city, "near": near, "meetup_local_time": req.local_time,
        "activity": req.activity, "shared_interests": req.interests[:6],
    })


PICK_SCHEMA = obj({
    "venues": {
        "type": "array",
        "items": obj({
            "id": {"type": "string", "description": "The candidate's id, exactly as given"},
            "why": {"type": "string", "description": "One sentence: fair travel, shared interests, quiet enough to talk, open then"},
            "description": {"type": "string", "description": "One short sentence on what the place is (cuisine, vibe, specialty)"},
        }),
    }
})

PICK_INSTRUCTIONS = (
    "You are the InGather venue agent. From the candidate places (real Google Maps listings), pick exactly 3 that best "
    "suit the group's activity and shared interests, are OPEN at the given local time (check their hours), are a fair "
    "trip for everyone (km_from_middle is the distance from the middle of the group), are quiet enough to talk, and "
    "are well rated. Prefer variety over three of the same kind. Rank best first. For each give its id exactly as "
    "given, one short sentence on why it fits, and one short sentence describing the place. Never mention latitude, "
    "longitude or coordinates; say 'near the middle of your group' instead."
)

# Extra Google queries by kind of activity, so there are always enough sensible candidates.
KIND_QUERIES = {
    "hike": "park with walking trail", "trail": "park with walking trail", "run": "park with running trail", "walk": "park",
    "study": "quiet cafe or library to study", "book": "bookstore cafe", "coffee": "coffee shop", "brunch": "brunch restaurant",
    "dinner": "restaurant", "lunch": "restaurant", "food": "food hall", "museum": "museum", "art": "art museum",
    "board game": "board game cafe", "game": "board game cafe", "photo": "scenic park", "picnic": "park",
}


def _extra_query(activity: str) -> str:
    a = activity.lower()
    return next((q for k, q in KIND_QUERIES.items() if k in a), "cafe")


def _quality(c: dict, near: tuple[float, float] | None) -> float:
    """Heuristic rank when Muse isn't available: well rated, much reviewed, close to the middle."""
    import math

    rating, count = c.get("rating") or 3.5, c.get("rating_count") or 0
    dist = gplaces.km(near, (c["lat"], c["lng"])) if near else 3
    return rating * math.log10(count + 10) / (1 + dist / 4) - (0.5 if c.get("open_now") is False else 0)


def _heuristic_why(c: dict, near: tuple[float, float] | None) -> str:
    bits = []
    if c.get("rating"):
        bits.append(f"rated {c['rating']:.1f} from {c.get('rating_count') or 0:,} Google reviews")
    if near:
        bits.append(f"about {gplaces.km(near, (c['lat'], c['lng'])):.1f} km from the middle of your group")
    return (", ".join(bits) or "A public place near the middle of your group").capitalize() + "."


def google_option(c: dict, why: str, description: str) -> dict:
    return {
        "name": c["name"], "area": c["address"], "category": c["category"], "why": strip_coordinates(why)[:400],
        "reservation_url": None, "source_url": c.get("maps_url"), "verified": True,
        "description": strip_coordinates(description or c.get("summary") or c.get("type") or "")[:300],
        "latitude": c["lat"], "longitude": c["lng"], "image_url": None, "place": c,
    }


class VenueAgent:
    def __init__(self, client, settings):
        self.client, self.settings = client, settings  # client: MuseClient (or a fake with .responses.create)

    @property
    def _live(self) -> bool:
        return self.client is not None and getattr(self.client, "ai_live", True)

    def suggest(self, req: VenueRequest, avoid: set[str] = frozenset()) -> VenueResult:
        key = getattr(self.settings, "google_maps_api_key", "")
        if key:
            found = self._from_google(req, key, avoid)
            if found:
                return found
        return self._from_web_search(req)

    def _from_google(self, req: VenueRequest, key: str, avoid: set[str]) -> VenueResult | None:
        """Fast path (a few seconds): Google finds real places near the middle, Muse (no web search) picks 3 and says why."""
        seen, cands = set(), []
        for query in (f"{req.activity} in {req.city}", f"{_extra_query(req.activity)} in {req.city}"):
            for c in gplaces.search(query, key, req.midpoint, radius_km=12, n=10):
                if c["id"] in seen or c["name"].casefold() in avoid or (req.midpoint and gplaces.km(req.midpoint, (c["lat"], c["lng"])) > MAX_KM_FROM_MIDDLE):
                    continue
                seen.add(c["id"])
                cands.append(c)
        if len(cands) < MAX_OPTIONS:
            return None
        cands.sort(key=lambda c: _quality(c, req.midpoint), reverse=True)
        cands = cands[:12]
        picks = self._muse_pick(req, cands) if self._live else []
        if len(picks) < MAX_OPTIONS:
            chosen = {p[0]["id"] for p in picks}
            picks += [(c, _heuristic_why(c, req.midpoint), "") for c in cands if c["id"] not in chosen][: MAX_OPTIONS - len(picks)]
        return VenueResult([google_option(c, why, desc) for c, why, desc in picks[:MAX_OPTIONS]], "google")

    def _muse_pick(self, req: VenueRequest, cands: list[dict]) -> list[tuple[dict, str, str]]:
        by_id = {c["id"]: c for c in cands}
        brief = [{
            "id": c["id"], "name": c["name"], "type": c.get("type"), "rating": c.get("rating"), "reviews": c.get("rating_count"),
            "price": c.get("price"), "hours": c.get("hours"), "summary": c.get("summary"),
            "km_from_middle": round(gplaces.km(req.midpoint, (c["lat"], c["lng"])), 1) if req.midpoint else None,
        } for c in cands]
        try:
            resp = self.client.responses.create(
                model=self.settings.meta_model, instructions=PICK_INSTRUCTIONS,
                input=[{"role": "user", "content": json.dumps({"request": json.loads(_prompt(req)), "candidates": brief})}],
                text={"format": {"type": "json_schema", "name": "venue_picks", "schema": PICK_SCHEMA, "strict": True}},
            )
            text = answer_text(resp)
            raw = parse_json(text).get("venues", []) if text else []
        except Exception as exc:  # fall back to the heuristic ranking
            log.warning("venue pick failed: %s", type(exc).__name__)
            return []
        out, used = [], set()
        for v in raw if isinstance(raw, list) else []:
            c = by_id.get(v.get("id")) if isinstance(v, dict) else None
            if c and c["id"] not in used:
                used.add(c["id"])
                out.append((c, str(v.get("why") or ""), str(v.get("description") or "")))
        return out[:MAX_OPTIONS]

    def _from_web_search(self, req: VenueRequest) -> VenueResult:
        if not self._live:
            return VenueResult(fallback_options(), "fallback")
        try:
            resp = self.client.responses.create(
                model=self.settings.meta_model,
                instructions=INSTRUCTIONS,
                input=[{"role": "user", "content": _prompt(req)}],
                tools=[{"type": "web_search", "search_context_size": "medium",
                        "user_location": {"type": "approximate", "city": req.city[:80]}}],
                include=["web_search_call.results"],
                text={"format": {"type": "json_schema", "name": "venue_options", "schema": SCHEMA, "strict": True}},
            )
            searched, grounded = _grounded_urls(resp)
            text = answer_text(resp)
            options = validate(parse_json(text).get("venues", []) if text else [], grounded, searched, req.midpoint)
        except Exception as exc:  # network, schema, parse: fall back honestly
            log.warning("venue agent failed: %s", type(exc).__name__)
            return VenueResult(fallback_options(), "fallback")
        if not options:
            return VenueResult(fallback_options(), "fallback")
        if len(options) < MAX_OPTIONS:  # pad with generic kinds, never invented names
            names = {o["category"] for o in options}
            options += [f for f in fallback_options() if f["category"] not in names][: MAX_OPTIONS - len(options)]
        return VenueResult(options, "grounded" if any(o["verified"] for o in options) else "fallback")


_COORDS = re.compile(r"(?:the\s+)?\(?-?\d{1,3}\.\d+°?,\s*-?\d{1,3}\.\d+°?\)?(?:\s+midpoint)?", re.I)


def strip_coordinates(text: str) -> str:
    """Users never see raw coordinates, even the rounded group midpoint."""
    return re.sub(r"\s{2,}", " ", _COORDS.sub("the middle of your group", text)).strip()

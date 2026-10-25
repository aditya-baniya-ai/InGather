"""Public venue lookup. Only the explicitly supplied public event location leaves the server.

OSM results are cached for 30 minutes; geocoding is serialized at <= 1 request/second.
Distances are straight-line estimates, not walking routes or opening-hours guarantees.
"""
import math
import threading
import time
from functools import lru_cache

import httpx

_lock = threading.Lock()
_last_request = 0.0


class ProviderUnavailable(Exception):
    pass


def distance_m(a: tuple[float, float], b: tuple[float, float]) -> int:
    lat1, lat2 = math.radians(a[0]), math.radians(b[0])
    dlat, dlon = lat2 - lat1, math.radians(b[1] - a[1])
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return round(6371000 * 2 * math.asin(math.sqrt(min(1, h))))


def nearby(location: str | None, city: str, enabled: bool = True) -> dict:
    if not location or not location.strip():
        return {"status": "missing_location", "places": [], "message": "Add the conference venue or a public address to find nearby places."}
    if not enabled:
        return {"status": "unavailable", "places": [], "message": "Place lookup is disabled on this server."}
    # Never accept URL-controlled destinations: providers are fixed below.
    try:
        return _lookup(location.strip()[:200], city.strip()[:80], int(time.time() // 1800))
    except ProviderUnavailable:
        # Failed requests must not be cached: the explicit retry should contact the provider again.
        return {"status": "unavailable", "places": [], "message": "Place lookup is temporarily unavailable. You can still choose a public venue manually."}


@lru_cache(maxsize=128)
def _lookup(location: str, city: str, bucket: int) -> dict:
    global _last_request
    headers = {"User-Agent": "InGather/0.1 (public-event venue lookup)", "Accept": "application/json"}
    try:
        with httpx.Client(timeout=15, headers=headers) as client:
            with _lock:
                wait = 1.1 - (time.monotonic() - _last_request)
                if wait > 0:
                    time.sleep(wait)
                try:
                    response = client.get("https://nominatim.openstreetmap.org/search", params={
                        "q": f"{location}, {city}", "format": "jsonv2", "limit": 1,
                    })
                    response.raise_for_status()
                finally:
                    _last_request = time.monotonic()
            hits = response.json()
            if not hits or hits[0].get("type") in {"city", "administrative", "state", "country", "suburb"}:
                return {"status": "not_found", "places": [], "message": "Couldn't locate that public venue. Try its street address."}
            origin = (float(hits[0]["lat"]), float(hits[0]["lon"]))
            if not (-90 <= origin[0] <= 90 and -180 <= origin[1] <= 180):
                raise ValueError("invalid coordinates")
            query = f'''[out:json][timeout:12];(nwr(around:1500,{origin[0]},{origin[1]})[amenity~"^(cafe|restaurant|food_court|library)$"][name];);out center tags;'''
            try:
                response = client.post("https://overpass-api.de/api/interpreter", data={"data": query})
                response.raise_for_status()
            except httpx.HTTPError:
                # One bounded fallback, rather than repeated requests to an overloaded instance.
                response = client.post("https://overpass.private.coffee/api/interpreter", data={"data": query}, timeout=8)
                response.raise_for_status()
            places = []
            seen = set()
            for item in response.json().get("elements", []):
                tags = item.get("tags", {})
                center = item.get("center", item)
                if not tags.get("name") or tags.get("access") in {"private", "no", "customers_only"}:
                    continue
                if "lat" not in center or "lon" not in center:
                    continue
                point = (float(center["lat"]), float(center["lon"]))
                if not (-90 <= point[0] <= 90 and -180 <= point[1] <= 180):
                    continue
                distance = distance_m(origin, point)
                key = (tags["name"].casefold(), round(point[0], 4), round(point[1], 4))
                if distance > 1500 or key in seen:
                    continue
                category = {"restaurant": "restaurant", "cafe": "cafe", "library": "library", "food_court": "food_hall"}.get(tags.get("amenity"))
                if not category:
                    continue
                seen.add(key)
                address = " ".join(filter(None, [tags.get("addr:housenumber"), tags.get("addr:street")]))
                places.append({"id": f"{item['type']}/{item['id']}", "name": tags["name"][:160],
                    "category": category, "latitude": point[0], "longitude": point[1],
                    "address": address[:200], "distance_m": distance, "source": "OpenStreetMap"})
            places.sort(key=lambda p: (p["distance_m"], p["id"]))
            return {"status": "ok" if places else "no_results", "places": places[:12],
                "message": "Places within 1.5 km. Distances are straight-line estimates; check hours and access." if places else "No mapped public cafés or restaurants were found within 1.5 km. Try another public address.",
                "origin": {"latitude": origin[0], "longitude": origin[1], "label": hits[0].get("display_name", location)[:300]}}
    except (httpx.HTTPError, ValueError, TypeError, KeyError, IndexError) as exc:
        raise ProviderUnavailable() from exc

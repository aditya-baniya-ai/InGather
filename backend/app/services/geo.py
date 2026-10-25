"""Coarse, privacy-preserving locations. Everything here is rounded to 0.01 degrees (~1 km).

Individual home areas never leave the server except as the free-text query to the geocoder; only the
rounded group midpoint and the city are ever given to a model.
"""
import time

import httpx

from app.services import places

PRECISION = 2  # 0.01 deg latitude ~ 1.1 km


def coarse(lat: float, lng: float) -> tuple[float, float]:
    if not (-90 <= lat <= 90 and -180 <= lng <= 180):
        raise ValueError("invalid coordinates")
    return round(lat, PRECISION), round(lng, PRECISION)


def midpoint(points: list[tuple[float, float]]) -> tuple[float, float] | None:
    """Rounded centroid of already-coarse points (fine at city scale)."""
    pts = [p for p in points if p and p[0] is not None and p[1] is not None]
    if not pts:
        return None
    return coarse(sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))


def geocode_area(area: str, enabled: bool = True) -> tuple[float, float] | None:
    """City / neighborhood / ZIP -> coarse lat/lng, or None. Shares the OSM rate limit with venue lookup."""
    area = (area or "").strip()[:80]
    if not area or not enabled:
        return None
    try:
        with places._lock:
            wait = 1.1 - (time.monotonic() - places._last_request)
            if wait > 0:
                time.sleep(wait)
            try:
                r = httpx.get("https://nominatim.openstreetmap.org/search", params={"q": area, "format": "jsonv2", "limit": 1},
                              headers={"User-Agent": "InGather/0.1 (coarse home-area geocode)"}, timeout=10)
                r.raise_for_status()
            finally:
                places._last_request = time.monotonic()
        hits = r.json()
        return coarse(float(hits[0]["lat"]), float(hits[0]["lon"])) if hits else None
    except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError):
        return None


def geocode_place(query: str, enabled: bool = True) -> tuple[float, float] | None:
    """A public venue's street address -> exact map pin (venues are public places, so no rounding). None if unknown."""
    query = (query or "").strip()[:200]
    if not query or not enabled:
        return None
    try:
        with places._lock:
            wait = 1.1 - (time.monotonic() - places._last_request)
            if wait > 0:
                time.sleep(wait)
            try:
                r = httpx.get("https://nominatim.openstreetmap.org/search", params={"q": query, "format": "jsonv2", "limit": 1},
                              headers={"User-Agent": "InGather/0.1 (venue map pin)"}, timeout=10)
                r.raise_for_status()
            finally:
                places._last_request = time.monotonic()
        hits = r.json()
        return (round(float(hits[0]["lat"]), 6), round(float(hits[0]["lon"]), 6)) if hits else None
    except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError):
        return None

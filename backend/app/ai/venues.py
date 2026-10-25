"""Venue agent: Muse Spark + web_search grounding finds 3 real public venues near the group's midpoint.

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
    source: str  # grounded|fallback


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
        })
        if len(out) == MAX_OPTIONS:
            break
    return out


def fallback_options() -> list[dict]:
    return [{"name": n, "area": None, "category": c, "why": w, "reservation_url": None, "source_url": None, "verified": False,
             "description": "", "latitude": None, "longitude": None, "image_url": None} for n, c, w in FALLBACK]


def _prompt(req: VenueRequest) -> str:
    near = f"around latitude {req.midpoint[0]:.2f}, longitude {req.midpoint[1]:.2f} (approximate group midpoint)" if req.midpoint else "central, easy to reach"
    return json.dumps({
        "city": req.city, "near": near, "meetup_local_time": req.local_time,
        "activity": req.activity, "shared_interests": req.interests[:6],
    })


class VenueAgent:
    def __init__(self, client, settings):
        self.client, self.settings = client, settings  # client: MuseClient (or a fake with .responses.create)

    def suggest(self, req: VenueRequest) -> VenueResult:
        if self.client is None or not getattr(self.client, "ai_live", True):
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

"""Austin venue catalog for the demo, built once with Muse Spark + web search (the grounded VenueAgent).

    python -m app.demo.enrich --venues        # needs MODEL_API_KEY; ~36 grounded searches, run once

Each Austin area x kind of meetup gets up to 3 real public places, and only venues the search actually backed with a
source page are kept. Seeded groups and Austin plans without a mapped place pick the nearest fitting venue from this
catalog, so matching never needs a model call. Without a catalog, groups fall back to generic public suggestions.
"""

import json
import logging
import math
from pathlib import Path

from app.config import Settings

log = logging.getLogger(__name__)

PACKAGE_FILE = Path(__file__).parent / "data" / "austin_venues.json"

# Areas the catalog covers (coarse centers) and the kinds of meetups to search for in each.
AREAS = [
    ("UT Austin / West Campus", 30.29, -97.74), ("Downtown", 30.27, -97.74), ("East Austin", 30.26, -97.72),
    ("South Congress", 30.25, -97.75), ("Zilker / Barton Springs", 30.26, -97.77), ("Hyde Park / North Loop", 30.31, -97.73),
    ("Mueller", 30.30, -97.70), ("The Domain / North Burnet", 30.40, -97.72), ("Riverside / Travis Heights", 30.24, -97.74),
    ("Crestview / Allandale", 30.34, -97.74), ("Clarksville / Old West Austin", 30.28, -97.76), ("Windsor Park / Cherrywood", 30.30, -97.70),
]
KINDS = {
    "coffee": ("coffee and conversation", ["coffee"]),
    "food": ("casual group meal or food hall", ["food", "tacos"]),
    "quiet": ("quiet place to study, read or play board games", ["books", "board games", "studying"]),
}


def catalog_path(settings: Settings) -> Path:
    return Path(settings.media_dir) / "austin_venues.json"


def load_catalog(settings: Settings) -> list[dict]:
    """Venues from the media volume (built on this machine) or the copy shipped in the repo, else []."""
    for path in (catalog_path(settings), PACKAGE_FILE):
        try:
            data = json.loads(path.read_text())
            venues = [v for v in data.get("venues", []) if v.get("verified") and v.get("name")]
            if venues:
                return venues
        except (OSError, ValueError):
            continue
    return []


def nearest(catalog: list[dict], categories: tuple[str, ...], near: tuple[float, float] | None, avoid: set[str] = frozenset()) -> dict | None:
    """Best fitting venue: first category that has one, then closest area to `near` (coarse), skipping `avoid`."""
    for category in categories:
        options = [v for v in catalog if v["category"] == category and v["name"] not in avoid]
        if options:
            if near is None:
                return options[0]
            return min(options, key=lambda v: math.dist(near, (v["area_lat"], v["area_lng"])))
    return None


def build_catalog(settings: Settings, client=None) -> dict:
    """Run the grounded venue agent for every area x kind and save the verified results."""
    from app.ai.muse import MuseClient
    from app.ai.venues import VenueAgent, VenueRequest

    client = client or MuseClient(settings)
    if not getattr(client, "ai_live", True):
        raise SystemExit("MODEL_API_KEY is not set: the venue catalog needs Muse Spark with web search.")
    agent, venues, seen = VenueAgent(client, settings), [], set()
    for area, lat, lng in AREAS:
        for kind, (activity, interests) in KINDS.items():
            result = agent.suggest(VenueRequest("Austin", (lat, lng), "Saturday 11:00 (America/Chicago)", activity, interests))
            kept = [o for o in result.options if o["verified"] and o["name"].casefold() not in seen]
            for o in kept:
                seen.add(o["name"].casefold())
                venues.append({**o, "area_name": area, "area_lat": lat, "area_lng": lng, "kind": kind})
            log.info("%s / %s: %d verified venues", area, kind, len(kept))
            print(f"  {area} / {kind}: {', '.join(o['name'] for o in kept) or 'none verified'}", flush=True)
    data = {"city": "Austin", "source": "Muse Spark web search (grounded, verified sources only)", "venues": venues}
    path = catalog_path(settings)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=1))
    return data

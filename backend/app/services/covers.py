"""Group cover photos made by the scene agent (app/ai/scenes.py), stored under /media.

Groups with the same title, city and part of day share one image, so a demo with many similar groups costs only a few
Muse Image calls. Generation runs in the background; the UI shows the category photo until the cover lands.
"""

import hashlib
import logging
import re
import threading
from pathlib import Path
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.models import MemberStatus, Plan, Proposal

log = logging.getLogger(__name__)

_inflight: set[str] = set()
_lock = threading.Lock()
EXT = {"png": "png", "jpeg": "jpg", "jpg": "jpg", "webp": "webp"}


def part_of_day(proposal: Proposal, plan: Plan) -> str:
    from app.services.clock import as_utc
    from app.services.feed import part_of_day as label

    return label(as_utc(proposal.start_at).astimezone(ZoneInfo(plan.timezone))) if proposal.start_at else "afternoon"


def cover_key(title: str, city: str, when: str) -> str:
    norm = re.sub(r"\W+", " ", f"{title}|{city}|{when}".casefold()).strip()
    return hashlib.sha1(norm.encode()).hexdigest()[:16]


def _existing(media: Path, key: str) -> str | None:
    hit = next(iter(sorted(media.glob(f"scene-{key}.*"))), None)
    return f"/media/{hit.name}" if hit else None


def make_cover(db: Session, settings: Settings, proposal: Proposal, client) -> str | None:
    """Give one group its cover: reuse a matching image, else brief + render a new one. Returns the URL (or None)."""
    if proposal.cover_image_url:
        return proposal.cover_image_url
    from app.ai.scenes import SceneAgent

    plan = db.get(Plan, proposal.plan_id)
    when = part_of_day(proposal, plan)
    key = cover_key(proposal.activity_title, plan.city, when)
    media = Path(settings.media_dir)
    media.mkdir(parents=True, exist_ok=True)
    url = _existing(media, key)
    if url is None:
        with _lock:
            if key in _inflight:
                return None  # another worker is drawing this one; the next feed load picks it up
            _inflight.add(key)
        try:
            members = [m.user for m in proposal.members if m.status == MemberStatus.accepted]
            tags = sorted({i for u in members for i in (u.interests or [])})[:4]
            agent = SceneAgent(client, settings)
            image = agent.render(agent.brief(proposal.activity_title, plan.activity_type, plan.city, when, tags))
            name = f"scene-{key}.{EXT.get(image.fmt, 'webp')}"
            (media / name).write_bytes(image.data)
            url = f"/media/{name}"
        finally:
            with _lock:
                _inflight.discard(key)
    proposal.cover_image_url = url
    db.commit()
    return url


def cover_in_background(proposal_ids: list[UUID]) -> None:
    """Best effort, one after another (BackgroundTasks after a feed or groups response)."""
    from app.ai.muse import MuseClient
    from app.db import SessionLocal

    settings = get_settings()
    if not settings.ai_live:
        return
    client = MuseClient(settings)
    for pid in proposal_ids:
        try:
            with SessionLocal() as db:
                proposal = db.get(Proposal, pid)
                if proposal is not None:
                    make_cover(db, settings, proposal, client)
        except Exception as exc:
            log.warning("group cover failed: %s", type(exc).__name__)


def missing(items, limit: int = 4) -> list[UUID]:
    """The first few listed groups that still have no cover."""
    return [i.proposal_id for i in items if not getattr(i, "cover_url", None)][:limit]

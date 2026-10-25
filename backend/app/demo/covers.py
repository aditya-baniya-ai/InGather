"""Draw scene-agent covers for the seeded open groups ahead of a demo (one Muse Spark + Muse Image call per new scene).

    docker compose exec app python -m app.demo.covers            # up to 40 groups
    docker compose exec app python -m app.demo.covers --limit 200
Groups that share a title, city and part of day reuse one image, so most groups cost nothing extra.
"""

import sys

from sqlalchemy import select

from app.ai.muse import MuseClient
from app.config import get_settings
from app.db import SessionLocal
from app.models import Proposal
from app.services.covers import make_cover


def main(limit: int = 40) -> None:
    settings = get_settings()
    client = MuseClient(settings)
    if not client.ai_live:
        raise SystemExit("MODEL_API_KEY is not set: the scene agent needs Muse Spark and Muse Image.")
    with SessionLocal() as db:
        todo = list(db.scalars(select(Proposal).where(Proposal.open_to_requests.is_(True), Proposal.cover_image_url.is_(None))
                               .order_by(Proposal.start_at).limit(limit)))
        print(f"{len(todo)} groups without a cover", flush=True)
        for i, p in enumerate(todo, 1):
            try:
                url = make_cover(db, settings, p, client)
                print(f"  {i}/{len(todo)} {p.activity_title}: {url}", flush=True)
            except Exception as exc:
                db.rollback()
                print(f"  {i}/{len(todo)} {p.activity_title}: failed ({type(exc).__name__})", flush=True)


if __name__ == "__main__":
    main(int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else 40)

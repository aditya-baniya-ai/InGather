"""One-time Muse Spark enrichment of the Austin demo (needs MODEL_API_KEY; matching itself never calls Muse).

    python -m app.demo.enrich --venues    # grounded web search for real Austin venues; seeded groups pick from them
    python -m app.demo.enrich --bios      # rewrite the 1,000 generated "about" texts in natural, first-person voice
    python -m app.demo.enrich --all

In Docker: `docker compose exec app python -m app.demo.enrich --all`. Results are stored (venue catalog in the media
volume, bios in the database), so it never needs to run again.
"""

import argparse
import json
import logging
import re
import sys

from sqlalchemy import select

from app.ai.intake import answer_text, obj, parse_json
from app.ai.muse import MuseClient
from app.config import get_settings
from app.db import SessionLocal
from app.demo.austin import DOMAIN, VENUE_KINDS
from app.demo.venues import build_catalog, load_catalog, nearest
from app.models import Plan, Proposal, User

log = logging.getLogger("ingather.demo")
BATCH = 20
BIO_SCHEMA = obj({"bios": {"type": "array", "items": obj({"id": {"type": "string"}, "bio": {"type": "string"}})}})
BIO_INSTRUCTIONS = (
    "You rewrite short profile 'about' texts for FICTIONAL demo people in Austin, Texas, so they sound like real people "
    "wrote them: first person, warm, specific, a little personality, varied sentence shapes, no clichés, max 240 "
    "characters. Keep every fact: job, neighborhood, interests, when they're free this week and what they're looking "
    "for. Don't add new facts, real business names, ages, contact details, links, hashtags or emoji. Reply only with "
    "the JSON answer, one entry per input id."
)
_BAD = re.compile(r"(https?://|www\.|@|#|\d{3}[-. ]\d{3,4})")


def polish_bios(db, settings, client) -> int:
    users = list(db.scalars(select(User).where(User.email.like(f"%{DOMAIN}")).order_by(User.email)))
    done = 0
    for i in range(0, len(users), BATCH):
        batch = {str(u.id): u for u in users[i:i + BATCH]}
        prompt = json.dumps([{"id": k, "about": u.bio, "interests": u.interests} for k, u in batch.items()])
        try:
            resp = client.responses.create(
                model=settings.meta_model, instructions=BIO_INSTRUCTIONS, reasoning={"effort": "minimal"},
                input=[{"role": "user", "content": prompt}],
                text={"format": {"type": "json_schema", "name": "bios", "schema": BIO_SCHEMA, "strict": True}},
            )
            rows = parse_json(answer_text(resp) or "{}").get("bios", [])
        except Exception as exc:  # keep the generated bios for this batch
            log.warning("bio batch %d failed: %s", i // BATCH, type(exc).__name__)
            continue
        for row in rows:
            user, bio = batch.get(str(row.get("id"))), " ".join(str(row.get("bio") or "").split())
            if user and 40 <= len(bio) <= 280 and not _BAD.search(bio):
                user.bio = bio
                done += 1
        db.commit()
        print(f"  bios {min(i + BATCH, len(users))}/{len(users)}", flush=True)
    return done


def assign_venues(db, settings) -> int:
    """Give every seeded group the nearest fitting venue from the (new) catalog."""
    catalog = load_catalog(settings)
    if not catalog:
        return 0
    n = 0
    q = select(Proposal).join(User, Proposal.owner_id == User.id).where(User.email.like(f"%{DOMAIN}"), Proposal.open_to_requests.is_(True))
    for p in db.scalars(q):
        host, plan = db.get(User, p.owner_id), db.get(Plan, p.plan_id)
        near = (host.home_lat, host.home_lng) if host.home_lat is not None else None
        venue = nearest(catalog, VENUE_KINDS.get(plan.activity_type, ("cafe",)), near)
        if venue:
            p.venue_label, p.venue_category = venue["name"][:160], venue["category"]
            p.venue_details = {"name": venue["name"], "category": venue["category"], "address": venue.get("area") or venue["area_name"],
                               "source": "Muse Spark web search", "source_url": venue.get("source_url")}
            n += 1
    db.commit()
    return n


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--venues", action="store_true")
    ap.add_argument("--bios", action="store_true")
    ap.add_argument("--all", action="store_true")
    args = ap.parse_args(argv)
    settings = get_settings()
    client = MuseClient(settings)
    if not client.ai_live:
        print("MODEL_API_KEY is not set, so there's nothing to enrich. Add it to .env and try again.")
        return 1
    if not (args.venues or args.bios or args.all):
        ap.print_help()
        return 1
    with SessionLocal() as db:
        if args.venues or args.all:
            print("Finding real Austin venues with Muse Spark web search...")
            data = build_catalog(settings, client)
            print(f"  {len(data['venues'])} verified venues; updated {assign_venues(db, settings)} groups")
        if args.bios or args.all:
            print("Rewriting the demo bios with Muse Spark...")
            print(f"  rewrote {polish_bios(db, settings, client)} bios")
    return 0


if __name__ == "__main__":
    sys.exit(main())

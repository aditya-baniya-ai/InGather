"""Home feed, join requests and the demo people's avatars (docs/api-contract.md, "Home feed")."""

import re
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, Response
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db import get_db
from app.models import User
from app.schemas import ActivityType, FeedItemOut, JoinDraftOut, JoinIn, JoinRequestOut, OpenIn
from app.security import current_user, not_found
from app.services.feed import Feed, auto_respond
from app.services.policy import Policy
from app.services.ratelimit import limiter

router = APIRouter(prefix="/api", tags=["feed"])
_DEMO_KEY = re.compile(r"^atx-\d{4}$")


def feed(db: Session = Depends(get_db), s: Settings = Depends(get_settings)) -> Feed:
    return Feed(db, s)


@router.get("/feed", response_model=list[FeedItemOut])
def home_feed(sort: Literal["match", "soonest"] = "match", activity: ActivityType | None = None,
              user: User = Depends(current_user), svc: Feed = Depends(feed)):
    return svc.items(user, sort=sort, activity=activity)


def _item(svc: Feed, user: User, proposal_id: UUID) -> FeedItemOut:
    item = next((i for i in svc.items(user, limit=500) if i.proposal_id == proposal_id), None)
    if item is None:
        raise not_found()
    return item


@router.post("/proposals/{proposal_id}/join", response_model=FeedItemOut, status_code=201)
def ask_to_join(proposal_id: UUID, body: JoinIn, background: BackgroundTasks, user: User = Depends(current_user),
                svc: Feed = Depends(feed), s: Settings = Depends(get_settings)):
    limiter.hit("join_request", user.id)
    req = svc.request(user, proposal_id, body.message)
    if s.demo_mode:
        background.add_task(auto_respond, req.id)  # only fictional hosts answer on their own
    return _item(svc, user, proposal_id)


@router.delete("/proposals/{proposal_id}/join", status_code=204)
def withdraw(proposal_id: UUID, user: User = Depends(current_user), svc: Feed = Depends(feed)):
    svc.withdraw(user, proposal_id)
    return Response(status_code=204)


@router.post("/proposals/{proposal_id}/join/draft", response_model=JoinDraftOut)
def draft_intro(proposal_id: UUID, user: User = Depends(current_user), svc: Feed = Depends(feed)):
    """Muse Spark drafts a short intro from the requester's own profile. Nothing is sent until they press send."""
    limiter.hit("join_draft", user.id)
    message, live = svc.draft(user, proposal_id)
    return JoinDraftOut(message=message, mode="live" if live else "template")


@router.get("/proposals/{proposal_id}/join-requests", response_model=list[JoinRequestOut])
def join_requests(proposal_id: UUID, user: User = Depends(current_user), svc: Feed = Depends(feed), db: Session = Depends(get_db),
                  s: Settings = Depends(get_settings)):
    proposal, _ = Policy(db, s).visible_proposal(user, proposal_id, "owner")
    return svc.for_owner(proposal)


@router.post("/proposals/{proposal_id}/join-requests/{request_id}/{decision}", response_model=list[JoinRequestOut])
def decide(proposal_id: UUID, request_id: UUID, decision: str, user: User = Depends(current_user), svc: Feed = Depends(feed),
           db: Session = Depends(get_db), s: Settings = Depends(get_settings)):
    if decision not in ("accept", "decline"):
        raise not_found()
    proposal, _ = Policy(db, s).visible_proposal(user, proposal_id, "owner")
    svc.decide(proposal, request_id, decision == "accept")
    return svc.for_owner(proposal)


@router.post("/proposals/{proposal_id}/open", status_code=204)
def set_open(proposal_id: UUID, body: OpenIn, user: User = Depends(current_user), db: Session = Depends(get_db),
             s: Settings = Depends(get_settings)):
    """Owner: let people ask to join from their Home feed while there are open spots (or stop)."""
    proposal, _ = Policy(db, s).visible_proposal(user, proposal_id, "owner")
    proposal.open_to_requests = body.open
    db.commit()
    return Response(status_code=204)


@router.get("/demo/avatars/{key}.svg", include_in_schema=False)
def demo_avatar(key: str):
    """Illustrated portraits for the fictional Austin demo people (public, like any profile picture)."""
    if not _DEMO_KEY.match(key):
        raise not_found()
    from app.demo.avatars import avatar_svg

    return Response(avatar_svg(key), media_type="image/svg+xml", headers={"Cache-Control": "public, max-age=86400"})

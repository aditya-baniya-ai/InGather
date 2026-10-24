"""Deterministic hard filters + transparent ranking. Other people's windows/goal_text never leave this module;
callers only receive previews and group-level availability."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import DiscoveryMode, Plan, PlanStatus, Proposal, ProposalMember, User
from app.services.clock import Interval, intersect, merge, minutes
from app.services.policy import Policy

MIN_GROUP_MINUTES = 60


@dataclass
class CandidatePreview:
    user_id: str
    display_name: str
    activity_type: str
    shared_interests: list[str]
    preview_text: str
    intent: str
    score: int = 0  # transparent baseline from rank()


@dataclass
class GroupAvailability:
    possible: bool
    windows: list[tuple[datetime, datetime]]
    reason: str


class Matching:
    def __init__(self, db: Session, settings: Settings):
        self.db, self.settings = db, settings
        self.policy = Policy(db, settings)

    def find_candidates(self, plan: Plan, excluded: set[UUID], limit: int) -> list[CandidatePreview]:
        skip = {UUID(str(x)) for x in excluded} | self.policy.blocked_with(plan.owner_id) | self._already_on(plan)
        owner_windows = self._windows([plan])
        cands = []
        for user, plans in self._peers(plan).items():
            if user.id in skip or not intersect(owner_windows, self._windows(plans)):
                continue
            cands.append(self._preview(plan, user, plans[0]))
        return self.rank(plan, cands)[: max(limit, 0)]

    def group_availability(self, plan: Plan, user_ids: list[UUID]) -> GroupAvailability:
        ids = {UUID(str(x)) for x in user_ids}
        peers = {u.id: plans for u, plans in self._peers(plan, ids).items()}
        common = self._windows([plan])
        for uid in ids:
            common = intersect(common, self._windows(peers.get(uid, [])))
        possible = any(minutes([w]) >= MIN_GROUP_MINUTES for w in common)
        size = len(ids) + 1
        reason = (
            f"All {size} people share {minutes(common)} free minutes across {len(common)} window(s)."
            if possible
            else f"No common window of at least {MIN_GROUP_MINUTES} minutes for this group of {size}."
        )
        return GroupAvailability(possible, common, reason)

    def rank(self, plan: Plan, cands: list[CandidatePreview]) -> list[CandidatePreview]:
        """score = 3/shared interest + 2 same activity + 1 same intent + 1/hour of overlap (max 4)."""
        peers = {str(u.id): plans for u, plans in self._peers(plan, {UUID(c.user_id) for c in cands}).items()}
        owner_windows = self._windows([plan])
        for c in cands:
            overlap = minutes(intersect(owner_windows, self._windows(peers.get(c.user_id, []))))
            c.score = (
                3 * len(c.shared_interests)
                + 2 * (c.activity_type == plan.activity_type)
                + (c.intent == plan.intent)
                + min(overlap // 60, 4)
            )
        return sorted(cands, key=lambda c: (-c.score, c.display_name.lower(), c.user_id))

    def _peers(self, plan: Plan, only: set[UUID] | None = None) -> dict[User, list[Plan]]:
        """Other users' discoverable plans in the same city with overlapping dates."""
        q = (
            select(User, Plan)
            .join(Plan, Plan.owner_id == User.id)
            .where(
                User.id != plan.owner_id,
                User.is_adult.is_(True),
                User.discovery_paused.is_(False),
                Plan.status == PlanStatus.active,
                Plan.discovery_mode == DiscoveryMode.mutual_discovery,
                func.lower(Plan.city) == plan.city.strip().lower(),
                Plan.start_date <= plan.end_date,
                Plan.end_date >= plan.start_date,
            )
            .order_by(Plan.created_at)
        )
        if only is not None:
            q = q.where(User.id.in_(only))
        blocked = self.policy.blocked_with(plan.owner_id)
        out: dict[User, list[Plan]] = {}
        for user, peer in self.db.execute(q):
            if user.id not in blocked and self.policy.can_discover(user):
                out.setdefault(user, []).append(peer)
        return out

    def _already_on(self, plan: Plan) -> set[UUID]:
        """Anyone already on one of this plan's proposals (suggested, invited, passed, declined...)."""
        q = select(ProposalMember.user_id).join(Proposal).where(Proposal.plan_id == plan.id)
        return set(self.db.scalars(q))

    @staticmethod
    def _windows(plans: list[Plan]) -> list[Interval]:
        return merge([(w.starts_at, w.ends_at) for p in plans for w in p.windows])

    @staticmethod
    def _preview(plan: Plan, user: User, peer: Plan) -> CandidatePreview:
        mine = {i.lower(): i for i in plan.interests}
        theirs = {i.lower() for i in [*peer.interests, *user.interests]}
        return CandidatePreview(
            user_id=str(user.id),
            display_name=user.display_name,
            activity_type=peer.activity_type,
            shared_interests=[mine[k] for k in mine if k in theirs],
            preview_text=peer.preview_text or "",
            intent=peer.intent,
        )

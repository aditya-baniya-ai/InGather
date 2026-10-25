"""Deterministic hard filters + the InGather matcher (an ML model, app/ml) for ranking. Other people's windows,
goal text and event locations never leave this module; callers only receive previews, scores and group-level
availability."""

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import Settings
from app.ml.features import Context, pair_features
from app.ml.interests import Profile, normalize
from app.ml.model import Matcher, load_matcher
from app.models import DiscoveryMode, Plan, PlanStatus, Proposal, ProposalMember, User
from app.services.clock import Interval, intersect, merge, minutes
from app.services.policy import Policy

MIN_GROUP_MINUTES = 60
RELATED = 0.75  # embedding similarity above which two different interests are called "close" in a reason


@dataclass
class CandidatePreview:
    user_id: str
    display_name: str
    activity_type: str
    shared_interests: list[str]
    preview_text: str
    intent: str
    score: float = 0.0  # matcher probability that this person and the plan are a good fit (0-1)
    related: list[tuple[str, str]] = field(default_factory=list)  # (owner interest, their similar interest)


@dataclass
class GroupAvailability:
    possible: bool
    windows: list[tuple[datetime, datetime]]
    reason: str


@dataclass
class Fit:
    """Server-only scoring detail for one candidate (the engine uses it to search groups and write reasons)."""

    preview: CandidatePreview
    windows: list[Interval]  # this person's free time intersected with the owner's
    same_activity: bool
    same_event: bool

    @property
    def overlap_hours(self) -> float:
        return minutes(self.windows) / 60


class Matching:
    def __init__(self, db: Session, settings: Settings, matcher: Matcher | None = None):
        self.db, self.settings = db, settings
        self.policy = Policy(db, settings)
        self._matcher = matcher

    @property
    def matcher(self) -> Matcher:
        if self._matcher is None:
            self._matcher = load_matcher()
        return self._matcher

    # ----- hard filters -----
    def eligible(self, plan: Plan, excluded: set[UUID]) -> list[CandidatePreview]:
        """Everyone who may be suggested for this plan, in a stable order (no scoring)."""
        return [f.preview for f in self._fits(plan, excluded)]

    def find_candidates(self, plan: Plan, excluded: set[UUID], limit: int, extra_interests=()) -> list[CandidatePreview]:
        """Eligible people, best fit first according to the matcher."""
        return [f.preview for f in self.fits(plan, excluded, extra_interests)][: max(limit, 0)]

    def fits(self, plan: Plan, excluded: set[UUID], extra_interests=()) -> list[Fit]:
        fits = self._fits(plan, excluded)
        self.score(plan, fits, extra_interests)
        return sorted(fits, key=lambda f: (-f.preview.score, f.preview.display_name.lower(), f.preview.user_id))

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

    # ----- the matcher -----
    def profile(self, terms) -> Profile:
        return self.matcher.space.profile(terms)

    def score(self, plan: Plan, fits: list[Fit], extra_interests=()) -> None:
        """Set each candidate's score: the matcher's probability that they fit the owner's plan."""
        if not fits:
            return
        owner = self.profile([*plan.interests, *extra_interests])
        peers = {str(u.id): (u, plans) for u, plans in self._peers(plan, {UUID(f.preview.user_id) for f in fits}).items()}
        rows = []
        for f in fits:
            user, plans = peers[f.preview.user_id]
            theirs = self.profile([*plans[0].interests, *user.interests])
            rows.append(pair_features(owner, theirs, Context(f.same_activity, f.preview.intent == plan.intent, f.same_event, f.overlap_hours)))
            f.preview.related = self._related(owner, theirs, plan.interests, [*plans[0].interests, *user.interests])
        for f, p in zip(fits, self.matcher.predict(rows)):
            f.preview.score = round(float(p), 4)

    def cohesion(self, plan: Plan, user_ids: list[UUID]) -> dict[tuple[UUID, UUID], float]:
        """How well each pair of candidates fits each other (symmetric matcher score), for choosing the group."""
        peers = {u.id: (u, plans) for u, plans in self._peers(plan, set(user_ids)).items()}
        ids = [i for i in user_ids if i in peers]
        prof = {i: self.profile([*peers[i][1][0].interests, *peers[i][0].interests]) for i in ids}
        pairs, rows = [], []
        for n, a in enumerate(ids):
            for b in ids[n + 1:]:
                pa, pb = peers[a][1][0], peers[b][1][0]
                ctx = Context(pa.activity_type == pb.activity_type, pa.intent == pb.intent, _same_event(pa, pb),
                              minutes(intersect(self._windows(peers[a][1]), self._windows(peers[b][1]))) / 60)
                pairs.append((a, b))
                rows += [pair_features(prof[a], prof[b], ctx), pair_features(prof[b], prof[a], ctx)]
        p = self.matcher.predict(rows)
        return {pair: float((p[2 * i] + p[2 * i + 1]) / 2) for i, pair in enumerate(pairs)}

    def _related(self, owner: Profile, theirs: Profile, mine_labels, their_labels) -> list[tuple[str, str]]:
        """Closely related (not identical) interest pairs, in the words each person typed, to explain a match."""
        key = self.matcher.space.key
        mine, other = {key(t): normalize(t) for t in mine_labels}, {key(t): normalize(t) for t in their_labels}
        exact = set(owner.keys) & set(theirs.keys)
        out = []
        for ka, va in zip(owner.keys, owner.vecs):
            if va is None or ka in exact or ka not in mine:
                continue
            best = max(((float(va @ vb), kb) for kb, vb in zip(theirs.keys, theirs.vecs) if vb is not None and kb not in exact and kb in other), default=None)
            if best and best[0] >= RELATED:
                out.append((best[0], mine[ka], other[best[1]]))
        return [(a, b) for _, a, b in sorted(out, reverse=True)[:2]]

    # ----- data access (private) -----
    def _fits(self, plan: Plan, excluded: set[UUID]) -> list[Fit]:
        skip = {UUID(str(x)) for x in excluded} | self.policy.blocked_with(plan.owner_id) | self._already_on(plan)
        owner_windows = self._windows([plan])
        out = []
        for user, plans in self._peers(plan).items():
            shared = intersect(owner_windows, self._windows(plans))
            if user.id in skip or not shared:
                continue
            out.append(Fit(self._preview(plan, user, plans[0]), shared, plans[0].activity_type == plan.activity_type, _same_event(plan, plans[0])))
        return sorted(out, key=lambda f: (f.preview.display_name.lower(), f.preview.user_id))

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


def _same_event(a: Plan, b: Plan) -> bool:
    x, y = (" ".join((p.public_location or "").lower().split()) for p in (a, b))
    return bool(x) and x == y

"""Home feed: open groups with room for one or two more, ranked for the viewer by the InGather matcher, and the join
requests people send from it. The host decides every request; nobody joins a group on their own.

A group is in the feed only while its host opted in (`open_to_requests`), its plan is active and in mutual
discovery, it hasn't started yet and it has open spots. The viewer never sees exact times, the venue name or full
names until they're accepted, and blocked people never see each other's groups.

In DEMO_MODE the fictional Austin hosts answer requests on their own after a short pause, based on the same match
score, so the flow can be shown end to end. Real hosts answer from the proposal page.
"""

import logging
import time
from datetime import datetime, timedelta, timezone
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.ml.features import Context, pair_features
from app.models import (
    ConsentEvent, DiscoveryMode, JoinRequest, JoinStatus, MemberStatus, Plan, PlanStatus, Proposal, ProposalMember,
    ProposalStatus, User, now,
)
from app.schemas import FeedItemOut, FeedPerson, JoinRequestOut
from app.services.clock import as_utc, intersect, merge, minutes
from app.services.matching import Matching
from app.services.policy import Policy, conflict
from app.security import not_found

log = logging.getLogger("ingather.feed")

JOINABLE = (ProposalStatus.invites_pending, ProposalStatus.awaiting_final)
ROSTER = (MemberStatus.invited, MemberStatus.accepted)
KINDS = {"cafe": "Café", "restaurant": "Restaurant", "food_hall": "Food hall", "museum": "Museum", "park": "Park",
         "library": "Library", "conference_venue": "Event venue", "public_venue": "Public place"}
DEMO_ACCEPT = 0.25  # fictional hosts say yes at or above this match
DEMO_DELAY = 4.0  # seconds before a fictional host answers


def first_name(user: User) -> str:
    return (user.display_name or "Someone").split(" ")[0][:30]


def short_names(users: list[User]) -> list[str]:
    """First names, adding a last initial where two people in the group share one ("Jamal R.", "Jamal T.")."""
    firsts = [first_name(u) for u in users]
    out = []
    for u, f in zip(users, firsts):
        parts = (u.display_name or "").split()
        out.append(f"{f} {parts[-1][0]}." if firsts.count(f) > 1 and len(parts) > 1 else f)
    return out


def part_of_day(dt: datetime) -> str:
    return "morning" if dt.hour < 12 else "afternoon" if dt.hour < 17 else "evening"


class Feed:
    def __init__(self, db: Session, settings: Settings, matching: Matching | None = None):
        self.db, self.settings = db, settings
        self.policy = Policy(db, settings)
        self.matching = matching or Matching(db, settings)

    # ----- publishing a plan as an open post -----
    def publish(self, plan: Plan, host: User) -> Proposal | None:
        """"Public" plan: make sure there is an open group with the host on it, so it shows on Home for people to ask to
        join. Reuses the plan's open group if it has one. Without an upcoming free time there's nothing to post."""
        from app.services.gather import GENERIC, VENUES

        current = self.db.scalars(select(Proposal).where(Proposal.plan_id == plan.id, Proposal.status.in_(JOINABLE))).first()
        if current:
            current.open_to_requests = True
            return current
        upcoming = sorted((as_utc(w.starts_at), as_utc(w.ends_at)) for w in plan.windows if as_utc(w.ends_at) > datetime.now(timezone.utc))
        if not upcoming:
            return None
        start = max(upcoming[0][0], datetime.now(timezone.utc) + timedelta(hours=1))
        end = min(upcoming[0][1], start + timedelta(minutes=90))
        kind = VENUES.get(plan.activity_type, ("cafe",))[0]
        proposal = Proposal(plan_id=plan.id, owner_id=host.id, status=ProposalStatus.invites_pending, activity_title=plan.title,
                            start_at=start, end_at=end, venue_label=GENERIC[kind].format(city=plan.city), venue_category=kind,
                            open_to_requests=True)
        proposal.members.append(ProposalMember(user_id=host.id, is_initiator=True, status=MemberStatus.accepted))
        self.db.add(proposal)
        return proposal

    def unpublish(self, plan: Plan) -> None:
        for p in self.db.scalars(select(Proposal).where(Proposal.plan_id == plan.id, Proposal.open_to_requests.is_(True))):
            p.open_to_requests = False

    # ----- what's open -----
    def _plan(self, proposal: Proposal) -> Plan:
        return self.db.get(Plan, proposal.plan_id)

    def roster(self, proposal: Proposal) -> list[User]:
        """Host first, then everyone invited or accepted."""
        host = next((m.user for m in proposal.members if m.is_initiator), None) or self.db.get(User, proposal.owner_id)
        return [host, *[m.user or self.db.get(User, m.user_id) for m in proposal.members if not m.is_initiator and m.status in ROSTER]]

    def spots_left(self, proposal: Proposal, plan: Plan) -> int:
        return max(0, min(plan.group_max, 4) - len(self.roster(proposal)))

    def joinable(self, proposal: Proposal | None, plan: Plan | None = None) -> bool:
        if proposal is None or not proposal.open_to_requests or proposal.status not in JOINABLE or proposal.start_at is None:
            return False
        plan = plan or self._plan(proposal)
        return bool(plan and plan.status == PlanStatus.active and plan.discovery_mode == DiscoveryMode.mutual_discovery
                    and as_utc(proposal.start_at) > datetime.now(timezone.utc) and self.spots_left(proposal, plan) > 0)

    def _visible_to(self, viewer: User, proposal: Proposal, blocked: set[UUID] | None = None) -> bool:
        """Not the viewer's own group, not one they're already on, and nobody in it is blocked with them."""
        if proposal.owner_id == viewer.id or any(m.user_id == viewer.id for m in proposal.members):
            return False
        blocked = self.policy.blocked_with(viewer.id) if blocked is None else blocked
        return not any(u.id in blocked for u in self.roster(proposal))

    # ----- scoring -----
    def _viewer_plans(self, viewer: User, city: str) -> list[Plan]:
        q = select(Plan).where(Plan.owner_id == viewer.id, Plan.status == PlanStatus.active)
        return [p for p in self.db.scalars(q) if p.city.strip().lower() == city.strip().lower()]

    def score(self, viewer: User, proposal: Proposal, plan: Plan, mine: list[Plan] | None = None) -> tuple[float, float, list[str], bool | None]:
        """(rank score, interest fit for display, interests the viewer shares with the group, whether they're free then)."""
        return self.score_many(viewer, [(proposal, plan)], mine)[0]

    def score_many(self, viewer: User, groups: list[tuple[Proposal, Plan]], mine: list[Plan] | None = None):
        """One batched matcher call for many groups. The rank score uses the viewer's real context (their plans in that
        city and free time); the displayed fit assumes the timing and activity work, so it reads as "how well you'd click"."""
        space = self.matching.matcher.space
        viewer_terms = [*viewer.interests]
        plans_by_city: dict[str, list[Plan]] = {}
        rows, meta = [], []
        for proposal, plan in groups:
            city = plan.city.strip().lower()
            if city not in plans_by_city:
                plans_by_city[city] = self._viewer_plans(viewer, plan.city) if mine is None else mine
            here = plans_by_city[city]
            terms = viewer_terms + [i for p in here for i in p.interests if i not in viewer_terms]
            person = space.profile(terms)
            roster = [u for u in self.roster(proposal) if u.id != viewer.id]  # once they've joined, don't score them against themselves
            group_terms = [*plan.interests]
            for u in roster[1:]:
                group_terms += [i for i in u.interests or [] if i not in group_terms]
            group = space.profile(group_terms[:10])
            start, end = as_utc(proposal.start_at), as_utc(proposal.end_at or proposal.start_at + timedelta(minutes=90))
            slot = (end - start).total_seconds() / 3600
            if here:
                free = merge([(w.starts_at, w.ends_at) for p in here for w in p.windows])
                hours = minutes(intersect(free, [(start, end)])) / 60
                best = max(here, key=lambda p: (p.activity_type == plan.activity_type, p.intent == plan.intent))
                ctx = Context(best.activity_type == plan.activity_type, best.intent == plan.intent,
                              bool(best.public_location and best.public_location.strip().lower() == (plan.public_location or "").strip().lower()), hours)
                free_then = hours >= slot - 1e-6
            else:  # no plan there yet: rank on interests, assume the time could work
                ctx, free_then = Context(False, False, False, slot), None
            ideal = Context(True, True, False, slot)
            start_row = len(rows)
            rows += [pair_features(group, person, ctx), pair_features(group, person, ideal)]
            rows += [pair_features(space.profile(u.interests or []), person, ideal) for u in roster[1:]]
            keys = set(person.keys)
            shared = list(dict.fromkeys(t for t in group_terms if space.key(t) in keys))
            meta.append((start_row, len(roster) - 1, shared, free_then))
        p = self.matching.matcher.predict(rows) if rows else []
        out = []
        for start_row, n_members, shared, free_then in meta:
            real, fit = float(p[start_row]), float(p[start_row + 1])
            if n_members:
                together = float(p[start_row + 2:start_row + 2 + n_members].mean())
                real, fit = 0.7 * real + 0.3 * together, 0.7 * fit + 0.3 * together
            out.append((real, fit, shared, free_then))
        return out

    # ----- the feed -----
    def items(self, viewer: User, limit: int = 50, sort: str = "match", activity: str | None = None) -> list[FeedItemOut]:
        """Open groups for the viewer. `sort`: "match" (best fit first, sooner first on ties) or "soonest" (earliest
        first, best fit first on ties). `activity` limits it to one kind of plan (a Home category tab). Groups they
        asked to join or joined always come first."""
        if not self.policy.can_discover(viewer):
            return []
        q = select(Proposal).where(Proposal.open_to_requests.is_(True), Proposal.status.in_(JOINABLE),
                                   Proposal.start_at > datetime.now(timezone.utc))
        requests = {r.proposal_id: r for r in self.db.scalars(select(JoinRequest).where(JoinRequest.user_id == viewer.id))}
        blocked = self.policy.blocked_with(viewer.id)
        groups = []
        for proposal in self.db.scalars(q):
            req = requests.get(proposal.id)
            if req and req.status == JoinStatus.declined:
                continue  # never shown again; the requester isn't told why
            plan = self._plan(proposal)
            if activity and plan.activity_type != activity:
                continue
            if self.joinable(proposal, plan) and self._visible_to(viewer, proposal, blocked):
                groups.append((proposal, plan))
        # Groups the viewer already joined stay at the top as a link into their group.
        joined = [self.db.get(Proposal, r.proposal_id) for r in requests.values() if r.status == JoinStatus.accepted]
        joined = [(p, self._plan(p)) for p in joined if p and p.status != ProposalStatus.cancelled]
        joined = [(p, plan) for p, plan in joined if not activity or plan.activity_type == activity]
        scored = [(*sc, p, plan) for (p, plan), sc in zip(groups + joined, self.score_many(viewer, groups + joined))]
        def key(t):
            fit, start = round(t[1] * 100), as_utc(t[4].start_at)  # sort on the fit people see, not a hidden score
            not_asked = requests.get(t[4].id) is None
            return (not_asked, -fit, start, str(t[4].id)) if sort == "match" else (not_asked, start, -fit, str(t[4].id))

        top = sorted(scored[:len(groups)], key=key)[:limit]
        return [self._item(fit, p, plan, shared, free_then, requests.get(p.id))
                for _, fit, shared, free_then, p, plan in scored[len(groups):] + top]

    def _item(self, fit: float, proposal: Proposal, plan: Plan, shared: list[str], free_then: bool | None,
              req: JoinRequest | None) -> FeedItemOut:
        local = as_utc(proposal.start_at).astimezone(ZoneInfo(plan.timezone))
        roster = self.roster(proposal)
        names = short_names(roster)
        group_interests = list(dict.fromkeys([*plan.interests]))[:6]
        bits = [f"You share {self._join(shared[:3])}" if shared else "New interests to try"]
        if free_then is True:
            bits.append("you're free then")
        elif free_then is False:
            bits.append("check the time against your plans")
        return FeedItemOut(
            proposal_id=proposal.id, title=proposal.activity_title, activity_type=plan.activity_type, city=plan.city,
            day=local.date(), part_of_day=part_of_day(local), venue_kind=KINDS.get(proposal.venue_category, "Public place"),
            preview=plan.preview_text, host=FeedPerson(first_name=names[0], avatar_url=roster[0].avatar_url),
            members=[FeedPerson(first_name=n, avatar_url=u.avatar_url) for n, u in zip(names[1:], roster[1:])],
            group_size=len(roster), spots_left=self.spots_left(proposal, plan), group_interests=group_interests,
            shared_interests=shared[:5], match=round(fit * 100), reason="; ".join(bits),
            free_then=free_then, request_status=req.status.value if req else None,
            welcome=req.welcome if req and req.status == JoinStatus.accepted else None, cover_url=proposal.cover_image_url,
        )

    @staticmethod
    def _join(items: list[str]) -> str:
        return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]

    # ----- requests -----
    def open_group(self, viewer: User, proposal_id: UUID) -> tuple[Proposal, Plan]:
        """A group the viewer may ask to join; uniform 404 otherwise (closed, full, blocked, their own...)."""
        proposal = self.db.get(Proposal, proposal_id)
        plan = self._plan(proposal) if proposal else None
        if not (proposal and self.joinable(proposal, plan) and self._visible_to(viewer, proposal)):
            raise not_found()
        return proposal, plan

    def request(self, viewer: User, proposal_id: UUID, message: str | None) -> JoinRequest:
        if not self.policy.can_discover(viewer):
            raise conflict("not_eligible")
        existing = self.db.scalar(select(JoinRequest).where(JoinRequest.proposal_id == proposal_id, JoinRequest.user_id == viewer.id))
        if existing and existing.status in (JoinStatus.pending, JoinStatus.accepted):
            return existing
        if existing and existing.status == JoinStatus.declined:
            raise not_found()
        proposal, plan = self.open_group(viewer, proposal_id)
        _, fit, _, _ = self.score(viewer, proposal, plan)
        req = existing or JoinRequest(proposal_id=proposal.id, user_id=viewer.id)
        req.status, req.message, req.score, req.created_at, req.responded_at = JoinStatus.pending, (message or "").strip()[:400] or None, round(fit, 4), now(), None
        self.db.add(req)
        self.db.add(ConsentEvent(user_id=viewer.id, kind="join_request", plan_id=plan.id, proposal_id=proposal.id,
                                 proposal_version=proposal.version, scope={"disclosed": ["display_name", "bio", "interests", "message"]}))
        self.db.commit()
        return req

    def withdraw(self, viewer: User, proposal_id: UUID) -> None:
        req = self.db.scalar(select(JoinRequest).where(JoinRequest.proposal_id == proposal_id, JoinRequest.user_id == viewer.id))
        if req is None or req.status != JoinStatus.pending:
            raise not_found()
        req.status, req.responded_at = JoinStatus.withdrawn, now()
        self.db.commit()

    def for_owner(self, proposal: Proposal) -> list[JoinRequestOut]:
        rows = self.db.scalars(select(JoinRequest).where(JoinRequest.proposal_id == proposal.id, JoinRequest.status == JoinStatus.pending)
                               .order_by(JoinRequest.created_at))
        return [JoinRequestOut(id=r.id, user_id=r.user_id, display_name=r.user.display_name, avatar_url=r.user.avatar_url,
                               bio=r.user.bio, interests=list(r.user.interests or []), message=r.message,
                               match=round(r.score * 100) if r.score is not None else None, status=r.status.value,
                               created_at=r.created_at) for r in rows]

    def decide(self, proposal: Proposal, request_id: UUID, accept: bool) -> JoinRequest:
        req = self.db.get(JoinRequest, request_id)
        if req is None or req.proposal_id != proposal.id:
            raise not_found()
        if req.status != JoinStatus.pending:
            raise conflict("not_pending")
        plan = self._plan(proposal)
        user = self.db.get(User, req.user_id)
        if accept:
            if not self.joinable(proposal, plan) or not self._visible_to(user, proposal) or not self.policy.can_discover(user):
                raise conflict("group_full_or_closed")
            at = now()
            proposal.members.append(ProposalMember(user_id=user.id, status=MemberStatus.accepted, invited_at=at, responded_at=at,
                                                   reason="Asked to join from their Home feed"))
            proposal.version += 1  # roster changed: earlier final confirmations no longer count
            for m in proposal.members:
                m.final_confirmed_version = None
            self.db.add(ConsentEvent(user_id=proposal.owner_id, kind="accept_join_request", plan_id=plan.id, proposal_id=proposal.id,
                                     proposal_version=proposal.version, scope={"user_id": str(user.id)}))
            req.welcome = self._welcome(user, proposal, plan)
        req.status, req.responded_at = (JoinStatus.accepted if accept else JoinStatus.declined), now()
        self.db.commit()
        return req

    def _welcome(self, user: User, proposal: Proposal, plan: Plan) -> str:
        from app.ai.join import welcome_note

        _, _, shared, _ = self.score(user, proposal, plan)
        local = as_utc(proposal.start_at).astimezone(ZoneInfo(plan.timezone))
        when = f"{local:%A} {part_of_day(local)}"
        return welcome_note(self.settings, first_name(user), proposal.activity_title, proposal.venue_category, when, shared)

    def draft(self, viewer: User, proposal_id: UUID) -> tuple[str, bool]:
        from app.ai.join import intro_draft

        proposal, plan = self.open_group(viewer, proposal_id)
        _, _, shared, _ = self.score(viewer, proposal, plan)
        local = as_utc(proposal.start_at).astimezone(ZoneInfo(plan.timezone))
        return intro_draft(self.settings, viewer.bio, list(viewer.interests or []), proposal.activity_title,
                           proposal.venue_category, f"{local:%A} {part_of_day(local)}", shared)


def auto_respond(request_id: UUID, delay: float = DEMO_DELAY) -> None:
    """DEMO_MODE only: a fictional Austin host answers a request after a short pause, by match score."""
    from app.config import get_settings
    from app.db import SessionLocal
    from app.demo.austin import is_synthetic

    settings = get_settings()
    if not settings.demo_mode:
        return
    time.sleep(delay)
    try:
        with SessionLocal() as db:
            req = db.get(JoinRequest, request_id)
            proposal = db.get(Proposal, req.proposal_id) if req else None
            if req is None or proposal is None or req.status != JoinStatus.pending or not is_synthetic(db.get(User, proposal.owner_id)):
                return
            feed = Feed(db, settings)
            accept = (req.score or 0) >= DEMO_ACCEPT and feed.joinable(proposal)
            feed.decide(proposal, req.id, accept)
    except Exception as exc:
        log.warning("demo auto-response failed: %s", type(exc).__name__)

"""Proposal/invitation state machine. The agent can only *suggest*; every invitation, acceptance and final
confirmation is an explicit human action recorded here."""

from collections import Counter
from datetime import datetime, timedelta
from typing import get_args
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import (
    AgentRun,
    ConsentEvent,
    MemberStatus,
    Message,
    OutboxEvent,
    Plan,
    PlanStatus,
    Proposal,
    ProposalMember,
    ProposalStatus,
    User,
    now,
)
from app.schemas import FinalizeIn, InvitationOut, MemberOut, MessageOut, ProposalOut, VenueCategory
from app.services.clock import as_utc, minutes
from app.services.matching import GroupAvailability, Matching
from app.services.policy import Policy, conflict
from app.security import not_found

OPEN = (ProposalStatus.pending_owner, ProposalStatus.invites_pending, ProposalStatus.awaiting_final)
ACTIVE = (MemberStatus.suggested, MemberStatus.invited, MemberStatus.accepted)
ROSTER = (MemberStatus.invited, MemberStatus.accepted)
INVITE_TTL = timedelta(hours=48)
DEFAULT_SLOT = timedelta(minutes=90)


class Proposals:
    def __init__(self, db: Session, settings: Settings):
        self.db, self.settings = db, settings
        self.policy = Policy(db, settings)
        self.matching = Matching(db, settings)

    # --- agent-facing --------------------------------------------------------------------------
    def save_agent_result(
        self,
        run: AgentRun,
        plan: Plan,
        picks: list[tuple[UUID, str]],
        activity_title: str,
        explanation: str,
        start_at,
        end_at,
        venue_label: str,
        venue_category: str,
        icebreaker: str | None,
        venue_details: dict | None = None,
    ) -> Proposal:
        ids = [UUID(str(uid)) for uid, _ in picks]
        if not ids or len(set(ids)) != len(ids):
            raise ValueError("picks must be a non-empty list of distinct users")
        eligible = {c.user_id for c in self.matching.eligible(plan, set(run.excluded_user_ids))}
        if any(str(i) not in eligible for i in ids):
            raise ValueError("every pick must be an eligible candidate for this plan")
        proposal = self.open_for(plan)
        current = [m.user_id for m in proposal.members if m.status in ACTIVE and not m.is_initiator] if proposal else []
        if len(current) + len(ids) > plan.group_max - 1:
            raise ValueError(f"group would exceed group_max={plan.group_max}")
        availability = self.matching.group_availability(plan, current + ids)
        if not availability.possible:
            raise ValueError(availability.reason)

        if proposal is None:
            proposal = Proposal(plan_id=plan.id, owner_id=plan.owner_id, activity_title=activity_title[:120])
            proposal.members.append(
                ProposalMember(user_id=plan.owner_id, is_initiator=True, status=MemberStatus.accepted)
            )
            self.db.add(proposal)
        else:
            proposal.version += 1
        proposal.start_at, proposal.end_at = self._slot(availability, start_at, end_at)
        proposal.status = ProposalStatus.pending_owner
        proposal.activity_title = activity_title[:120]
        proposal.explanation = explanation
        proposal.venue_label = (venue_label or "A public café near the venue")[:160]
        proposal.venue_category = venue_category if venue_category in get_args(VenueCategory) else "cafe"
        proposal.venue_details = venue_details
        proposal.venue_verified = False
        proposal.icebreaker = icebreaker[:280] if icebreaker else None
        for uid, reason in picks:
            proposal.members.append(ProposalMember(user_id=UUID(str(uid)), reason=(reason or "")[:300] or None))
        self.db.flush()
        run.proposal_id = proposal.id
        self.db.commit()
        return proposal

    def open_for(self, plan: Plan) -> Proposal | None:
        q = select(Proposal).where(Proposal.plan_id == plan.id, Proposal.status.in_(OPEN))
        return self.db.scalar(q.order_by(Proposal.created_at.desc()).limit(1))

    def exclusions(self, plan: Plan) -> set[UUID]:
        """People the owner passed on or who declined — never re-suggested for this plan."""
        q = (
            select(ProposalMember.user_id)
            .join(Proposal)
            .where(Proposal.plan_id == plan.id, ProposalMember.status.in_([MemberStatus.passed, MemberStatus.declined]))
        )
        return set(self.db.scalars(q))

    # --- owner actions -------------------------------------------------------------------------
    def pass_member(self, proposal: Proposal, user_id: UUID) -> None:
        member = self._member(proposal, user_id)
        if member.status != MemberStatus.suggested:
            raise conflict("not_suggested")
        member.status = MemberStatus.passed  # private: the candidate is never notified
        self.db.commit()

    def approve(self, proposal: Proposal, version: int, user_ids: list[UUID]) -> Proposal:
        plan = self.db.get(Plan, proposal.plan_id)
        if plan.status != PlanStatus.active:
            raise conflict("plan_inactive")
        if proposal.status not in (ProposalStatus.pending_owner, ProposalStatus.invites_pending):
            raise conflict("not_awaiting_approval")
        if version != proposal.version:
            raise conflict("stale_version")
        suggested = {m.user_id: m for m in proposal.members if m.status == MemberStatus.suggested}
        ids = set(user_ids)
        if not ids <= suggested.keys():
            raise conflict("not_suggested")
        for uid in ids:  # re-validate at time of use
            user = self.db.get(User, uid)
            if self.policy.blocked_between(proposal.owner_id, uid) or not self.policy.can_discover(user):
                raise conflict("candidate_unavailable")
        roster = [m.user_id for m in proposal.members if m.status in ROSTER and not m.is_initiator]
        if not self.matching.group_availability(plan, roster + list(ids)).possible:
            raise conflict("no_common_time")

        at = now()
        for uid in ids:
            m = suggested[uid]
            m.status, m.invited_at, m.expires_at = MemberStatus.invited, at, at + INVITE_TTL
        proposal.status = ProposalStatus.invites_pending
        self.db.add(
            ConsentEvent(
                user_id=proposal.owner_id,
                kind="approve_invites",
                plan_id=plan.id,
                proposal_id=proposal.id,
                proposal_version=version,
                scope={
                    "user_ids": sorted(str(i) for i in ids),
                    "disclosed": ["activity_title", "city", "date", "group_size", "initiator_name"],
                },
            )
        )
        self.db.commit()
        return proposal

    def finalize(self, proposal: Proposal, data: FinalizeIn) -> Proposal:
        if proposal.status not in OPEN or self.db.get(Plan, proposal.plan_id).status != PlanStatus.active:
            raise conflict("not_open")
        others = [m for m in proposal.members if not m.is_initiator]
        if any(m.status == MemberStatus.invited for m in others):
            raise conflict("invites_pending")
        if not any(m.status == MemberStatus.accepted for m in others):
            raise conflict("no_accepted_members")
        selected = None
        if data.venue_place_id:
            from app.services.places import nearby
            plan = self.db.get(Plan, proposal.plan_id)
            result = nearby(plan.public_location, plan.city, self.settings.venue_search_enabled)
            selected = next((p for p in result["places"] if p["id"] == data.venue_place_id), None)
            if selected is None:
                raise conflict("venue_not_found_search_again")
        if (data.venue_label is not None and data.venue_label != proposal.venue_label) or (data.venue_category is not None and data.venue_category != proposal.venue_category):
            proposal.venue_details = None
            proposal.venue_verified = False
        for field, value in data.model_dump(exclude_none=True, exclude={"venue_place_id"}).items():
            setattr(proposal, field, value)
        if selected:
            proposal.venue_label = selected["name"]
            proposal.venue_category = selected["category"]
            proposal.venue_details = selected
            proposal.venue_verified = False  # map listing is not a booking or a safety guarantee
        if proposal.start_at is None or proposal.end_at is None or as_utc(proposal.end_at) <= as_utc(proposal.start_at):
            raise conflict("invalid_time")
        self._bump(proposal)
        proposal.status = ProposalStatus.awaiting_final
        self.db.commit()
        return proposal

    # --- participant actions -------------------------------------------------------------------
    def respond(self, proposal: Proposal, user: User, accept: bool) -> Proposal:
        member = self._member(proposal, user.id)
        if member.status == MemberStatus.accepted:
            if accept:
                return proposal  # idempotent replay
            raise conflict("already_accepted")
        if member.expires_at and as_utc(member.expires_at) < now():
            member.status = MemberStatus.expired
            self.db.commit()
            raise conflict("invitation_expired")
        member.responded_at = now()
        if accept:
            member.status = MemberStatus.accepted
            self.db.add(
                ConsentEvent(
                    user_id=user.id,
                    kind="accept_invite",
                    plan_id=proposal.plan_id,
                    proposal_id=proposal.id,
                    proposal_version=proposal.version,
                )
            )
        else:
            member.status = MemberStatus.declined  # owner's agent replans; no reason is recorded
            self.db.add(OutboxEvent(kind="invitation_declined", aggregate_id=proposal.id, payload={}))
        self.db.commit()
        return proposal

    def confirm(self, proposal: Proposal, user: User, version: int) -> Proposal:
        if proposal.status != ProposalStatus.awaiting_final:
            raise conflict("not_awaiting_final")
        if version != proposal.version:
            raise conflict("stale_version")
        self._member(proposal, user.id).final_confirmed_version = version
        self.db.add(
            ConsentEvent(
                user_id=user.id,
                kind="confirm_final",
                plan_id=proposal.plan_id,
                proposal_id=proposal.id,
                proposal_version=version,
                scope={"start_at": str(proposal.start_at), "venue_label": proposal.venue_label},
            )
        )
        self.db.flush()
        if self._all_confirmed(proposal, version):
            # compare-and-set: only the exact version everyone confirmed can become `confirmed`
            done = self.db.execute(
                update(Proposal)
                .where(
                    Proposal.id == proposal.id,
                    Proposal.version == version,
                    Proposal.status == ProposalStatus.awaiting_final,
                )
                .values(status=ProposalStatus.confirmed)
            )
            if done.rowcount == 1:
                from app.services.chats import Chats
                Chats(self.db, self.settings).connect(proposal)
                from app.ai.icebreaker import write_icebreaker

                people = [m.user for m in proposal.members if m.status in ROSTER and m.status != MemberStatus.invited]
                shared = common_interests([u.interests or [] for u in people])
                proposal.icebreaker = write_icebreaker(
                    self.settings, proposal.activity_title, proposal.venue_category, shared, proposal.icebreaker or ""
                ) or None
                if proposal.icebreaker:
                    self.db.add(Message(proposal_id=proposal.id, sender_id=None, body=proposal.icebreaker))
        self.db.commit()
        self.db.refresh(proposal)
        return proposal

    def leave(self, proposal: Proposal, user: User) -> None:
        if proposal.owner_id == user.id:
            proposal.status = ProposalStatus.cancelled
        else:
            self._remove(proposal, self._member(proposal, user.id))
        self.db.commit()

    def remove_blocked(self, a: UUID, b: UUID) -> None:
        """After a block, neither person stays on the other's proposals."""
        q = select(Proposal).where(Proposal.owner_id.in_([a, b]), Proposal.status != ProposalStatus.cancelled)
        for proposal in self.db.scalars(q):
            other = b if proposal.owner_id == a else a
            member = next((m for m in proposal.members if m.user_id == other), None)
            if member and member.status != MemberStatus.removed:
                self._remove(proposal, member)
        self.db.commit()

    def cancel_for_plan(self, plan: Plan) -> None:
        self.db.execute(
            update(Proposal).where(Proposal.plan_id == plan.id, Proposal.status.in_(OPEN)).values(status=ProposalStatus.cancelled)
        )

    # --- chat ----------------------------------------------------------------------------------
    def messages(self, proposal: Proposal) -> list[MessageOut]:
        q = select(Message, User).outerjoin(User, User.id == Message.sender_id).where(Message.proposal_id == proposal.id)
        return [MessageOut.build(m, u) for m, u in self.db.execute(q.order_by(Message.created_at))]

    def post_message(self, proposal: Proposal, user: User, body: str) -> MessageOut:
        msg = Message(proposal_id=proposal.id, sender_id=user.id, body=body)
        self.db.add(msg)
        self.db.commit()
        return MessageOut.build(msg, user)

    # --- read models ---------------------------------------------------------------------------
    def invitations(self, user: User) -> list[InvitationOut]:
        q = (
            select(ProposalMember, Proposal, Plan, User)
            .join(Proposal, Proposal.id == ProposalMember.proposal_id)
            .join(Plan, Plan.id == Proposal.plan_id)
            .join(User, User.id == Proposal.owner_id)
            .where(
                ProposalMember.user_id == user.id,
                ProposalMember.is_initiator.is_(False),
                ProposalMember.status.in_(ROSTER),
                Proposal.status != ProposalStatus.cancelled,
            )
            .order_by(ProposalMember.invited_at.desc())
        )
        blocked = self.policy.blocked_with(user.id)
        return [
            InvitationOut(
                proposal_id=p.id,
                activity_title=p.activity_title,
                city=plan.city,
                date=self._local_date(p, plan),
                group_size=self._group_size(p),
                from_user_id=owner.id,
                from_display_name=owner.display_name,
                from_avatar_url=owner.avatar_url,
                status=m.status,
                expires_at=m.expires_at,
            )
            for m, p, plan, owner in self.db.execute(q)
            if owner.id not in blocked
        ]

    def view(self, proposal: Proposal, viewer: User, role: str) -> ProposalOut:
        """Shape a proposal for one viewer according to the disclosure rules in the API contract."""
        plan = self.db.get(Plan, proposal.plan_id)
        me = next((m for m in proposal.members if m.user_id == viewer.id), None)
        initiator = next(m for m in proposal.members if m.is_initiator)
        owner, final = role == "owner", proposal.status in (ProposalStatus.awaiting_final, ProposalStatus.confirmed)
        details = owner or (role == "member" and final)
        if owner:
            members = [self._member_out(m, proposal, reason=True) for m in proposal.members if m.status != MemberStatus.removed]
        elif role == "member":
            members = [self._member_out(m, proposal, reason=False) for m in proposal.members if m.status in ROSTER]
        else:
            members = []
        return ProposalOut(
            id=proposal.id,
            plan_id=proposal.plan_id,
            version=proposal.version,
            status=proposal.status,
            activity_title=proposal.activity_title,
            explanation=proposal.explanation if owner else "",
            start_at=proposal.start_at if details else self._local_date(proposal, plan),
            end_at=proposal.end_at if details else None,
            timezone=plan.timezone,
            city=plan.city,
            venue_label=proposal.venue_label if details else None,
            venue_category=proposal.venue_category if details else None,
            venue_verified=proposal.venue_verified,
            venue_details=proposal.venue_details if details else None,
            icebreaker=proposal.icebreaker if role != "invitee" else None,
            viewer_role=role,
            initiator_name=initiator.user.display_name,
            initiator_user_id=initiator.user_id,
            latest_run_id=self._latest_run_id(plan) if owner else None,
            members=members,
            group_size=self._group_size(proposal),
            my_status=me.status if me else MemberStatus.accepted,
            i_confirmed=bool(me and me.final_confirmed_version == proposal.version),
        )

    # --- internals -----------------------------------------------------------------------------
    def _latest_run_id(self, plan: Plan) -> UUID | None:
        q = select(AgentRun.id).where(AgentRun.plan_id == plan.id).order_by(AgentRun.created_at.desc()).limit(1)
        return self.db.scalar(q)

    def _member(self, proposal: Proposal, user_id: UUID) -> ProposalMember:
        member = next((m for m in proposal.members if m.user_id == user_id), None)
        if member is None:
            raise not_found()
        return member

    def _remove(self, proposal: Proposal, member: ProposalMember) -> None:
        was_on_roster = member.status in ROSTER
        member.status = MemberStatus.removed
        if not was_on_roster or proposal.status not in OPEN:
            return
        self._bump(proposal)  # roster changed: earlier final confirmations are void
        others = [m for m in proposal.members if not m.is_initiator and m.status in ROSTER]
        if not others:
            proposal.status = ProposalStatus.pending_owner
        elif proposal.status == ProposalStatus.awaiting_final and any(m.status == MemberStatus.invited for m in others):
            proposal.status = ProposalStatus.invites_pending

    @staticmethod
    def _bump(proposal: Proposal) -> None:
        proposal.version += 1
        for m in proposal.members:
            m.final_confirmed_version = None

    @staticmethod
    def _all_confirmed(proposal: Proposal, version: int) -> bool:
        if any(m.status == MemberStatus.invited for m in proposal.members):
            return False
        accepted = [m for m in proposal.members if m.status == MemberStatus.accepted]
        return len(accepted) >= 2 and all(m.final_confirmed_version == version for m in accepted)

    @staticmethod
    def _group_size(proposal: Proposal) -> int:
        return sum(m.status in ROSTER for m in proposal.members)

    @staticmethod
    def _local_date(proposal: Proposal, plan: Plan):
        if proposal.start_at is None:
            return plan.start_date
        return as_utc(proposal.start_at).astimezone(ZoneInfo(plan.timezone)).date()

    @staticmethod
    def _member_out(m: ProposalMember, proposal: Proposal, reason: bool) -> MemberOut:
        return MemberOut(
            user_id=m.user_id,
            display_name=m.user.display_name,
            avatar_url=m.user.avatar_url,
            interests=m.user.interests,
            is_initiator=m.is_initiator,
            status=m.status,
            reason=m.reason if reason else None,
            confirmed=m.final_confirmed_version == proposal.version,
        )

    @staticmethod
    def _slot(availability: GroupAvailability, start_at, end_at) -> tuple[datetime, datetime]:
        """Keep the agent's proposed time if it sits inside a common window; otherwise use the first one."""
        if start_at and end_at:
            s, e = (as_utc(datetime.fromisoformat(x) if isinstance(x, str) else x) for x in (start_at, end_at))
            if e > s and any(ws <= s and e <= we for ws, we in availability.windows):
                return s, e
        ws, we = next(w for w in availability.windows if minutes([w]) >= 60)
        return ws, min(we, ws + DEFAULT_SLOT)


def common_interests(groups: list[list[str]]) -> list[str]:
    """Interests at least half the group (and two people) share, most common first."""
    counts = Counter(i for g in groups for i in set(g))
    need = max(2, (len(groups) + 1) // 2)
    return [i for i, n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])) if n >= need]

"""All authorization decisions. Routers and the agent ask Policy; nothing else decides access."""

from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import AgentRun, Block, DirectConnection, MemberStatus, Plan, Proposal, ProposalStatus, User, Verification
from app.security import not_found


def conflict(detail: str) -> HTTPException:
    return HTTPException(status.HTTP_409_CONFLICT, detail)


class Policy:
    def __init__(self, db: Session, settings: Settings):
        self.db, self.settings = db, settings

    def can_discover(self, user: User) -> bool:
        verified = user.verification == Verification.verified_live or (
            user.verification == Verification.verified_demo and self.settings.demo_mode
        )
        return bool(user.is_adult and verified and not user.discovery_paused)

    def own_plan(self, user: User, plan_id: UUID) -> Plan:
        plan = self.db.get(Plan, plan_id)
        if plan is None or plan.owner_id != user.id:
            raise not_found()
        return plan

    def own_run(self, user: User, run_id: UUID) -> AgentRun:
        run = self.db.get(AgentRun, run_id)
        if run is None or run.owner_id != user.id:
            raise not_found()
        return run

    def blocked_between(self, a: UUID, b: UUID) -> bool:
        return self.db.scalar(select(Block.id).where(self._pair(a, b)).limit(1)) is not None

    def blocked_with(self, user_id: UUID) -> set[UUID]:
        rows = self.db.execute(
            select(Block.blocker_id, Block.blocked_id).where(or_(Block.blocker_id == user_id, Block.blocked_id == user_id))
        )
        return {x for pair in rows for x in pair} - {user_id}

    def viewer_role(self, user: User, proposal: Proposal) -> str | None:
        if proposal.owner_id == user.id:
            return "owner"
        if proposal.status == ProposalStatus.cancelled or self.blocked_between(user.id, proposal.owner_id):
            return None
        member = next((m for m in proposal.members if m.user_id == user.id), None)
        return {MemberStatus.invited: "invitee", MemberStatus.accepted: "member"}.get(member.status) if member else None

    def visible_proposal(self, user: User, proposal_id: UUID, *roles: str) -> tuple[Proposal, str]:
        """Proposal plus the viewer's role; uniform 404 if the viewer has no (allowed) role."""
        proposal = self.db.get(Proposal, proposal_id)
        role = self.viewer_role(user, proposal) if proposal else None
        if role is None or (roles and role not in roles):
            raise not_found()
        return proposal, role

    def direct_peer(self, user: User, peer_id: UUID) -> User:
        pair = tuple(sorted((user.id, peer_id), key=str))
        if user.id == peer_id or self.blocked_between(user.id, peer_id) or self.db.get(DirectConnection, pair) is None:
            raise not_found()
        peer = self.db.get(User, peer_id)
        if peer is None:
            raise not_found()
        return peer

    @staticmethod
    def _pair(a: UUID, b: UUID):
        return or_((Block.blocker_id == a) & (Block.blocked_id == b), (Block.blocker_id == b) & (Block.blocked_id == a))

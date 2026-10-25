"""Data model. Sensitive columns (goal_text, availability windows, email,
password_hash, verification fields) must never be serialized to non-owners."""

import uuid
from datetime import date, datetime, timezone
from enum import StrEnum

from sqlalchemy import JSON, Date, DateTime, Enum, Float, ForeignKey, Integer, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def now() -> datetime:
    return datetime.now(timezone.utc)


def str_enum(cls):
    return Enum(cls, native_enum=False, length=32, values_callable=lambda e: [m.value for m in e])


class Verification(StrEnum):
    unverified = "unverified"
    verified_demo = "verified_demo"  # simulated; no ID checked
    verified_live = "verified_live"  # only ever set by a signed provider webhook


class DiscoveryMode(StrEnum):
    private_browse = "private_browse"
    mutual_discovery = "mutual_discovery"
    paused = "paused"


class PlanStatus(StrEnum):
    active = "active"
    paused = "paused"
    cancelled = "cancelled"
    expired = "expired"


class ProposalStatus(StrEnum):
    pending_owner = "pending_owner"  # agent suggested people; owner must approve invites
    invites_pending = "invites_pending"  # invitations sent, waiting for replies
    awaiting_final = "awaiting_final"  # everyone accepted intro; confirming final time/venue
    confirmed = "confirmed"
    cancelled = "cancelled"


class MemberStatus(StrEnum):
    suggested = "suggested"
    passed = "passed"  # owner passed privately; candidate never told
    invited = "invited"
    accepted = "accepted"
    declined = "declined"
    expired = "expired"
    removed = "removed"


class RunStatus(StrEnum):
    running = "running"
    completed = "completed"
    failed = "failed"


class Id:
    @staticmethod
    def pk() -> Mapped[uuid.UUID]:
        return mapped_column(Uuid, primary_key=True, default=uuid.uuid4)


class User(Base):
    __tablename__ = "users"
    id: Mapped[uuid.UUID] = Id.pk()
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    display_name: Mapped[str] = mapped_column(String(60))
    avatar_url: Mapped[str | None] = mapped_column(String(500))
    bio: Mapped[str | None] = mapped_column(String(280))
    interests: Mapped[list[str]] = mapped_column(JSON, default=list)
    verification: Mapped[Verification] = mapped_column(str_enum(Verification), default=Verification.unverified)
    is_adult: Mapped[bool] = mapped_column(default=False)
    # PRIVATE, backend-only: identity provider correlation (never serialized)
    verification_provider: Mapped[str | None] = mapped_column(String(20))  # demo|stripe
    verification_session_id: Mapped[str | None] = mapped_column(String(120), index=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_demo: Mapped[bool] = mapped_column(default=False)
    discovery_paused: Mapped[bool] = mapped_column(default=False)
    group_only: Mapped[bool] = mapped_column(default=True)
    # PRIVATE, owner-only: optional coarse "home area" (city/neighborhood/ZIP text). Coordinates are
    # server-geocoded and rounded to 0.01 deg (~1 km); never an exact address, never live GPS, never shown to others.
    home_area: Mapped[str | None] = mapped_column(String(80))
    home_lat: Mapped[float | None] = mapped_column(Float)
    home_lng: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Plan(Base):
    __tablename__ = "plans"
    id: Mapped[uuid.UUID] = Id.pk()
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    activity_type: Mapped[str] = mapped_column(String(30))  # travel|conference|hackathon|study|coffee|event|other
    title: Mapped[str] = mapped_column(String(120))
    goal_text: Mapped[str] = mapped_column(Text)  # PRIVATE
    city: Mapped[str] = mapped_column(String(80), index=True)
    public_location: Mapped[str | None] = mapped_column(String(200))  # owner-supplied public event venue; private plan context
    timezone: Mapped[str] = mapped_column(String(64))  # IANA, e.g. America/New_York
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    intent: Mapped[str] = mapped_column(String(20), default="friends")  # friends|networking|activity
    interests: Mapped[list[str]] = mapped_column(JSON, default=list)
    group_min: Mapped[int] = mapped_column(Integer, default=3)
    group_max: Mapped[int] = mapped_column(Integer, default=4)
    group_only: Mapped[bool] = mapped_column(default=True)
    discovery_mode: Mapped[DiscoveryMode] = mapped_column(str_enum(DiscoveryMode), default=DiscoveryMode.private_browse)
    status: Mapped[PlanStatus] = mapped_column(str_enum(PlanStatus), default=PlanStatus.active)
    preview_text: Mapped[str | None] = mapped_column(String(200))  # owner-approved public-safe blurb
    cover_image_url: Mapped[str | None] = mapped_column(String(500))
    ai_consent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

    windows: Mapped[list["AvailabilityWindow"]] = relationship(cascade="all, delete-orphan", order_by="AvailabilityWindow.starts_at")


class AvailabilityWindow(Base):
    """PRIVATE. Stored in UTC; only the matching service reads other people's windows."""

    __tablename__ = "availability_windows"
    id: Mapped[uuid.UUID] = Id.pk()
    plan_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("plans.id", ondelete="CASCADE"), index=True)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Block(Base):
    __tablename__ = "blocks"
    __table_args__ = (UniqueConstraint("blocker_id", "blocked_id"),)
    id: Mapped[uuid.UUID] = Id.pk()
    blocker_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    blocked_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Proposal(Base):
    """A group gathering for one plan. `version` bumps whenever roster/time/venue changes;
    final confirmations are only valid for the current version."""

    __tablename__ = "proposals"
    id: Mapped[uuid.UUID] = Id.pk()
    plan_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("plans.id", ondelete="CASCADE"), index=True)
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[ProposalStatus] = mapped_column(str_enum(ProposalStatus), default=ProposalStatus.pending_owner)
    activity_title: Mapped[str] = mapped_column(String(120))
    explanation: Mapped[str] = mapped_column(Text, default="")
    start_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    venue_label: Mapped[str] = mapped_column(String(160), default="A public café near the venue")
    venue_category: Mapped[str] = mapped_column(String(40), default="cafe")  # always a public category
    venue_details: Mapped[dict | None] = mapped_column(JSON)  # provider-sourced meetup coordinates, never event origin
    venue_verified: Mapped[bool] = mapped_column(default=False)  # False = generic suggestion, not a real booking
    icebreaker: Mapped[str | None] = mapped_column(String(280))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)

    members: Mapped[list["ProposalMember"]] = relationship(cascade="all, delete-orphan", order_by="ProposalMember.created_at")


class ProposalMember(Base):
    """One row per person on a proposal; doubles as the invitation record."""

    __tablename__ = "proposal_members"
    __table_args__ = (UniqueConstraint("proposal_id", "user_id"),)
    id: Mapped[uuid.UUID] = Id.pk()
    proposal_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("proposals.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    is_initiator: Mapped[bool] = mapped_column(default=False)
    status: Mapped[MemberStatus] = mapped_column(str_enum(MemberStatus), default=MemberStatus.suggested)
    reason: Mapped[str | None] = mapped_column(String(300))  # grounded compatibility reason (owner-visible)
    final_confirmed_version: Mapped[int | None] = mapped_column(Integer)
    invited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

    user: Mapped[User] = relationship(lazy="joined")


class ConsentEvent(Base):
    """Immutable ledger of explicit human approvals."""

    __tablename__ = "consent_events"
    id: Mapped[uuid.UUID] = Id.pk()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(40))  # ai_processing|discovery|approve_invites|accept_invite|confirm_final
    plan_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    proposal_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    proposal_version: Mapped[int | None] = mapped_column(Integer)
    scope: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class AgentRun(Base):
    __tablename__ = "agent_runs"
    id: Mapped[uuid.UUID] = Id.pk()
    plan_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("plans.id", ondelete="CASCADE"), index=True)
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    proposal_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    trigger: Mapped[str] = mapped_column(String(20), default="user")  # user|pass|decline|feedback
    mode: Mapped[str] = mapped_column(String(10), default="ml")  # ml (InGather matcher); older rows: live|offline
    status: Mapped[RunStatus] = mapped_column(str_enum(RunStatus), default=RunStatus.running)
    goal: Mapped[str] = mapped_column(Text, default="")
    excluded_user_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    summary: Mapped[str | None] = mapped_column(Text)
    error: Mapped[str | None] = mapped_column(String(300))
    model: Mapped[str | None] = mapped_column(String(60))  # matcher version, e.g. matcher-1
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    events: Mapped[list["AgentEvent"]] = relationship(cascade="all, delete-orphan", order_by="AgentEvent.seq")


class AgentEvent(Base):
    """Safe, owner-visible timeline entry. `kind=tool` rows are written only by real backend steps."""

    __tablename__ = "agent_events"
    id: Mapped[uuid.UUID] = Id.pk()
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("agent_runs.id", ondelete="CASCADE"), index=True)
    seq: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(12))  # tool|model|system|error|review
    agent: Mapped[str | None] = mapped_column(String(20))  # pipeline step: gather|matcher|scheduler|venue|checks
    tool_name: Mapped[str | None] = mapped_column(String(60))
    summary: Mapped[str] = mapped_column(String(400))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Message(Base):
    __tablename__ = "messages"
    id: Mapped[uuid.UUID] = Id.pk()
    proposal_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("proposals.id", ondelete="CASCADE"), index=True)
    sender_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))  # None = agent icebreaker
    body: Mapped[str] = mapped_column(String(1000))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Report(Base):
    __tablename__ = "reports"
    id: Mapped[uuid.UUID] = Id.pk()
    reporter_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    reported_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    proposal_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    reason: Mapped[str] = mapped_column(String(30))  # harassment|unsafe_request|impersonation|spam|threat|other
    details: Mapped[str | None] = mapped_column(String(1000))
    status: Mapped[str] = mapped_column(String(20), default="open")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class OutboxEvent(Base):
    """Durable trigger for background work (e.g. invitation_declined -> agent replan)."""

    __tablename__ = "outbox_events"
    id: Mapped[uuid.UUID] = Id.pk()
    kind: Mapped[str] = mapped_column(String(40), index=True)
    aggregate_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class ConnectorToken(Base):
    """Personal access token letting the user's own Muse agent call InGather via MCP. Stores only a hash."""

    __tablename__ = "connector_tokens"
    id: Mapped[uuid.UUID] = Id.pk()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    label: Mapped[str] = mapped_column(String(60), default="Muse")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class DirectConnection(Base):
    """A connection established when two people confirm the same meetup. Blocks override it."""
    __tablename__ = "direct_connections"
    user_a_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    user_b_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class DirectMessage(Base):
    __tablename__ = "direct_messages"
    id: Mapped[uuid.UUID] = Id.pk()
    sender_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    recipient_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    body: Mapped[str] = mapped_column(String(1000))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class VenuePoll(Base):
    """One venue vote per proposal. `round` bumps on a re-roll ("none of these work"); only one re-roll allowed."""

    __tablename__ = "venue_polls"
    id: Mapped[uuid.UUID] = Id.pk()
    proposal_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("proposals.id", ondelete="CASCADE"), unique=True)
    round: Mapped[int] = mapped_column(Integer, default=1)
    rerolls_used: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(12), default="open")  # open|decided
    winner_option_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    source: Mapped[str] = mapped_column(String(12), default="fallback")  # grounded|fallback
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

    options: Mapped[list["VenueOption"]] = relationship(cascade="all, delete-orphan", order_by="VenueOption.rank")


class VenueOption(Base):
    __tablename__ = "venue_options"
    id: Mapped[uuid.UUID] = Id.pk()
    poll_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("venue_polls.id", ondelete="CASCADE"), index=True)
    round: Mapped[int] = mapped_column(Integer)
    rank: Mapped[int] = mapped_column(Integer)  # venue agent's ranking, 1 = best; breaks ties
    name: Mapped[str] = mapped_column(String(160))
    area: Mapped[str | None] = mapped_column(String(200))  # address or neighborhood
    category: Mapped[str] = mapped_column(String(40))
    why: Mapped[str] = mapped_column(String(400), default="")
    reservation_url: Mapped[str | None] = mapped_column(String(500))
    source_url: Mapped[str | None] = mapped_column(String(500))
    verified: Mapped[bool] = mapped_column(default=False)  # True only if it came from grounded search with a source URL


class VenueVote(Base):
    __tablename__ = "venue_votes"
    __table_args__ = (UniqueConstraint("poll_id", "user_id"),)
    id: Mapped[uuid.UUID] = Id.pk()
    poll_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("venue_polls.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    option_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("venue_options.id", ondelete="CASCADE"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)

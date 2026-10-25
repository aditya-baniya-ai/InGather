"""Request/response shapes (docs/api-contract.md). Response models are the only way data leaves the API,
so private columns are simply absent from every non-owner schema."""

from datetime import date, datetime
from typing import Annotated, Literal
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import AfterValidator, BaseModel, ConfigDict, EmailStr, Field, StrictBool, field_validator, model_validator

from app.models import AgentRun, Message, Plan, User
from app.services.clock import as_utc

UTC = Annotated[datetime, AfterValidator(as_utc)]
Interest = Annotated[str, Field(min_length=1, max_length=40)]
ActivityType = Literal["travel", "conference", "hackathon", "study", "coffee", "event", "other"]
Intent = Literal["friends", "networking", "activity"]
VenueCategory = Literal["cafe", "restaurant", "food_hall", "museum", "park", "library", "conference_venue", "public_venue"]


class Out(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# --- auth / me ---------------------------------------------------------------------------------
class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    display_name: str = Field(min_length=1, max_length=60)


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(max_length=128)


class DemoLoginIn(BaseModel):
    email: EmailStr


class MeUpdate(BaseModel):
    """Only these fields are writable; anything else (e.g. verification) is dropped by pydantic."""

    display_name: str | None = Field(None, min_length=1, max_length=60)
    bio: str | None = Field(None, max_length=280)
    interests: list[Interest] | None = Field(None, max_length=20)
    avatar_url: str | None = Field(None, max_length=500)
    discovery_paused: bool | None = None
    group_only: bool | None = None
    home_area: str | None = Field(None, max_length=80)  # city / neighborhood / ZIP; "" clears it


class MeOut(Out):
    id: UUID
    email: str
    display_name: str
    avatar_url: str | None
    bio: str | None
    interests: list[str]
    verification: str
    is_demo: bool
    discovery_paused: bool
    group_only: bool
    can_discover: bool
    home_area: str | None = None  # private: only ever returned to its owner
    home_area_located: bool = False  # whether the server could place it (coords themselves are never returned)

    @classmethod
    def build(cls, user: User, can_discover: bool) -> "MeOut":
        fields = {k: getattr(user, k) for k in cls.model_fields if k not in ("can_discover", "home_area_located")}
        located = user.home_lat is not None and user.home_lng is not None
        return cls.model_validate({**fields, "can_discover": can_discover, "home_area_located": located})


class TokenOut(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    user: MeOut


class DemoAccountOut(Out):
    email: str
    display_name: str
    avatar_url: str | None
    bio: str | None


# --- plans -------------------------------------------------------------------------------------
class WindowIn(Out):
    starts_at: UTC
    ends_at: UTC

    @model_validator(mode="after")
    def _order(self):
        if self.ends_at <= self.starts_at:
            raise ValueError("ends_at must be after starts_at")
        return self


class PlanFields(BaseModel):
    activity_type: ActivityType
    title: str = Field(min_length=1, max_length=120)
    goal_text: str = Field(min_length=1, max_length=2000)
    city: str = Field(min_length=1, max_length=80)
    public_location: str | None = Field(None, max_length=200)
    timezone: str = Field(max_length=64)
    start_date: date
    end_date: date
    intent: Intent = "friends"
    interests: list[Interest] = Field(default_factory=list, max_length=20)
    group_min: int = Field(3, ge=2, le=4)
    group_max: int = Field(4, ge=2, le=4)
    group_only: bool = True
    preview_text: str | None = Field(None, max_length=200)
    windows: list[WindowIn] = Field(default_factory=list, max_length=60)

    @field_validator("timezone")
    @classmethod
    def _tz(cls, v: str) -> str:
        try:
            ZoneInfo(v)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError("unknown IANA timezone")
        return v

    @field_validator("city", "title")
    @classmethod
    def _strip(cls, v: str) -> str:
        return v.strip()


class PlanIn(PlanFields):
    @model_validator(mode="after")
    def _valid(self):
        if self.end_date < self.start_date:
            raise ValueError("end_date must be on or after start_date")
        if self.group_min > self.group_max:
            raise ValueError("group_min must be <= group_max")
        return self


class PlanPatch(BaseModel):
    """Partial PlanIn; the merged result is re-validated as a full PlanIn."""

    activity_type: ActivityType | None = None
    title: str | None = None
    goal_text: str | None = None
    city: str | None = None
    public_location: str | None = Field(None, max_length=200)
    timezone: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    intent: Intent | None = None
    interests: list[str] | None = None
    group_min: int | None = None
    group_max: int | None = None
    group_only: bool | None = None
    preview_text: str | None = None
    windows: list[WindowIn] | None = None


class DiscoveryIn(BaseModel):
    mode: Literal["private_browse", "mutual_discovery", "paused"]
    ai_consent: bool | None = None


class PlanOut(PlanFields, Out):
    id: UUID
    discovery_mode: str
    status: str
    cover_image_url: str | None
    ai_consent: bool
    created_at: UTC
    latest_proposal_id: UUID | None
    latest_run_id: UUID | None
    windows: list[WindowIn]

    @classmethod
    def build(cls, plan: Plan, latest_proposal_id: UUID | None, latest_run_id: UUID | None) -> "PlanOut":
        data = {k: getattr(plan, k) for k in cls.model_fields if hasattr(plan, k)}
        return cls.model_validate(
            {
                **data,
                "ai_consent": plan.ai_consent_at is not None,
                "latest_proposal_id": latest_proposal_id,
                "latest_run_id": latest_run_id,
            }
        )


# --- agent runs --------------------------------------------------------------------------------
class RunIn(BaseModel):
    plan_id: UUID
    goal: str = Field("", max_length=500)


class EventOut(Out):
    seq: int
    kind: str
    agent: str | None = None
    tool_name: str | None
    summary: str
    created_at: UTC


class RunOut(Out):
    id: UUID
    plan_id: UUID
    proposal_id: UUID | None
    trigger: str
    mode: str
    status: str
    summary: str | None
    error: str | None
    model: str | None
    created_at: UTC
    finished_at: UTC | None
    events: list[EventOut]

    @classmethod
    def build(cls, run: AgentRun) -> "RunOut":
        return cls.model_validate(run)


# --- proposals ---------------------------------------------------------------------------------
Feedback = Literal["prefer_same_event", "prefer_group", "different_activity", "schedule"] | None


class FeedbackIn(BaseModel):
    feedback: Feedback = None


class ApproveIn(BaseModel):
    version: int
    user_ids: list[UUID] = Field(min_length=1, max_length=3)


class RespondIn(BaseModel):
    accept: bool


class FinalizeIn(BaseModel):
    venue_place_id: str | None = Field(None, max_length=80)
    start_at: UTC | None = None
    end_at: UTC | None = None
    venue_label: str | None = Field(None, min_length=1, max_length=160)
    venue_category: VenueCategory | None = None


class ConfirmIn(BaseModel):
    version: int


class MemberOut(BaseModel):
    user_id: UUID
    display_name: str
    avatar_url: str | None
    interests: list[str]
    is_initiator: bool
    status: str
    reason: str | None
    confirmed: bool


class ProposalOut(BaseModel):
    id: UUID
    plan_id: UUID
    version: int
    status: str
    activity_title: str
    explanation: str
    start_at: UTC | date | None  # invitees only get the local date
    end_at: UTC | None
    timezone: str
    city: str
    venue_label: str | None
    venue_category: str | None
    venue_verified: bool
    venue_details: dict | None = None
    icebreaker: str | None
    viewer_role: Literal["owner", "invitee", "member"]
    initiator_name: str
    initiator_user_id: UUID  # lets invitees block the organizer
    latest_run_id: UUID | None  # owner only: the newest agent run for this plan
    members: list[MemberOut]
    group_size: int
    my_status: str
    i_confirmed: bool
    open_to_requests: bool = False  # owner only: people can ask to join from their Home feed


class InvitationOut(BaseModel):
    proposal_id: UUID
    activity_title: str
    city: str
    date: date | None
    group_size: int
    from_user_id: UUID
    from_display_name: str
    from_avatar_url: str | None
    status: str
    expires_at: UTC | None


class MessageIn(BaseModel):
    body: str = Field(min_length=1, max_length=1000)

    @field_validator("body")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("message cannot be blank")
        return v


class MessageOut(BaseModel):
    id: UUID
    sender_id: UUID | None
    sender_name: str
    body: str
    created_at: UTC

    @classmethod
    def build(cls, msg: Message, sender: User | None) -> "MessageOut":
        name = sender.display_name if sender else "Gather Agent"
        return cls(id=msg.id, sender_id=msg.sender_id, sender_name=name, body=msg.body, created_at=msg.created_at)


# --- safety ------------------------------------------------------------------------------------
class BlockIn(BaseModel):
    user_id: UUID


class BlockOut(BaseModel):
    user_id: UUID
    display_name: str


class ReportIn(BaseModel):
    reason: Literal["harassment", "unsafe_request", "impersonation", "spam", "threat", "other"]
    details: str | None = Field(None, max_length=1000)
    reported_user_id: UUID | None = None
    proposal_id: UUID | None = None


# --- verification ------------------------------------------------------------------------------
class VerificationOut(BaseModel):
    status: Literal["unverified", "verified_demo", "verified_live"]
    provider: Literal["demo", "stripe"] | None
    is_adult: bool
    verified_at: UTC | None
    demo_available: bool
    stripe_available: bool
    stripe_test_mode: bool


class DemoVerifyIn(BaseModel):
    confirm_adult: StrictBool  # JSON true only; 1/"true" are rejected

    @field_validator("confirm_adult")
    @classmethod
    def _must_confirm(cls, v: bool) -> bool:
        if v is not True:
            raise ValueError("confirm_adult must be true")
        return v


class StripeStartOut(BaseModel):
    url: str


# --- AI plan intake (POST /api/plans/draft) ----------------------------------------------------
class PlanDraftIn(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    timezone_hint: str | None = Field(None, max_length=64)


class PlanDraftOut(BaseModel):
    """A suggested, unsaved PlanIn. Every present field already passed PlanIn's rules; the rest are in `missing`."""

    activity_type: ActivityType | None = None
    title: str | None = None
    goal_text: str
    city: str | None = None
    public_location: str | None = Field(None, max_length=200)
    timezone: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    intent: Intent | None = None
    interests: list[Interest] = Field(default_factory=list)
    group_min: int | None = None
    group_max: int | None = None
    group_only: bool | None = None
    windows: list[WindowIn] = Field(default_factory=list)
    missing: list[str] = Field(default_factory=list)
    notes: str = ""
    mode: Literal["live"] = "live"


class ChatPerson(BaseModel):
    user_id: UUID
    display_name: str
    avatar_url: str | None


class ConversationOut(BaseModel):
    id: UUID
    kind: Literal["group", "direct"]
    title: str
    people: list[ChatPerson]
    last_message: str | None = None
    last_sender_name: str | None = None
    updated_at: UTC


class VenueOptionOut(BaseModel):
    id: UUID
    rank: int
    name: str
    area: str | None
    category: str
    why: str
    reservation_url: str | None
    source_url: str | None
    verified: bool  # True only when it came from grounded web search with a source URL
    votes: int


class VoterOut(BaseModel):
    user_id: UUID
    display_name: str
    voted: bool  # whether they voted, never what they chose


class VenuePollOut(BaseModel):
    status: Literal["not_started", "open", "decided"]
    round: int
    rerolls_left: int
    source: str | None  # grounded|fallback
    options: list[VenueOptionOut]
    my_vote: UUID | None
    voters: list[VoterOut]
    winner_option_id: UUID | None
    proposal_version: int


class VenueVoteIn(BaseModel):
    option_id: UUID


# --- home feed & join requests -----------------------------------------------------------------
class FeedPerson(BaseModel):
    first_name: str
    avatar_url: str | None


class FeedItemOut(BaseModel):
    """An open group as a non-member sees it: no exact time, venue or full names until the host accepts them."""

    proposal_id: UUID
    title: str
    activity_type: str
    city: str
    day: date
    part_of_day: str  # morning|afternoon|evening
    venue_kind: str
    preview: str | None
    host: FeedPerson
    members: list[FeedPerson]
    group_size: int
    spots_left: int
    group_interests: list[str]
    shared_interests: list[str]
    match: int  # matcher fit, 0-100
    reason: str
    free_then: bool | None  # None when the viewer has no plan in that city
    request_status: Literal["pending", "accepted", "declined", "withdrawn"] | None
    welcome: str | None  # Muse-written note once accepted


class JoinIn(BaseModel):
    message: str | None = Field(None, max_length=400)


class OpenIn(BaseModel):
    open: StrictBool


class JoinDraftOut(BaseModel):
    message: str
    mode: Literal["live", "template"]


class JoinRequestOut(BaseModel):
    id: UUID
    user_id: UUID
    display_name: str
    avatar_url: str | None
    bio: str | None
    interests: list[str]
    message: str | None
    match: int | None
    status: str
    created_at: UTC


# --- Supabase Auth --------------------------------------------------------------------------------
class AuthConfigOut(BaseModel):
    """Public sign-in settings for the browser (the Supabase anon key is meant to be public)."""

    supabase_url: str | None
    supabase_anon_key: str | None
    demo_mode: bool


class SupabaseIn(BaseModel):
    access_token: str = Field(min_length=20, max_length=8192)
    display_name: str | None = Field(None, max_length=60)

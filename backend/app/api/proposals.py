from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, Response
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db import get_db
from app.models import Plan, Proposal, ProposalStatus, User
from app.schemas import (
    ApproveIn,
    ConfirmIn,
    FeedbackIn,
    FinalizeIn,
    InvitationOut,
    MessageIn,
    MessageOut,
    ProposalOut,
    RespondIn,
    RunOut,
    VenuePollOut,
    VenueRateIn, LocationIn,
)
from app.security import current_user, not_found
from app.services.outbox import Outbox
from app.services.policy import Policy, conflict
from app.services.proposals import OPEN, Proposals
from app.services.ratelimit import limiter
from app.services.runs import FEEDBACK_HINTS, AgentRuns
from app.services.venue_votes import VenueVoting

router = APIRouter(prefix="/api", tags=["proposals"])


class Ctx:
    """Per-request bundle: the authenticated actor plus the services acting on their behalf."""

    def __init__(
        self,
        background: BackgroundTasks,
        user: User = Depends(current_user),
        db: Session = Depends(get_db),
        s: Settings = Depends(get_settings),
    ):
        self.background, self.user, self.db, self.settings = background, user, db, s
        self.policy, self.proposals, self.runs = Policy(db, s), Proposals(db, s), AgentRuns(db, s)

    def proposal(self, proposal_id: UUID, *roles: str) -> tuple[Proposal, str]:
        return self.policy.visible_proposal(self.user, proposal_id, *roles)

    def view(self, proposal: Proposal, role: str) -> ProposalOut:
        return self.proposals.view(proposal, self.user, role)

    def replan(self, proposal: Proposal, trigger: str, feedback: str | None, mutate=lambda: None) -> RunOut:
        if proposal.status not in OPEN:
            raise conflict("not_open")
        plan = self.db.get(Plan, proposal.plan_id)
        self.runs.check(self.user, plan)
        limiter.hit("agent_run", self.user.id)
        mutate()
        run = self.runs.start(self.user, plan, trigger, FEEDBACK_HINTS.get(feedback, ""), self.proposals.exclusions(plan))
        self.background.add_task(AgentRuns.run_in_background, run.id)
        return RunOut.build(run)


@router.get("/proposals/{proposal_id}", response_model=ProposalOut)
def get_proposal(proposal_id: UUID, ctx: Ctx = Depends()):
    return ctx.view(*ctx.proposal(proposal_id))


@router.post("/proposals/{proposal_id}/members/{user_id}/pass", response_model=RunOut, status_code=202)
def pass_member(proposal_id: UUID, user_id: UUID, body: FeedbackIn, ctx: Ctx = Depends()):
    proposal, _ = ctx.proposal(proposal_id, "owner")
    return ctx.replan(proposal, "pass", body.feedback, lambda: ctx.proposals.pass_member(proposal, user_id))


@router.post("/proposals/{proposal_id}/replan", response_model=RunOut, status_code=202)
def replan(proposal_id: UUID, body: FeedbackIn, ctx: Ctx = Depends()):
    proposal, _ = ctx.proposal(proposal_id, "owner")
    return ctx.replan(proposal, "feedback", body.feedback)


@router.post("/proposals/{proposal_id}/approve-invitations", response_model=ProposalOut)
def approve_invitations(proposal_id: UUID, body: ApproveIn, ctx: Ctx = Depends()):
    proposal, role = ctx.proposal(proposal_id, "owner")
    limiter.hit("approve_invites", ctx.user.id)
    return ctx.view(ctx.proposals.approve(proposal, body.version, body.user_ids), role)


@router.get("/invitations", response_model=list[InvitationOut])
def invitations(ctx: Ctx = Depends()):
    return ctx.proposals.invitations(ctx.user)


@router.post("/proposals/{proposal_id}/respond", response_model=ProposalOut)
def respond(proposal_id: UUID, body: RespondIn, ctx: Ctx = Depends()):
    proposal, role = ctx.proposal(proposal_id, "invitee", "member")
    ctx.proposals.respond(proposal, ctx.user, body.accept)
    if not body.accept:
        ctx.background.add_task(Outbox.process_in_background)
        return ctx.view(proposal, "invitee")  # what they already saw; they lose access from now on
    return ctx.view(proposal, "member")


@router.post("/proposals/{proposal_id}/finalize", response_model=ProposalOut)
def finalize(proposal_id: UUID, body: FinalizeIn, ctx: Ctx = Depends()):
    proposal, role = ctx.proposal(proposal_id, "owner")
    return ctx.view(ctx.proposals.finalize(proposal, body), role)


@router.post("/proposals/{proposal_id}/confirm", response_model=ProposalOut)
def confirm(proposal_id: UUID, body: ConfirmIn, ctx: Ctx = Depends()):
    proposal, role = ctx.proposal(proposal_id, "owner", "member")
    return ctx.view(ctx.proposals.confirm(proposal, ctx.user, body.version), role)


@router.post("/proposals/{proposal_id}/leave", status_code=204)
def leave(proposal_id: UUID, ctx: Ctx = Depends()):
    proposal, _ = ctx.proposal(proposal_id)
    ctx.proposals.leave(proposal, ctx.user)
    return Response(status_code=204)


def chat_room(ctx: Ctx, proposal_id: UUID) -> Proposal:
    proposal, _ = ctx.proposal(proposal_id, "owner", "member")
    if proposal.status != ProposalStatus.confirmed:
        raise not_found()
    return proposal


@router.get("/proposals/{proposal_id}/messages", response_model=list[MessageOut])
def list_messages(proposal_id: UUID, ctx: Ctx = Depends()):
    return ctx.proposals.messages(chat_room(ctx, proposal_id))


@router.post("/proposals/{proposal_id}/messages", response_model=MessageOut, status_code=201)
def post_message(proposal_id: UUID, body: MessageIn, ctx: Ctx = Depends()):
    proposal = chat_room(ctx, proposal_id)
    limiter.hit("message", ctx.user.id)
    return ctx.proposals.post_message(proposal, ctx.user, body.body)


# --- venue vote + calendar ---------------------------------------------------------------------
def voting(ctx: Ctx) -> VenueVoting:
    return VenueVoting(ctx.db, ctx.settings)


@router.get("/proposals/{proposal_id}/venue-poll", response_model=VenuePollOut)
def get_venue_poll(proposal_id: UUID, ctx: Ctx = Depends()):
    proposal, _ = ctx.proposal(proposal_id, "owner", "member")
    return voting(ctx).view(proposal, ctx.user)


@router.post("/proposals/{proposal_id}/venue-poll", response_model=VenuePollOut)
def start_venue_poll(proposal_id: UUID, ctx: Ctx = Depends()):
    proposal, _ = ctx.proposal(proposal_id, "owner", "member")
    v = voting(ctx)
    if v.poll(proposal) is None:
        limiter.hit("venue_agent", ctx.user.id)
    v.start(proposal)
    return v.view(proposal, ctx.user)


@router.post("/proposals/{proposal_id}/venue-poll/rate", response_model=VenuePollOut)
def rate_venue(proposal_id: UUID, body: VenueRateIn, ctx: Ctx = Depends()):
    proposal, _ = ctx.proposal(proposal_id, "owner", "member")
    limiter.hit("venue_vote", ctx.user.id)
    v = voting(ctx)
    v.rate(proposal, ctx.user, body.option_id, body.score)
    return v.view(proposal, ctx.user)


@router.put("/proposals/{proposal_id}/location", response_model=VenuePollOut)
def share_location(proposal_id: UUID, body: LocationIn, ctx: Ctx = Depends()):
    """Opt in: show my location (rounded to ~100 m) to this group's participants and use it to find fair places."""
    proposal, _ = ctx.proposal(proposal_id, "owner", "member")
    v = voting(ctx)
    v.share_location(proposal, ctx.user, body.latitude, body.longitude)
    return v.view(proposal, ctx.user)


@router.delete("/proposals/{proposal_id}/location", response_model=VenuePollOut)
def stop_sharing_location(proposal_id: UUID, ctx: Ctx = Depends()):
    proposal, _ = ctx.proposal(proposal_id, "owner", "member")
    v = voting(ctx)
    v.stop_sharing(proposal, ctx.user)
    return v.view(proposal, ctx.user)


@router.post("/proposals/{proposal_id}/venue-poll/reroll", response_model=VenuePollOut)
def reroll_venue_poll(proposal_id: UUID, ctx: Ctx = Depends()):
    proposal, _ = ctx.proposal(proposal_id, "owner", "member")
    limiter.hit("venue_agent", ctx.user.id)
    v = voting(ctx)
    v.reroll(proposal)
    return v.view(proposal, ctx.user)


@router.get("/proposals/{proposal_id}/calendar.ics")
def calendar_invite(proposal_id: UUID, ctx: Ctx = Depends()):
    from app.services.calendar import ics
    proposal = chat_room(ctx, proposal_id)  # confirmed + participant, else 404
    body = ics(proposal, ctx.db.get(Plan, proposal.plan_id), ctx.settings.public_base_url)
    return Response(body, media_type="text/calendar; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="ingather-{proposal.id}.ics"'})

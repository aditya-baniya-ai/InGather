"""Group venue vote. Fits the proposal state machine like this:

    invites_pending (nobody still `invited`, >= 1 accepted) or awaiting_final
        -> any participant starts the poll (venue agent suggests 3 options)
        -> every participant (owner + accepted) casts / changes one vote
        -> last vote decides: winner = most votes, ties -> agent's higher rank
        -> winner becomes the proposal venue, version bumps (old confirmations void), status = awaiting_final
        -> the existing per-version final confirmation applies unchanged.

"None of these work" re-rolls once per proposal (new options, votes reset). A decided poll is closed.
"""

from collections import Counter
from datetime import timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.muse import MuseClient
from app.ai.venues import VenueAgent, VenueRequest
from app.config import Settings
from app.models import MemberStatus, Plan, Proposal, ProposalStatus, User, VenueOption, VenuePoll, VenueVote
from app.services.clock import as_utc
from app.services.geo import midpoint
from app.services.policy import conflict
from app.services.proposals import Proposals

MAX_REROLLS = 1


def participants(proposal: Proposal) -> list:
    return [m for m in proposal.members if m.is_initiator or m.status == MemberStatus.accepted]


def pick_winner(options: list[VenueOption], votes: list[VenueVote]) -> VenueOption | None:
    """Most votes wins; a tie goes to the option the venue agent ranked highest (lowest rank)."""
    if not options:
        return None
    counts = Counter(v.option_id for v in votes)
    return min(options, key=lambda o: (-counts.get(o.id, 0), o.rank))


class VenueVoting:
    def __init__(self, db: Session, settings: Settings, agent: VenueAgent | None = None):
        self.db, self.settings = db, settings
        self.agent = agent or VenueAgent(MuseClient(settings) if settings.ai_live else None, settings)

    # --- queries -------------------------------------------------------------------------------
    def poll(self, proposal: Proposal) -> VenuePoll | None:
        return self.db.scalar(select(VenuePoll).where(VenuePoll.proposal_id == proposal.id))

    def _current(self, poll: VenuePoll) -> list[VenueOption]:
        return [o for o in poll.options if o.round == poll.round]

    def _votes(self, poll: VenuePoll, proposal: Proposal) -> list[VenueVote]:
        ids = {m.user_id for m in participants(proposal)}
        return [v for v in self.db.scalars(select(VenueVote).where(VenueVote.poll_id == poll.id)) if v.user_id in ids]

    # --- actions -------------------------------------------------------------------------------
    def _check_open(self, proposal: Proposal) -> None:
        if self.db.get(Plan, proposal.plan_id).status != "active":
            raise conflict("plan_inactive")
        others = [m for m in proposal.members if not m.is_initiator]
        if proposal.status not in (ProposalStatus.invites_pending, ProposalStatus.awaiting_final):
            raise conflict("not_open")
        if any(m.status == MemberStatus.invited for m in others):
            raise conflict("invites_pending")
        if not any(m.status == MemberStatus.accepted for m in others):
            raise conflict("no_accepted_members")
        if proposal.start_at is None:
            raise conflict("invalid_time")

    def start(self, proposal: Proposal) -> VenuePoll:
        self._check_open(proposal)
        poll = self.poll(proposal)
        if poll is not None:
            return poll  # idempotent: someone already started it
        poll = VenuePoll(proposal_id=proposal.id, round=1, rerolls_used=0, status="open")
        self.db.add(poll)
        self._fill(poll, proposal)
        self.db.commit()
        return poll

    def vote(self, proposal: Proposal, user: User, option_id: UUID) -> VenuePoll:
        poll = self._open_poll(proposal)
        if option_id not in {o.id for o in self._current(poll)}:
            raise conflict("option_not_found")
        vote = self.db.scalar(select(VenueVote).where(VenueVote.poll_id == poll.id, VenueVote.user_id == user.id))
        if vote is None:
            self.db.add(VenueVote(poll_id=poll.id, user_id=user.id, option_id=option_id))
        else:
            vote.option_id = option_id  # change of mind
        self.db.flush()
        self._maybe_decide(poll, proposal)
        self.db.commit()
        return poll

    def reroll(self, proposal: Proposal) -> VenuePoll:
        poll = self._open_poll(proposal)
        if poll.rerolls_used >= MAX_REROLLS:
            raise conflict("reroll_used")
        poll.rerolls_used += 1
        poll.round += 1
        for v in self.db.scalars(select(VenueVote).where(VenueVote.poll_id == poll.id)):
            self.db.delete(v)
        self._fill(poll, proposal, avoid={o.name.casefold() for o in poll.options})
        self.db.commit()
        return poll

    # --- internals -----------------------------------------------------------------------------
    def _open_poll(self, proposal: Proposal) -> VenuePoll:
        poll = self.poll(proposal)
        if poll is None:
            raise conflict("no_venue_poll")
        if poll.status != "open":
            raise conflict("venue_poll_closed")
        self._check_open(proposal)
        return poll

    def request_for(self, proposal: Proposal) -> VenueRequest:
        plan = self.db.get(Plan, proposal.plan_id)
        people = [m.user for m in participants(proposal)]
        mid = midpoint([(u.home_lat, u.home_lng) for u in people if u.home_lat is not None and u.home_lng is not None])
        shared = set(people[0].interests or []) if people else set()
        for u in people[1:]:
            shared &= set(u.interests or [])
        interests = sorted(shared) or sorted({i for u in people for i in (u.interests or [])})[:4]
        local = as_utc(proposal.start_at).astimezone(ZoneInfo(plan.timezone))
        end = as_utc(proposal.end_at).astimezone(ZoneInfo(plan.timezone)) if proposal.end_at else local + timedelta(minutes=90)
        when = f"{local:%A %Y-%m-%d %H:%M}-{end:%H:%M} ({plan.timezone})"
        return VenueRequest(city=plan.city, midpoint=mid, local_time=when, activity=proposal.activity_title, interests=interests)

    def _fill(self, poll: VenuePoll, proposal: Proposal, avoid: set[str] = frozenset()) -> None:
        result = self.agent.suggest(self.request_for(proposal))
        fresh = [o for o in result.options if o["name"].casefold() not in avoid or not o["verified"]]
        poll.source = result.source
        for rank, o in enumerate(fresh[:3], start=1):
            poll.options.append(VenueOption(round=poll.round, rank=rank, **o))
        self.db.flush()

    def _maybe_decide(self, poll: VenuePoll, proposal: Proposal) -> None:
        people = {m.user_id for m in participants(proposal)}
        votes = self._votes(poll, proposal)
        if {v.user_id for v in votes} != people:
            return
        winner = pick_winner(self._current(poll), votes)
        poll.status, poll.winner_option_id = "decided", winner.id
        proposal.venue_label = winner.name
        proposal.venue_category = winner.category
        proposal.venue_verified = winner.verified
        proposal.venue_details = {
            "name": winner.name, "address": winner.area or "", "category": winner.category,
            "source": "Muse Spark web search" if winner.verified else "suggestion, not verified",
            "source_url": winner.source_url, "reservation_url": winner.reservation_url,
        }
        Proposals._bump(proposal)  # everyone re-confirms the exact new version
        proposal.status = ProposalStatus.awaiting_final

    def view(self, proposal: Proposal, viewer: User) -> dict:
        poll = self.poll(proposal)
        people = participants(proposal)
        if poll is None:
            return {"status": "not_started", "round": 0, "rerolls_left": MAX_REROLLS, "source": None, "options": [],
                    "my_vote": None, "voters": [{"user_id": m.user_id, "display_name": m.user.display_name, "voted": False} for m in people],
                    "winner_option_id": None, "proposal_version": proposal.version}
        votes = self._votes(poll, proposal)
        counts = Counter(v.option_id for v in votes)
        voted = {v.user_id for v in votes}
        mine = next((v.option_id for v in votes if v.user_id == viewer.id), None)
        return {
            "status": poll.status, "round": poll.round, "rerolls_left": MAX_REROLLS - poll.rerolls_used, "source": poll.source,
            "options": [{"id": o.id, "rank": o.rank, "name": o.name, "area": o.area, "category": o.category, "why": o.why,
                         "reservation_url": o.reservation_url, "source_url": o.source_url, "verified": o.verified,
                         "votes": counts.get(o.id, 0)} for o in self._current(poll)],
            "my_vote": mine,
            "voters": [{"user_id": m.user_id, "display_name": m.user.display_name, "voted": m.user_id in voted} for m in people],
            "winner_option_id": poll.winner_option_id, "proposal_version": proposal.version,
        }

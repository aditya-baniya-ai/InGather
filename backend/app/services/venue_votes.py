"""Group venue rating. Fits the proposal state machine like this:

    invites_pending (nobody still `invited`, >= 1 accepted) or awaiting_final
        -> any participant asks for places (the Muse venue agent suggests 3 near the middle of the group)
        -> every participant (owner + accepted) rates every option from 1 to 10, and can change a score
        -> once everyone has rated everything: winner = highest average, ties -> the agent's higher rank
        -> the winner becomes the proposal venue, version bumps (old confirmations void), status = awaiting_final
        -> the existing per-version final confirmation applies unchanged.

"Find more places" asks for 3 new ones (never the same names) up to MAX_REROLLS times; ratings reset. Participants may
share their location with the group (rounded to ~100 m): it is shown on the group map and moves the search midpoint.
"""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.muse import MuseClient
from app.ai.venues import VenueAgent, VenueRequest
from app.config import Settings
from app.models import MeetupLocation, MemberStatus, Plan, Proposal, ProposalStatus, User, VenueOption, VenuePoll, VenueRating, now
from app.services import gplaces
from app.services.clock import as_utc
from app.services.geo import coarse, geocode_place, midpoint
from app.services.policy import conflict
from app.services.proposals import Proposals

MAX_REROLLS = 3
SCORES = range(1, 11)


def participants(proposal: Proposal) -> list:
    return [m for m in proposal.members if m.is_initiator or m.status == MemberStatus.accepted]


def averages(options: list[VenueOption], ratings: list[VenueRating]) -> dict[UUID, float]:
    by: dict[UUID, list[int]] = {}
    for r in ratings:
        by.setdefault(r.option_id, []).append(r.score)
    return {o.id: sum(by[o.id]) / len(by[o.id]) for o in options if by.get(o.id)}


def pick_winner(options: list[VenueOption], ratings: list[VenueRating]) -> VenueOption | None:
    """Highest average score wins; a tie goes to the option the venue agent ranked highest (lowest rank)."""
    if not options:
        return None
    avg = averages(options, ratings)
    return min(options, key=lambda o: (-avg.get(o.id, 0.0), o.rank))


MAX_PIN_KM = 50  # a geocoded pin farther than this from the group is the wrong place


def place_out(o: VenueOption) -> dict | None:
    """Google details for the client. Photos go through our own endpoint (no API key in the browser)."""
    p = o.place
    if not p:
        return None
    keep = ("type", "rating", "rating_count", "price", "open_now", "hours", "phone", "website", "maps_url", "summary")
    return {**{k: p.get(k) for k in keep}, "hours": p.get("hours") or [],
            "photos": [{"url": f"/api/venue-photos/{o.id}/{i}", "author": ph.get("author")} for i, ph in enumerate(p.get("photos") or [])]}


class VenueVoting:
    def __init__(self, db: Session, settings: Settings, agent: VenueAgent | None = None):
        self.db, self.settings = db, settings
        self.agent = agent or VenueAgent(MuseClient(settings) if settings.ai_live else None, settings)

    # --- queries -------------------------------------------------------------------------------
    def poll(self, proposal: Proposal) -> VenuePoll | None:
        return self.db.scalar(select(VenuePoll).where(VenuePoll.proposal_id == proposal.id))

    def _current(self, poll: VenuePoll) -> list[VenueOption]:
        return [o for o in poll.options if o.round == poll.round]

    def _ratings(self, poll: VenuePoll, proposal: Proposal) -> list[VenueRating]:
        """Current-round ratings from people still in the group."""
        ids, current = {m.user_id for m in participants(proposal)}, {o.id for o in self._current(poll)}
        q = select(VenueRating).where(VenueRating.poll_id == poll.id)
        return [r for r in self.db.scalars(q) if r.user_id in ids and r.option_id in current]

    def locations(self, proposal: Proposal) -> list[MeetupLocation]:
        ids = {m.user_id for m in participants(proposal)}
        return [x for x in self.db.scalars(select(MeetupLocation).where(MeetupLocation.proposal_id == proposal.id)) if x.user_id in ids]

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

    def rate(self, proposal: Proposal, user: User, option_id: UUID, score: int) -> VenuePoll:
        poll = self._open_poll(proposal)
        if option_id not in {o.id for o in self._current(poll)}:
            raise conflict("option_not_found")
        if score not in SCORES:
            raise conflict("invalid_score")
        q = select(VenueRating).where(VenueRating.poll_id == poll.id, VenueRating.user_id == user.id, VenueRating.option_id == option_id)
        rating = self.db.scalar(q)
        if rating is None:
            self.db.add(VenueRating(poll_id=poll.id, user_id=user.id, option_id=option_id, score=score))
        else:
            rating.score = score  # change of mind
        self.db.flush()
        self._maybe_decide(poll, proposal)
        self.db.commit()
        return poll

    def share_location(self, proposal: Proposal, user: User, lat: float, lng: float) -> None:
        if not (-90 <= lat <= 90 and -180 <= lng <= 180):
            raise conflict("invalid_location")
        lat, lng = round(lat, 3), round(lng, 3)  # ~100 m: enough to find fair places, not a doorstep
        row = self.db.scalar(select(MeetupLocation).where(MeetupLocation.proposal_id == proposal.id, MeetupLocation.user_id == user.id))
        if row is None:
            self.db.add(MeetupLocation(proposal_id=proposal.id, user_id=user.id, latitude=lat, longitude=lng))
        else:
            row.latitude, row.longitude, row.updated_at = lat, lng, now()
        self.db.commit()

    def stop_sharing(self, proposal: Proposal, user: User) -> None:
        row = self.db.scalar(select(MeetupLocation).where(MeetupLocation.proposal_id == proposal.id, MeetupLocation.user_id == user.id))
        if row is not None:
            self.db.delete(row)
            self.db.commit()

    def reroll(self, proposal: Proposal) -> VenuePoll:
        poll = self._open_poll(proposal)
        if poll.rerolls_used >= MAX_REROLLS:
            raise conflict("reroll_used")
        poll.rerolls_used += 1
        poll.round += 1  # earlier rounds' ratings stay stored but no longer count
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
        # The middle of everyone: a shared meetup location if they gave one, else their coarse home area.
        shared = {x.user_id: coarse(x.latitude, x.longitude) for x in self.locations(proposal)}
        points = [shared.get(u.id) or ((u.home_lat, u.home_lng) if u.home_lat is not None and u.home_lng is not None else None) for u in people]
        mid = midpoint([p for p in points if p])
        common = set(people[0].interests or []) if people else set()
        for u in people[1:]:
            common &= set(u.interests or [])
        interests = sorted(common) or sorted({i for u in people for i in (u.interests or [])})[:4]
        local = as_utc(proposal.start_at).astimezone(ZoneInfo(plan.timezone))
        end = as_utc(proposal.end_at).astimezone(ZoneInfo(plan.timezone)) if proposal.end_at else local + timedelta(minutes=90)
        when = f"{local:%A %Y-%m-%d %H:%M}-{end:%H:%M} ({plan.timezone})"
        return VenueRequest(city=plan.city, midpoint=mid, local_time=when, activity=proposal.activity_title, interests=interests)

    def _fill(self, poll: VenuePoll, proposal: Proposal, avoid: set[str] = frozenset()) -> None:
        req = self.request_for(proposal)
        result = self.agent.suggest(req, avoid)
        fresh = [o for o in result.options if o["name"].casefold() not in avoid or not o["verified"]][:3]
        poll.source = result.source
        city = self.db.get(Plan, proposal.plan_id).city
        todo = [i for i, o in enumerate(fresh) if o["verified"] and not o.get("place")]
        key = self.settings.google_maps_api_key
        if key and todo:  # web-search picks: exact pin, photos, rating and hours from Google, looked up in parallel
            with ThreadPoolExecutor(max_workers=3) as pool:
                found = list(pool.map(lambda i: gplaces.lookup(fresh[i]["name"], fresh[i]["area"], city, key, req.midpoint), todo))
            for i, hit in zip(todo, found):
                if hit:
                    fresh[i] = {**fresh[i], "latitude": hit["lat"], "longitude": hit["lng"], "area": fresh[i]["area"] or hit["address"], "place": hit}
        for i, o in enumerate(fresh):
            if o["verified"] and o.get("latitude") is None:  # no key, or Google didn't know it: pin it from OpenStreetMap
                pin = self._geocode(o, city, req.midpoint)
                if pin:
                    fresh[i] = {**o, "latitude": pin[0], "longitude": pin[1]}
        for rank, o in enumerate(fresh, start=1):
            poll.options.append(VenueOption(round=poll.round, rank=rank, **o))
        self.db.flush()

    def _geocode(self, o: dict, city: str, near: tuple[float, float] | None) -> tuple[float, float] | None:
        """Try the full address, then the street address alone, then name + city; reject pins far from the group."""
        queries = [f"{o['name']}, {o['area']}" if o.get("area") else None, o.get("area"), f"{o['name']}, {city}"]
        for q in dict.fromkeys(q for q in queries if q):
            pin = geocode_place(q, self.settings.venue_search_enabled)
            if pin and (not near or gplaces.km(near, pin) <= MAX_PIN_KM):
                return pin
        return None

    def _maybe_decide(self, poll: VenuePoll, proposal: Proposal) -> None:
        people = {m.user_id for m in participants(proposal)}
        options = self._current(poll)
        rated = {(r.user_id, r.option_id) for r in self._ratings(poll, proposal)}
        if not options or any((u, o.id) not in rated for u in people for o in options):
            return  # someone still has a place to rate
        winner = pick_winner(options, self._ratings(poll, proposal))
        poll.status, poll.winner_option_id = "decided", winner.id
        proposal.venue_label = winner.name
        proposal.venue_category = winner.category
        proposal.venue_verified = winner.verified
        proposal.venue_details = {
            "name": winner.name, "address": winner.area or "", "category": winner.category,
            "source": "Muse Spark web search" if winner.verified else "suggestion, not verified",
            "source_url": winner.source_url, "reservation_url": winner.reservation_url,
            **({"latitude": winner.latitude, "longitude": winner.longitude, "distance_m": 0} if winner.latitude is not None else {}),
        }
        Proposals._bump(proposal)  # everyone re-confirms the exact new version
        proposal.status = ProposalStatus.awaiting_final

    def view(self, proposal: Proposal, viewer: User) -> dict:
        poll = self.poll(proposal)
        people = participants(proposal)
        where = {x.user_id: x for x in self.locations(proposal)}
        located = [{"user_id": m.user_id, "display_name": m.user.display_name, "avatar_url": m.user.avatar_url,
                    "latitude": where[m.user_id].latitude, "longitude": where[m.user_id].longitude, "is_me": m.user_id == viewer.id}
                   for m in people if m.user_id in where]
        base = {"people": located, "i_shared_location": viewer.id in where, "proposal_version": proposal.version}
        if poll is None:
            return {**base, "status": "not_started", "round": 0, "rerolls_left": MAX_REROLLS, "source": None, "options": [],
                    "voters": [{"user_id": m.user_id, "display_name": m.user.display_name, "voted": False, "rated": 0} for m in people],
                    "winner_option_id": None}
        options, ratings = self._current(poll), self._ratings(poll, proposal)
        avg = averages(options, ratings)
        mine = {r.option_id: r.score for r in ratings if r.user_id == viewer.id}
        count = {o.id: sum(1 for r in ratings if r.option_id == o.id) for o in options}
        rated = {m.user_id: sum(1 for r in ratings if r.user_id == m.user_id) for m in people}
        return {
            **base, "status": poll.status, "round": poll.round, "rerolls_left": MAX_REROLLS - poll.rerolls_used, "source": poll.source,
            "options": [{"id": o.id, "rank": o.rank, "name": o.name, "area": o.area, "category": o.category, "why": o.why,
                         "description": o.description, "latitude": o.latitude, "longitude": o.longitude, "image_url": o.image_url,
                         "place": place_out(o),
                         "reservation_url": o.reservation_url, "source_url": o.source_url, "verified": o.verified,
                         "average": round(avg[o.id], 1) if o.id in avg else None, "ratings": count[o.id], "my_score": mine.get(o.id)}
                        for o in options],
            "voters": [{"user_id": m.user_id, "display_name": m.user.display_name, "voted": rated[m.user_id] >= len(options),
                        "rated": rated[m.user_id]} for m in people],
            "winner_option_id": poll.winner_option_id,
        }

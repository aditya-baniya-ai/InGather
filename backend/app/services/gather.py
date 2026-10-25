"""Gather engine: finds one small group for a plan with the InGather matcher (an ML model, app/ml) and plain code.
No LLM is involved, so a run costs no tokens and gives the same answer for the same data.

    matcher    eligible people (hard filters) -> each scored by the model for fit with the owner's plan
    scheduler  best group: owner fit + how well the people fit each other + a shared free window of 60+ minutes
    venue      nearest public place of a fitting kind (OpenStreetMap lookup), or a generic public suggestion
    checks     public venue, time inside the shared window, group size, nobody excluded or blocked
    -> Proposals.save_agent_result re-validates everything and stores a proposal the owner must approve.

Every step writes a timeline row. Replans (a pass, a decline, owner feedback) run the same pipeline, keep the
people still on the proposal and fill only the open slots.
"""

import itertools
import logging
import re
import threading
import uuid
from datetime import datetime, timedelta, timezone
from typing import get_args
from zoneinfo import ZoneInfo

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings, get_settings
from app.db import SessionLocal
from app.ml.interests import ALIASES, normalize
from app.models import AgentEvent, AgentRun, Block, MemberStatus, Plan, PlanStatus, Proposal, ProposalStatus, RunStatus, User, now
from app.schemas import VenueCategory
from app.services.clock import Interval, intersect, minutes
from app.services.matching import MIN_GROUP_MINUTES, Fit, Matching
from app.services.runs import FEEDBACK_HINTS

log = logging.getLogger("ingather.gather")

PUBLIC_VENUE_CATEGORIES: tuple[str, ...] = get_args(VenueCategory)
_PRIVATE_VENUE = re.compile(
    r"\b(home|house|apartment|apt|flat|condo|dorm|hotel|motel|hostel|airbnb|room|suite|my place|your place|their place|residence|bedroom)\b",
    re.I,
)
OPEN_PROPOSAL = (ProposalStatus.pending_owner, ProposalStatus.invites_pending, ProposalStatus.awaiting_final)
TRIGGER_EVENTS = {
    "user": "Started by you",
    "pass": "Replanning: you passed on a suggested person (they won't be told)",
    "decline": "Replanning: an invitation was declined",
    "feedback": "Replanning with your feedback",
}
SHORTLIST = 10  # best-scoring people the group search considers
SLOT = timedelta(minutes=90)
# Public place kinds that suit each activity, best first. Venue lookup results are already sorted by distance.
VENUES = {
    "coffee": ("cafe", "food_hall", "restaurant"),
    "conference": ("cafe", "food_hall", "restaurant"),
    "hackathon": ("food_hall", "restaurant", "cafe"),
    "study": ("library", "cafe"),
    "travel": ("museum", "cafe", "park", "restaurant"),
    "event": ("food_hall", "restaurant", "cafe"),
}
GENERIC = {
    "cafe": "A public café in {city}", "food_hall": "A food hall in {city}", "restaurant": "A casual restaurant in {city}",
    "library": "A public library in {city}", "museum": "A museum in {city}", "park": "A public park in {city}",
    "conference_venue": "The public lobby café at the conference venue", "public_venue": "A public place in {city}",
}
TITLES = {
    "cafe": "Coffee", "food_hall": "Food hall meetup", "restaurant": "Dinner", "library": "Study session",
    "museum": "Museum visit", "park": "Walk in the park", "conference_venue": "Coffee at the venue", "public_venue": "Meetup",
}
_STOP = {"people", "person", "someone", "free", "want", "looking", "after", "group", "find", "meet", "with", "some", "near", "into"}


def aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def plan_zone(plan: Plan) -> ZoneInfo:
    try:
        return ZoneInfo(plan.timezone)
    except Exception:
        return ZoneInfo("UTC")


class StepError(Exception):
    """Ends the run without a proposal. `code` is stored as the run error; the message is shown to the owner."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class EventLog:
    """Appends owner-visible timeline rows, each in its own short-lived Session, so pollers see progress live."""

    def __init__(self, db: Session, run: AgentRun):
        self.run_id = run.id
        self._sessions = sessionmaker(bind=db.get_bind(), expire_on_commit=False)
        self._lock = threading.Lock()
        self.seq = db.scalar(select(func.max(AgentEvent.seq)).where(AgentEvent.run_id == run.id)) or 0

    def add(self, kind: str, summary: str, tool_name: str | None = None, agent: str | None = None) -> None:
        with self._lock, self._sessions() as s:
            self.seq += 1
            s.add(AgentEvent(run_id=self.run_id, seq=self.seq, kind=kind, agent=agent, tool_name=tool_name, summary=summary[:400]))
            s.commit()


def start_run(db: Session, owner: User, plan: Plan, trigger: str, goal: str = "", excluded: set[uuid.UUID] = ()) -> AgentRun:
    """Create a running AgentRun (caller schedules run_in_background). Authorization was checked by the caller;
    ownership is re-checked here because the run acts in the owner's scope."""
    if plan.owner_id != owner.id:
        raise PermissionError("not the plan owner")
    run = AgentRun(
        plan_id=plan.id, owner_id=owner.id, trigger=trigger if trigger in TRIGGER_EVENTS else "user",
        mode="ml", model=Matching(db, get_settings()).matcher.version, status=RunStatus.running,
        goal=(goal or "")[:2000], excluded_user_ids=sorted({str(x) for x in excluded}),
    )
    db.add(run)
    db.flush()
    db.add(AgentEvent(run_id=run.id, seq=1, kind="system", agent="gather", tool_name=None, summary=TRIGGER_EVENTS[run.trigger]))
    db.commit()
    return run


def run_in_background(run_id: uuid.UUID) -> None:
    """Entry point for BackgroundTasks / outbox workers. Opens its own Session."""
    try:
        with SessionLocal() as db:
            GatherEngine(db, get_settings()).run(run_id)
    except Exception as exc:
        log.warning("background gather run %s crashed: %s", run_id, type(exc).__name__)


class GatherEngine:
    def __init__(self, db: Session, settings: Settings, matching: Matching | None = None):
        self.db, self.settings = db, settings
        self.matching = matching or Matching(db, settings)

    def run(self, run_id: uuid.UUID) -> None:
        run = self.db.get(AgentRun, run_id)
        if run is None or run.status != RunStatus.running:
            return
        plan, owner = self.db.get(Plan, run.plan_id), self.db.get(User, run.owner_id)
        events = EventLog(self.db, run)
        try:
            if plan is None or owner is None or plan.status != PlanStatus.active:
                raise StepError("plan_inactive", "This plan is not active, so nothing was searched.")
            Run(self, run, plan, owner, events).go()
        except StepError as e:
            self.db.rollback()
            self._finish(run, events, False, str(e), e.code)
        except Exception as exc:  # never leak stack traces into the run
            self.db.rollback()
            log.warning("gather run %s failed: %s", run_id, type(exc).__name__)
            self._finish(run, events, False, "Something went wrong while finding a group.", "internal_error")

    def _finish(self, run: AgentRun, events: EventLog, ok: bool, summary: str, error: str | None = None) -> None:
        run.status = RunStatus.completed if ok else RunStatus.failed
        run.summary, run.error, run.finished_at = summary[:2000], (error or None) and error[:300], now()
        self.db.commit()
        events.add(
            "system",
            "Proposal ready for your review — nobody has been invited" if ok else f"Run ended without a proposal ({run.error})",
            agent="gather",
        )


class Run:
    """One pass of the pipeline for one AgentRun."""

    def __init__(self, engine: GatherEngine, run: AgentRun, plan: Plan, owner: User, events: EventLog):
        self.engine, self.db, self.settings, self.matching = engine, engine.db, engine.settings, engine.matching
        self.run, self.plan, self.owner, self.events = run, plan, owner, events
        self.tz = plan_zone(plan)
        self.prefs = {k for k, hint in FEEDBACK_HINTS.items() if hint in (run.goal or "")}
        self.previous = self.open_proposal()

    def go(self) -> None:
        self.events.add("system", f"InGather matcher ({self.matching.matcher.version}): a machine-learning model trained on real "
                        "Meetup.com group data. No AI chat model is used to pick people.", agent="gather")
        fits = self.match()
        picks, window = self.schedule(fits)
        venue = self.venue()
        start, end = self.slot(window)
        self.check(picks, start, end, venue)
        self.db.refresh(self.plan)
        if self.plan.status != PlanStatus.active:
            raise StepError("plan_inactive", "Plan was paused, so nothing was proposed.")
        self.propose(picks, start, end, venue)

    # ----- shared state -----
    def open_proposal(self) -> Proposal | None:
        return self.db.scalars(
            select(Proposal).where(Proposal.plan_id == self.plan.id, Proposal.status.in_(OPEN_PROPOSAL)).order_by(Proposal.created_at.desc())
        ).first()

    def current_member_ids(self) -> list[uuid.UUID]:
        """People still on the open proposal (suggested/invited/accepted); they stay in the group on a replan."""
        ok = (MemberStatus.suggested, MemberStatus.invited, MemberStatus.accepted)
        return [m.user_id for m in (self.previous.members if self.previous else []) if not m.is_initiator and m.status in ok]

    def excluded_ids(self) -> set[uuid.UUID]:
        out = {self.owner.id, *self.current_member_ids()}
        for raw in self.run.excluded_user_ids or []:
            try:
                out.add(uuid.UUID(str(raw)))
            except ValueError:
                pass
        gone = (MemberStatus.passed, MemberStatus.declined, MemberStatus.removed, MemberStatus.expired)
        out.update(m.user_id for m in (self.previous.members if self.previous else []) if m.status in gone)
        return out

    def pick_bounds(self) -> tuple[int, int]:
        """How many NEW people to suggest (group size counts the owner and people already on the proposal)."""
        have = 1 + len(self.current_member_ids())
        hi = max(0, min(self.plan.group_max, 4) - have)
        lo = max(1, self.plan.group_min - have)
        if self.plan.group_only and have + lo < 3:
            lo = 3 - have
        return min(lo, hi), hi

    def blocked(self, other: uuid.UUID) -> bool:
        me = self.owner.id
        return self.db.scalar(select(Block.id).where(or_(
            (Block.blocker_id == me) & (Block.blocked_id == other), (Block.blocker_id == other) & (Block.blocked_id == me),
        ))) is not None

    def label(self, a: datetime, b: datetime) -> str:
        la, lb = aware(a).astimezone(self.tz), aware(b).astimezone(self.tz)
        return f"{la:%a %b %d, %I:%M %p}–{lb:%I:%M %p} {la.tzname()}"

    # ----- 1. matcher -----
    def note_interests(self) -> list[str]:
        """Interests named in the owner's note for this run ("people into jazz"), matched against the vocabulary."""
        if not self.run.goal or self.run.trigger != "user":
            return []
        space, words = self.matching.matcher.space, re.findall(r"[a-z][a-z&+-]*", self.run.goal.lower())
        grams = [" ".join(words[i:i + n]) for n in (2, 1) for i in range(len(words) - n + 1)]
        mine = {space.key(t) for t in self.plan.interests}
        out = []
        for g in grams:
            if g in _STOP or len(g) < 3 or (g not in ALIASES and len(g) < 4) or not space.rows(g):
                continue
            k = space.key(g)
            if k not in mine and all(space.key(o) != k for o in out):
                out.append(g)
        return out[:4]

    def match(self) -> list[Fit]:
        extra = self.note_interests()
        if extra:
            self.events.add("system", f"Also matching on interests from your note: {', '.join(extra)}", agent="matcher")
        fits = [f for f in self.matching.fits(self.plan, self.excluded_ids(), extra) if not self.blocked(uuid.UUID(f.preview.user_id))]
        self.events.add("tool", f"Found {len(fits)} eligible {'person' if len(fits) == 1 else 'people'} in {self.plan.city} "
                        "(opted in, verified, free when you are, not blocked)", "find_eligible_candidates", "matcher")
        if not fits:
            raise StepError("no_suitable_group", "No compatible people are available for this plan right now.")
        if "prefer_same_event" in self.prefs:
            fits.sort(key=lambda f: (not f.same_event, -f.preview.score))
        top = fits[0].preview
        self.events.add("tool", f"Scored {len(fits)} {'person' if len(fits) == 1 else 'people'} with the matcher: best fit "
                        f"{top.display_name} ({round(top.score * 100)}% match)", "score_candidates", "matcher")
        return fits[:SHORTLIST]

    # ----- 2. scheduler -----
    def schedule(self, fits: list[Fit]) -> tuple[list[Fit], Interval]:
        lo, hi = self.pick_bounds()
        if hi < 1:
            raise StepError("no_suitable_group", "The group is already full.")
        base = [(aware(s), aware(e)) for s, e in self.matching.group_availability(self.plan, self.current_member_ids()).windows]
        pair = self.matching.cohesion(self.plan, [uuid.UUID(f.preview.user_id) for f in fits]) if hi > 1 else {}
        size_bonus = 1.0 if "prefer_group" in self.prefs else 0.03  # asked for a bigger group: size comes first
        time_weight = 0.04 if "schedule" in self.prefs else 0.02
        best, checked = None, 0
        for k in range(hi, lo - 1, -1):
            for combo in itertools.combinations(fits, k):
                checked += 1
                common = base
                for f in combo:
                    common = intersect(common, f.windows)
                windows = [w for w in common if minutes([w]) >= MIN_GROUP_MINUTES]
                if not windows:
                    continue
                fit = sum(f.preview.score for f in combo) / k
                ids = [uuid.UUID(f.preview.user_id) for f in combo]
                links = [pair.get((a, b), pair.get((b, a), 0.0)) for a, b in itertools.combinations(ids, 2)]
                together = sum(links) / len(links) if links else fit
                longest = max(minutes([w]) for w in windows) / 60
                utility = 0.7 * fit + 0.3 * together + size_bonus * (k - lo) + time_weight * min(longest, 3)
                if best is None or utility > best[0]:
                    best = (utility, list(combo), windows, together)
        if best is None:
            self.events.add("tool", f"Checked {checked} possible groups: none share an hour of free time", "check_group_availability", "scheduler")
            raise StepError("no_suitable_group", "No group with shared free time was found right now.")
        _, picks, windows, together = best
        window = self.choose_window(windows)
        self.events.add("tool", f"Checked {checked} possible groups: best is {len(picks) + 1 + len(self.current_member_ids())} people, "
                        f"free together {self.label(*window)}", "check_group_availability", "scheduler")
        if len(picks) > 1:
            self.events.add("system", f"The people in this group also fit each other ({round(together * 100)}% average match)", agent="scheduler")
        return picks, window

    def choose_window(self, windows: list[Interval]) -> Interval:
        """The first window, unless the owner asked for a different schedule and the last proposal used it."""
        if "schedule" in self.prefs and self.previous and self.previous.start_at:
            prev = aware(self.previous.start_at)
            other = [w for w in windows if not (w[0] <= prev < w[1])]
            if other:
                return other[0]
        return windows[0]

    def slot(self, window: Interval) -> tuple[datetime, datetime]:
        """90 minutes from the window's start, rounded up to the half hour, kept inside the window."""
        ws, we = window
        start = ws + timedelta(minutes=(-ws.minute) % 30) if ws.second == 0 else ws
        if we - start < timedelta(minutes=MIN_GROUP_MINUTES):
            start = ws
        return start, min(we, start + SLOT)

    # ----- 3. venue -----
    def venue(self) -> dict:
        from app.services.places import nearby

        kinds = VENUES.get(self.plan.activity_type, ("cafe", "restaurant", "public_venue"))
        if "different_activity" in self.prefs and self.previous and self.previous.venue_category in kinds:
            kinds = tuple(k for k in kinds if k != self.previous.venue_category) or kinds
        found = nearby(self.plan.public_location, self.plan.city, self.settings.venue_search_enabled)
        if self.plan.public_location:
            self.events.add("tool", f"Looked up public places within 1.5 km of your event: {len(found['places'])} mapped results. "
                            f"{found['message']}", "find_nearby_places", "venue")
        for kind in kinds:
            place = next((p for p in found["places"] if p["category"] == kind), None)
            if place:
                self.events.add("system", f"Picked the nearest {kind.replace('_', ' ')}: {place['name']}", agent="venue")
                return {"label": place["name"], "category": kind, "details": place}
        kind = kinds[0]
        label = (f"A public {kind.replace('_', ' ')} in {self.plan.city} (choose exact location)" if self.plan.public_location
                 else GENERIC.get(kind, GENERIC["public_venue"]).format(city=self.plan.city))
        hint = "" if self.plan.public_location else " (add your event's public location to get a mapped place nearby)"
        self.events.add("system", f"Suggested {label[0].lower() + label[1:]}{hint}"[:400], agent="venue")
        return {"label": label[:160], "category": kind, "details": None}

    # ----- 4. checks -----
    def check(self, picks: list[Fit], start: datetime, end: datetime, venue: dict) -> None:
        lo, hi = self.pick_bounds()
        excluded = self.excluded_ids()
        ids = [uuid.UUID(f.preview.user_id) for f in picks]
        problems = []
        if not lo <= len(ids) <= hi:
            problems.append(f"group size must add {lo}-{hi} people")
        if any(i in excluded or self.blocked(i) for i in ids):
            problems.append("someone excluded or blocked was picked")
        if venue["category"] not in PUBLIC_VENUE_CATEGORIES or _PRIVATE_VENUE.search(venue["label"]):
            problems.append("the venue must be a public place")
        common = self.matching.group_availability(self.plan, self.current_member_ids() + ids)
        if not (start < end and any(aware(s) <= start and end <= aware(e) for s, e in common.windows)):
            problems.append("the time must fall inside everyone's shared free time")
        if problems:
            self.events.add("error", "Checks failed: " + "; ".join(problems), "safety_checks", "checks")
            raise StepError("checks_failed", "The safety checks did not pass, so nothing was proposed.")
        self.events.add("review", "Checks passed: public place, everyone free at that time, group size OK, nobody excluded or blocked",
                        "safety_checks", "checks")

    # ----- proposal -----
    def reason(self, f: Fit) -> str:
        p, bits = f.preview, []
        if p.shared_interests:
            bits.append(f"Shares {_join(p.shared_interests[:3])}")
        elif p.related:
            mine, theirs = p.related[0]
            bits.append(f"into {theirs}, close to your interest in {mine}")
        if f.same_activity:
            bits.append(f"also here for a {self.plan.activity_type}" if self.plan.activity_type != "other" else "similar plans")
        elif not bits:
            bits.append(f"planning {p.activity_type} in {self.plan.city}")
        hours = f.overlap_hours
        bits.append(f"free together {hours:.0f}h" if hours >= 1 else "short shared window")
        text = "; ".join(bits)
        return (text[0].upper() + text[1:])[:300]

    def propose(self, picks: list[Fit], start: datetime, end: datetime, venue: dict) -> None:
        shared = []
        for f in picks:
            shared += [i for i in f.preview.shared_interests if i not in shared]
        title = f"{TITLES.get(venue['category'], 'Meetup')} {_after(self.plan.activity_type)}".strip()
        why = f"you share {_join(shared[:3])}" if shared else "your interests and plans line up"
        explanation = (f"The InGather matcher picked this group from the people who are free when you are: {why}, and the "
                       f"people in the group fit each other too. Suggested time: {self.label(start, end)}.")
        topic = shared[0] if shared else (self.plan.interests[0] if self.plan.interests else self.plan.city)
        icebreaker = f"What's one {topic} tip for {self.plan.city} you'd share with the group?"[:280]
        from app.services.proposals import Proposals

        try:
            proposal = Proposals(self.db, self.settings).save_agent_result(
                self.run, self.plan, [(uuid.UUID(f.preview.user_id), self.reason(f)) for f in picks], title[:120], explanation,
                start.astimezone(timezone.utc), end.astimezone(timezone.utc), venue["label"], venue["category"], icebreaker,
                venue_details=venue["details"],
            )
        except ValueError as e:
            raise StepError("propose_failed", f"Could not save the group: {str(e)[:160]}")
        self.run.proposal_id = proposal.id
        n = len(picks)
        self.events.add("tool", f"Proposed “{title[:80]}” with {n} {'person' if n == 1 else 'people'} — waiting for your approval",
                        "propose_group", "gather")
        self.engine._finish(self.run, self.events, True, f"Suggested “{title[:100]}” with {n} {'person' if n == 1 else 'people'}. "
                            "Nobody is invited until you approve.")


def _join(items: list[str]) -> str:
    items = [normalize(i) for i in items]
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


def _after(activity: str) -> str:
    return {"conference": "after the conference", "hackathon": "during the hackathon", "study": "study break",
            "travel": "around town", "event": "before the event"}.get(activity, "")

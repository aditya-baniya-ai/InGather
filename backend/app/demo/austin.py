"""Seed the synthetic Austin demo: 1,000 fictional residents with plans for the coming week, plus open groups that
the ML matcher formed among them, each with one or two spots left for someone from the Home feed.

    python -m app.seed            # runs this when DEMO_MODE=true (DEMO_SYNTHETIC_USERS, DEMO_OPEN_GROUPS)

Idempotent: existing people are kept (so Muse-polished bios survive restarts). When the week has passed, plans move
to the new week and stale groups are rebuilt.
"""

import logging
import random
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.demo.people import CITY, TZ, Person, generate, week_windows
from app.demo.venues import load_catalog, nearest
from app.models import (
    AvailabilityWindow, DiscoveryMode, MemberStatus, Plan, PlanStatus, Proposal, ProposalStatus, User, Verification, now,
)
from app.security import Passwords

log = logging.getLogger("ingather.demo")
ACTIVITIES = ("coffee", "event", "other", "hackathon", "study", "conference", "travel")
MIN_PER_ACTIVITY = 12  # open groups per Home category tab

DOMAIN = "@atx.ingather.example"
PASSWORD = "demo-password"
VENUE_KINDS = {  # venue categories that suit each activity, best first (catalog categories)
    "coffee": ("cafe", "food_hall", "restaurant"), "hackathon": ("cafe", "food_hall", "library"),
    "conference": ("cafe", "restaurant"), "study": ("library", "cafe"), "event": ("food_hall", "restaurant", "cafe"),
    "travel": ("museum", "cafe", "food_hall"), "other": ("cafe", "food_hall", "park"),
}


# How a group's title shows which kind of plan it is, unless the title already says so.
_TITLE_CONTEXT = {
    "conference": (("conference", "session"), "{t} after the conference sessions"),
    "travel": (("austin", "explor", "visit"), "{t} while visiting Austin"),
    "study": (("study", "library", "class"), "Study break: {l}"),
    "hackathon": (("hack",), "{t} at the hackathon"),
}


def group_title(plan: Plan) -> str:
    """The host's plan title, made to fit its Home category ("Museum afternoon while visiting Austin")."""
    title = plan.title
    words, template = _TITLE_CONTEXT.get(plan.activity_type, ((), "{t}"))
    if any(w in title.lower() for w in words) or not words:
        return title[:120]
    return template.format(t=title, l=title[0].lower() + title[1:])[:120]


def is_synthetic(user: User | None) -> bool:
    return bool(user and user.email.endswith(DOMAIN))


def avatar_url(key: str) -> str:
    return f"/api/demo/avatars/{key}.svg"


def local_today() -> date:
    return datetime.now(ZoneInfo(TZ)).date()


class AustinSeeder:
    def __init__(self, db: Session, settings: Settings, n: int = 1000, groups: int = 150, today: date | None = None):
        self.db, self.settings, self.n, self.groups = db, settings, n, groups
        self.today = today or local_today()
        self.rng = random.Random(7)

    def run(self) -> dict:
        people = generate(self.n)
        created, refreshed = self._people(people)
        stale = self._drop_stale_groups()
        formed = self._groups(people)
        return {"people": len(people), "created": created, "refreshed": refreshed, "stale_groups": stale, "groups": formed}

    # ----- people -----
    def _people(self, people: list[Person]) -> tuple[int, int]:
        existing = {u.email: u for u in self.db.scalars(select(User).where(User.email.like(f"%{DOMAIN}")))}
        plans = {p.owner_id: p for p in self.db.scalars(select(Plan).join(User, Plan.owner_id == User.id).where(User.email.like(f"%{DOMAIN}")))}
        password = Passwords.hash(PASSWORD)  # one hash for all fictional accounts: bcrypt x1000 would take minutes
        created = refreshed = 0
        for p in people:
            user = existing.get(p.email)
            if user is None:
                user = User(
                    email=p.email, password_hash=password, display_name=p.name, avatar_url=avatar_url(p.key), bio=p.bio,
                    interests=p.interests, verification=Verification.verified_demo, is_adult=True, is_demo=True,
                    group_only=True, home_area=p.area[0], home_lat=p.area[1], home_lng=p.area[2],
                )
                self.db.add(user)
                self.db.flush()
                created += 1
            plan = plans.get(user.id)
            if plan is None:
                self.db.add(self._plan(user, p))
            elif plan.end_date < self.today:  # last week's plan: move it to this week
                plan.start_date, plan.end_date = self.today, self.today + timedelta(days=6)
                plan.windows = [AvailabilityWindow(starts_at=s, ends_at=e) for s, e in week_windows(p, self.today)]
                plan.status = PlanStatus.active
                refreshed += 1
        self.db.commit()
        return created, refreshed

    def _plan(self, user: User, p: Person) -> Plan:
        return Plan(
            owner_id=user.id, activity_type=p.activity, title=p.title, goal_text=p.goal, city=CITY, timezone=TZ,
            public_location=p.public_location, start_date=self.today, end_date=self.today + timedelta(days=6),
            intent=p.intent, interests=p.interests, group_min=p.group_min, group_max=p.group_max, group_only=True,
            discovery_mode=DiscoveryMode.mutual_discovery, preview_text=p.preview, ai_consent_at=now(),
            windows=[AvailabilityWindow(starts_at=s, ends_at=e) for s, e in week_windows(p, self.today)],
        )

    # ----- open groups -----
    def _synthetic_proposals(self) -> list[Proposal]:
        q = select(Proposal).join(User, Proposal.owner_id == User.id).where(User.email.like(f"%{DOMAIN}"))
        return list(self.db.scalars(q))

    def _drop_stale_groups(self) -> int:
        cutoff = datetime.now(timezone.utc)
        stale = [p for p in self._synthetic_proposals()
                 if p.start_at is None or (p.start_at if p.start_at.tzinfo else p.start_at.replace(tzinfo=timezone.utc)) < cutoff]
        for p in stale:
            self.db.delete(p)
        self.db.commit()
        return len(stale)

    def _groups(self, people: list[Person]) -> int:
        from app.services.gather import GatherEngine, start_run

        current = [p for p in self._synthetic_proposals() if p.open_to_requests and p.status != ProposalStatus.cancelled]
        for p in current:  # keeps titles of groups seeded by older versions in line with their category
            p.activity_title = group_title(self.db.get(Plan, p.plan_id))
        counts = Counter(self.db.get(Plan, p.plan_id).activity_type for p in current)
        # Every Home category tab (travel, conference, study...) needs groups of its own, not just the common ones.
        floor = min(MIN_PER_ACTIVITY, max(1, self.groups // len(ACTIVITIES)))
        need = self.groups - len(current)
        if need <= 0 and all(counts[a] >= floor for a in ACTIVITIES):
            self.db.commit()
            return len(current)
        by_email = {p.email: p for p in people}
        users = {u.id: u for u in self.db.scalars(select(User).where(User.email.like(f"%{DOMAIN}")))}
        taken = {m.user_id for p in current for m in p.members}
        quiet = self.settings.model_copy(update={"venue_search_enabled": False})  # no map lookups while seeding
        catalog = load_catalog(self.settings)
        plans = [pl for pl in self.db.scalars(select(Plan).where(Plan.owner_id.in_(users), Plan.status == PlanStatus.active))
                 if pl.group_max >= 3 and pl.owner_id not in taken]
        self.rng.shuffle(plans)
        pool = {a: [pl for pl in plans if pl.activity_type == a] for a in ACTIVITIES}
        formed = 0
        while True:
            # Fill the thinnest category first; stop at the target once every category has its floor.
            short = [a for a in ACTIVITIES if pool[a] and counts[a] < floor]
            open_ = [a for a in ACTIVITIES if pool[a]]
            if not open_ or (formed >= need and not short):
                break
            activity = min(short or open_, key=lambda a: counts[a])
            plan = pool[activity].pop()
            host = users[plan.owner_id]
            if host.id in taken:
                continue
            run = start_run(self.db, host, plan, "user", excluded=taken - {host.id})
            GatherEngine(self.db, quiet).run(run.id)
            self.db.refresh(run)
            proposal = self.db.get(Proposal, run.proposal_id) if run.proposal_id else None
            if proposal is None:
                continue
            self._open_up(proposal, plan, host, by_email.get(host.email), catalog)
            taken |= {m.user_id for m in proposal.members}
            counts[activity] += 1
            formed += 1
        self.db.commit()
        return len(current) + formed

    def _open_up(self, proposal: Proposal, plan: Plan, host: User, person: Person | None, catalog: list[dict]) -> None:
        """Pretend the host invited the suggestions and they said yes, keeping 1-2 spots open for the feed."""
        others = [m for m in proposal.members if not m.is_initiator]
        keep = max(1, min(len(others), plan.group_max - 1 - self.rng.choice((1, 2))))
        at = now()
        for m in others[:keep]:
            m.status, m.invited_at, m.responded_at = MemberStatus.accepted, at, at
        for m in others[keep:]:
            proposal.members.remove(m)
        proposal.status = ProposalStatus.invites_pending
        proposal.open_to_requests = True
        proposal.activity_title = group_title(plan)  # the host's own words ("Board game night") read better in a feed
        near = (host.home_lat, host.home_lng) if host.home_lat is not None else None
        venue = nearest(catalog, VENUE_KINDS.get(plan.activity_type, ("cafe",)), near) if catalog else None
        if venue:
            proposal.venue_label, proposal.venue_category = venue["name"][:160], venue["category"]
            proposal.venue_details = {
                "name": venue["name"], "category": venue["category"], "address": venue.get("area") or venue["area_name"],
                "source": "Muse Spark web search", "source_url": venue.get("source_url"),
            }


def seed_austin(db: Session, settings: Settings) -> dict:
    return AustinSeeder(db, settings, settings.demo_synthetic_users, settings.demo_open_groups).run()

"""Fictional demo data. Run with `uv run python -m app.seed`. Idempotent; refuses unless DEMO_MODE=true.
Every person here is made up; emails use the reserved `.example` domain and nothing is ever sent."""

import sys
from dataclasses import dataclass, field
from datetime import date, datetime, time

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import Base, SessionLocal, engine
from app.models import AvailabilityWindow, Block, DiscoveryMode, Plan, User, Verification, now
from app.security import Passwords
from app.services.clock import daily_windows

PASSWORD = "demo-password"
PHILLY, NY = "Philadelphia", "America/New_York"
CONF = (date(2027, 1, 17), date(2027, 1, 19))


@dataclass
class Persona:
    key: str
    name: str
    bio: str
    interests: list[str]
    title: str
    goal: str
    preview: str
    activity: str = "conference"
    intent: str = "friends"
    city: str = PHILLY
    tz: str = NY
    dates: tuple[date, date] = CONF
    hours: tuple[time, time] = (time(17), time(22))
    mode: DiscoveryMode = DiscoveryMode.mutual_discovery
    ai_consent: bool = False
    extra: dict = field(default_factory=dict)

    @property
    def email(self) -> str:
        return f"{self.key}@ingather.example"


PERSONAS = [
    Persona(
        "alice", "Alice", "Fictional demo initiator. Product designer in town for a tech conference.",
        ["tech", "food", "city exploring", "museums", "coffee"],
        "Philly tech conference evenings",
        "In Philadelphia for a tech conference Jan 17-19 2027. Free after 5pm. Looking for 2-3 friendly adults "
        "for food and exploring the city, group only.",
        "Conference attendee looking for a small group for food and city exploring.",
        mode=DiscoveryMode.private_browse, ai_consent=True,
    ),
    Persona(
        "maya", "Maya", "Fictional demo user. Backend engineer who plans trips around food.",
        ["tech", "food", "city exploring"], "Conference + food crawl",
        "Same conference, would love to explore food spots after sessions, 5-7pm.",
        "Conference attendee interested in food/city exploring.", hours=(time(17), time(19)),
    ),
    Persona(
        "sofia", "Sofia", "Fictional demo user. Traveling solo, loves a good flat white.",
        ["coffee", "city exploring", "friendship"], "Solo trip to Philly",
        "Traveling solo, want coffee and friendship in a group, free after 6pm.",
        "Visitor interested in group coffee/exploration.", activity="travel", hours=(time(18), time(22)),
    ),
    Persona(
        "jordan", "Jordan", "Fictional demo user. Data scientist and museum completionist.",
        ["tech", "museums"], "Conference and museums",
        "At the conference, want to see a museum or two in the early evening.",
        "Conference/museum enthusiast.", hours=(time(17, 30), time(19, 30)),
    ),
    Persona(
        "taylor", "Taylor", "Fictional demo user. Local AI student who likes group outings.",
        ["tech", "AI", "coffee"], "Local evenings out",
        "Local student, free after 6pm, up for public group activities.",
        "Local tech enthusiast interested in public group activities.",
        activity="event", intent="activity", dates=(date(2027, 1, 10), date(2027, 1, 31)), hours=(time(18), time(22)),
    ),
    Persona(
        "eve", "Eve", "Fictional demo account used to show the attacker scenario. Blocked by Alice.",
        ["tech", "food"], "Philly weekend",
        "Wants to find out where people are going.", "Visitor in Philadelphia.",
    ),
    Persona(
        "priya", "Priya", "Fictional demo user. PhD student, always has a book.",
        ["coffee", "books"], "Study break in Philly",
        "Writing week in Philly, happy to grab coffee with a group in the evening.",
        "Visiting researcher up for coffee.", activity="study", dates=(date(2027, 1, 15), date(2027, 1, 20)),
    ),
    Persona(
        "marcus", "Marcus", "Fictional demo user. Jazz fan and amateur cook.",
        ["food", "jazz"], "Food + live music",
        "In town for a few days, looking for dinner and live music with a group.",
        "Visitor into food and live music.", activity="event", hours=(time(19), time(23)),
    ),
    Persona(
        "lena", "Lena", "Fictional demo user. Illustrator who sketches in galleries.",
        ["museums", "art"], "Gallery hopping",
        "Spending a long weekend in Philly visiting galleries.",
        "Art lover visiting galleries.", activity="travel", dates=(date(2027, 1, 16), date(2027, 1, 19)),
    ),
    Persona(
        "noah", "Noah", "Fictional demo user. Prefers to browse privately.",
        ["tech", "running"], "Quiet conference trip",
        "At the conference but only browsing for now.", "Conference attendee.", mode=DiscoveryMode.private_browse,
    ),
    Persona(
        "diego", "Diego", "Fictional demo user. Hacking at HackTX in Austin.",
        ["tech", "hackathons", "tacos"], "HackTX weekend",
        "At HackTX in Austin, looking for a team dinner crew.", "HackTX hacker looking for dinner buddies.",
        activity="hackathon", city="Austin", tz="America/Chicago",
        dates=(date(2026, 10, 24), date(2026, 10, 25)), hours=(time(18), time(21)),
    ),
]


# Fictional, coarse (~1 km) home areas so the venue vote has a group midpoint without any network geocoding.
HOME_AREAS = {
    "alice": ("Center City, Philadelphia", 39.95, -75.17), "maya": ("Fishtown, Philadelphia", 39.97, -75.13),
    "sofia": ("Rittenhouse, Philadelphia", 39.95, -75.17), "jordan": ("University City, Philadelphia", 39.95, -75.19),
    "taylor": ("Northern Liberties, Philadelphia", 39.96, -75.14), "eve": ("Old City, Philadelphia", 39.95, -75.14),
    "priya": ("Graduate Hospital, Philadelphia", 39.94, -75.18), "marcus": ("South Philadelphia", 39.93, -75.16),
    "lena": ("Fairmount, Philadelphia", 39.97, -75.18), "noah": ("Queen Village, Philadelphia", 39.94, -75.15),
    "diego": ("East Austin", 30.26, -97.72),
}


class Seeder:
    def __init__(self, db: Session):
        self.db = db

    def run(self) -> dict[str, User]:
        users = {p.key: self._user(p) for p in PERSONAS}
        self.db.flush()
        for p in PERSONAS:
            self._plan(users[p.key], p)
        self._block(users["alice"], users["eve"])
        self.db.commit()
        return users

    def _user(self, p: Persona) -> User:
        user = self.db.scalar(select(User).where(User.email == p.email))
        if user is None:
            user = User(email=p.email, password_hash=Passwords.hash(PASSWORD))
            self.db.add(user)
        user.display_name, user.bio, user.interests = p.name, p.bio, p.interests
        user.avatar_url = f"/avatars/{p.key}.svg"
        user.verification, user.is_adult, user.is_demo = Verification.verified_demo, True, True
        user.discovery_paused, user.group_only = False, True
        if p.key in HOME_AREAS and user.home_area is None:
            user.home_area, user.home_lat, user.home_lng = HOME_AREAS[p.key]
        return user

    def _plan(self, user: User, p: Persona) -> None:
        if self.db.scalar(select(Plan.id).where(Plan.owner_id == user.id, Plan.title == p.title)):
            return
        self.db.add(
            Plan(
                owner_id=user.id, activity_type=p.activity, title=p.title, goal_text=p.goal, city=p.city,
                timezone=p.tz, start_date=p.dates[0], end_date=p.dates[1], intent=p.intent, interests=p.interests,
                group_min=3, group_max=4, group_only=True, discovery_mode=p.mode, preview_text=p.preview,
                ai_consent_at=now() if p.ai_consent else None,
                windows=[AvailabilityWindow(starts_at=s, ends_at=e) for s, e in daily_windows(p.tz, *p.dates, *p.hours)],
            )
        )

    def _block(self, blocker: User, blocked: User) -> None:
        q = select(Block.id).where(Block.blocker_id == blocker.id, Block.blocked_id == blocked.id)
        if self.db.scalar(q) is None:
            self.db.add(Block(blocker_id=blocker.id, blocked_id=blocked.id))


def main() -> None:
    if not get_settings().demo_mode:
        sys.exit("Refusing to seed: DEMO_MODE is not enabled.")
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        users = Seeder(db).run()
    print(f"Seeded {len(users)} fictional demo users at {datetime.now():%H:%M} (password: {PASSWORD}).")
    settings = get_settings()
    if settings.demo_synthetic_users > 0:
        from app.demo.austin import seed_austin

        with SessionLocal() as db:
            stats = seed_austin(db, settings)
        print(f"Austin demo: {stats['people']} fictional residents ({stats['created']} new, {stats['refreshed']} moved to this week), "
              f"{stats['groups']} open groups ({stats['stale_groups']} stale ones rebuilt).")


if __name__ == "__main__":
    main()

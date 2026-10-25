import os

os.environ.update(MODEL_API_KEY="", DEMO_MODE="true", DATABASE_URL="sqlite://", JWT_SECRET="test-secret-test-secret-test-secret-0123",
                  VENUE_SEARCH_ENABLED="false", SUPABASE_URL="", SUPABASE_ANON_KEY="")

import sys  # noqa: E402
import types  # noqa: E402
from uuid import UUID  # noqa: E402

import bcrypt  # noqa: E402
import pytest  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, event  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app import db as app_db  # noqa: E402
from app.api import agent, auth, chats, plans, proposals, safety  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.models import AgentEvent, AgentRun, Plan, RunStatus, now  # noqa: E402
from app.security import Passwords, Tokens  # noqa: E402
from app.seed import Seeder  # noqa: E402
from app.services.matching import Matching  # noqa: E402
from app.services.proposals import ACTIVE, Proposals  # noqa: E402
from app.services.ratelimit import limiter  # noqa: E402

get_settings.cache_clear()


@pytest.fixture(autouse=True)
def engine(monkeypatch):
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    event.listen(eng, "connect", lambda conn, _: conn.execute("PRAGMA foreign_keys=ON"))  # cascade like Postgres
    app_db.Base.metadata.create_all(eng)
    app_db.SessionLocal.configure(bind=eng)  # background tasks open their own sessions
    monkeypatch.setattr(Passwords, "hash", staticmethod(lambda p: bcrypt.hashpw(p.encode(), bcrypt.gensalt(4)).decode()))
    limiter.reset()
    yield eng
    app_db.Base.metadata.drop_all(eng)
    eng.dispose()


@pytest.fixture
def db(engine):
    with app_db.SessionLocal() as session:
        yield session


@pytest.fixture
def settings():
    return get_settings()


@pytest.fixture
def app(engine):
    application = FastAPI()
    for module in (auth, plans, agent, proposals, safety, chats):
        application.include_router(module.router)

    def get_db():
        with app_db.SessionLocal() as session:
            yield session

    application.dependency_overrides[app_db.get_db] = get_db
    return application


@pytest.fixture
def client(app):
    return TestClient(app)


@pytest.fixture
def users(db):
    """Seeded fictional demo users keyed by first name (alice, maya, sofia, jordan, taylor, eve, ...)."""
    return Seeder(db).run()


@pytest.fixture
def plan_of(db):
    def get(user) -> Plan:
        return db.query(Plan).filter(Plan.owner_id == user.id).order_by(Plan.created_at).first()

    return get


class Api:
    def __init__(self, client: TestClient, user):
        self.client, self.headers = client, {"Authorization": f"Bearer {Tokens.issue(user.id)}"}

    def get(self, url, **kw):
        return self.client.get(url, headers=self.headers, **kw)

    def post(self, url, json=None):
        return self.client.post(url, headers=self.headers, json=json if json is not None else {})

    def patch(self, url, json):
        return self.client.patch(url, headers=self.headers, json=json)

    def put(self, url, json):
        return self.client.put(url, headers=self.headers, json=json)

    def delete(self, url):
        return self.client.delete(url, headers=self.headers)


@pytest.fixture
def as_user(client):
    return lambda user: Api(client, user)


class FakeAgent:
    """Deterministic stand-in for the gather engine (app.services.gather), so these API tests control who is picked."""

    def __init__(self):
        self.started: list[tuple[str, set]] = []

    def start_run(self, db, owner, plan, trigger, goal="", excluded=()):
        self.started.append((trigger, set(excluded)))
        run = AgentRun(
            plan_id=plan.id,
            owner_id=owner.id,
            trigger=trigger,
            mode="ml",
            goal=goal,
            excluded_user_ids=sorted(str(x) for x in excluded),
        )
        db.add(run)
        db.commit()
        return run

    def run_in_background(self, run_id):
        s = get_settings()
        with app_db.SessionLocal() as db:
            run = db.get(AgentRun, run_id)
            plan = db.get(Plan, run.plan_id)
            svc, matching = Proposals(db, s), Matching(db, s)
            current = svc.open_for(plan)
            group = [m.user_id for m in current.members if m.status in ACTIVE and not m.is_initiator] if current else []
            picks = []
            # Most shared interests first, then by name: deterministic and independent of the ML model's scores.
            pool = matching.eligible(plan, {UUID(x) for x in run.excluded_user_ids})
            for c in sorted(pool, key=lambda c: (-len(c.shared_interests), c.display_name)):
                if len(group) + len(picks) >= plan.group_max - 1:
                    break
                if matching.group_availability(plan, group + [p for p, _ in picks] + [UUID(c.user_id)]).possible:
                    picks.append((UUID(c.user_id), f"Shares {', '.join(c.shared_interests) or 'overlapping time'}"))
            if picks:
                svc.save_agent_result(
                    run, plan, picks, "Evening food walk", "Overlapping evenings and shared interests.",
                    None, None, "A public café near the venue", "cafe", "What are you most excited to learn?",
                )
            run.status, run.finished_at = RunStatus.completed, now()
            run.summary = f"Suggested {len(picks)} people."
            run.events.append(AgentEvent(seq=1, kind="system", summary=run.summary))
            db.commit()


@pytest.fixture
def fake_agent(monkeypatch):
    fake = FakeAgent()
    module = types.ModuleType("app.services.gather")
    module.start_run, module.run_in_background = fake.start_run, fake.run_in_background
    monkeypatch.setitem(sys.modules, "app.services.gather", module)
    return fake


@pytest.fixture
def statuses():
    def get(api, proposal_id) -> dict[str, str]:
        body = api.get(f"/api/proposals/{proposal_id}").json()
        return {m["display_name"]: m["status"] for m in body["members"]}

    return get


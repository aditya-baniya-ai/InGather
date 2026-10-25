"""Attacker cases from spec section 14. Denials are always the uniform 404 with no extra fields."""

from uuid import UUID

import pytest

from app.config import Settings, get_settings
from app.models import Plan, User, Verification
from tests.helpers import approve, members, start_agent

pytestmark = pytest.mark.usefixtures("fake_agent")
NOT_FOUND = {"detail": "Not found"}
PLAN = {
    "activity_type": "conference", "title": "Bob's trip", "goal_text": "secret itinerary", "city": "Philadelphia",
    "timezone": "America/New_York", "start_date": "2027-01-17", "end_date": "2027-01-19", "intent": "friends",
    "interests": ["tech"], "group_min": 2, "group_max": 4, "group_only": True,
    "windows": [{"starts_at": "2027-01-17T22:00:00Z", "ends_at": "2027-01-18T02:00:00Z"}],
}


@pytest.fixture
def bob(client, db):
    res = client.post("/api/auth/register", json={"email": "bob@x.example", "password": "bob-password", "display_name": "Bob"})
    assert res.status_code == 200
    return db.query(User).filter_by(email="bob@x.example").one()


def test_bob_cannot_read_or_change_alices_plan(users, plan_of, as_user, bob):
    api, pid = as_user(bob), plan_of(users["alice"]).id
    for res in (
        api.get(f"/api/plans/{pid}"),
        api.patch(f"/api/plans/{pid}", {"title": "pwned"}),
        api.post(f"/api/plans/{pid}/discovery", {"mode": "mutual_discovery"}),
        api.delete(f"/api/plans/{pid}"),
        api.post("/api/agent/runs", {"plan_id": str(pid)}),
    ):
        assert res.status_code == 404 and res.json() == NOT_FOUND
    assert api.get("/api/plans").json() == []
    assert as_user(users["alice"]).get(f"/api/plans/{pid}").json()["title"] == "Philly tech conference evenings"


def test_unknown_ids_look_the_same_as_forbidden_ones(as_user, users):
    api = as_user(users["eve"])
    fake = "00000000-0000-0000-0000-000000000000"
    for url in (f"/api/plans/{fake}", f"/api/proposals/{fake}", f"/api/agent/runs/{fake}"):
        assert api.get(url).json() == NOT_FOUND


def test_owner_id_in_body_is_ignored(db, users, as_user, bob):
    res = as_user(bob).post("/api/plans", {**PLAN, "owner_id": str(users["alice"].id)})
    assert res.status_code == 201
    assert db.get(Plan, UUID(res.json()["id"])).owner_id == bob.id
    assert as_user(users["alice"]).get(f"/api/plans/{res.json()['id']}").status_code == 404


def test_plan_validation(as_user, bob):
    api = as_user(bob)
    assert api.post("/api/plans", {**PLAN, "end_date": "2027-01-01"}).status_code == 422
    assert api.post("/api/plans", {**PLAN, "group_min": 4, "group_max": 3}).status_code == 422
    assert api.post("/api/plans", {**PLAN, "group_max": 5}).status_code == 422
    assert api.post("/api/plans", {**PLAN, "timezone": "Mars/Base"}).status_code == 422
    bad_window = [{"starts_at": "2027-01-17T22:00:00Z", "ends_at": "2027-01-17T21:00:00Z"}]
    assert api.post("/api/plans", {**PLAN, "windows": bad_window}).status_code == 422
    pid = api.post("/api/plans", PLAN).json()["id"]
    assert api.patch(f"/api/plans/{pid}", {"group_min": 4, "group_max": 2}).status_code == 422
    assert api.patch(f"/api/plans/{pid}", {"title": "New"}).json()["title"] == "New"


def test_patch_me_cannot_set_verification(db, as_user, bob):
    res = as_user(bob).patch(
        "/api/me",
        {"display_name": "Bobby", "verification": "verified_live", "is_adult": True, "is_demo": True, "email": "a@b.example"},
    )
    body = res.json()
    assert res.status_code == 200 and body["display_name"] == "Bobby"
    assert body["verification"] == "unverified" and not body["is_demo"] and not body["can_discover"]
    db.refresh(bob)
    assert bob.verification == Verification.unverified and not bob.is_adult and bob.email == "bob@x.example"


def test_unverified_user_cannot_run_agent(as_user, bob):
    api = as_user(bob)
    pid = api.post("/api/plans", PLAN).json()["id"]
    api.post(f"/api/plans/{pid}/discovery", {"mode": "private_browse", "ai_consent": True})
    assert api.post("/api/agent/runs", {"plan_id": pid}).json() == {"detail": "not_eligible"}


def test_agent_requires_ai_consent_and_active_plan(users, plan_of, as_user):
    api, pid = as_user(users["maya"]), plan_of(users["maya"]).id
    res = api.post("/api/agent/runs", {"plan_id": str(pid)})
    assert res.status_code == 409 and res.json() == {"detail": "ai_consent_required"}
    api.post(f"/api/plans/{pid}/discovery", {"mode": "paused", "ai_consent": True})
    assert api.post("/api/agent/runs", {"plan_id": str(pid)}).json() == {"detail": "plan_inactive"}


def test_verified_demo_has_no_power_outside_demo_mode(app, users, plan_of, as_user):
    app.dependency_overrides[get_settings] = lambda: Settings(demo_mode=False, model_api_key="")
    api = as_user(users["alice"])
    assert api.get("/api/me").json()["can_discover"] is False
    assert api.post("/api/agent/runs", {"plan_id": str(plan_of(users["alice"]).id)}).status_code == 403
    assert api.get("/api/auth/demo-accounts").status_code == 404
    assert api.client.post("/api/auth/demo-login", json={"email": "alice@ingather.example"}).status_code == 404


def test_demo_login_only_for_demo_accounts(client, users, bob):
    assert client.post("/api/auth/demo-login", json={"email": "alice@ingather.example"}).status_code == 200
    assert client.post("/api/auth/demo-login", json={"email": "bob@x.example"}).status_code == 404
    accounts = client.get("/api/auth/demo-accounts").json()
    assert "Alice" in {a["display_name"] for a in accounts} and set(accounts[0]) == {"email", "display_name", "avatar_url", "bio"}


def test_login(client, users):
    ok = client.post("/api/auth/login", json={"email": "alice@ingather.example", "password": "demo-password"})
    assert ok.status_code == 200 and ok.json()["user"]["can_discover"] is True
    assert client.post("/api/auth/login", json={"email": "alice@ingather.example", "password": "nope"}).status_code == 401
    assert client.get("/api/me").status_code == 401


def test_login_rate_limited(client, users):
    codes = [client.post("/api/auth/login", json={"email": "eve@ingather.example", "password": "x"}).status_code for _ in range(11)]
    assert codes[:10] == [401] * 10 and codes[10] == 429


def test_agent_runs_rate_limited(users, plan_of, as_user):
    api, pid = as_user(users["alice"]), str(plan_of(users["alice"]).id)
    codes = [api.post("/api/agent/runs", {"plan_id": pid}).status_code for _ in range(11)]
    assert codes.count(202) == 10 and codes[-1] == 429


def test_uninvited_users_cannot_see_or_answer_a_proposal(users, plan_of, as_user):
    alice = as_user(users["alice"])
    pid = start_agent(alice, plan_of(users["alice"]).id)["proposal_id"]
    approve(alice, pid, users["sofia"])
    for name in ("eve", "maya", "taylor"):  # outsider, suggested-only, unrelated
        api = as_user(users[name])
        assert api.get(f"/api/proposals/{pid}").json() == NOT_FOUND
        assert api.post(f"/api/proposals/{pid}/respond", {"accept": True}).json() == NOT_FOUND
        assert api.post(f"/api/proposals/{pid}/confirm", {"version": 1}).json() == NOT_FOUND
    assert alice.post(f"/api/proposals/{pid}/respond", {"accept": True}).status_code == 404  # owner isn't an invitee
    eve = as_user(users["eve"])
    assert eve.post(f"/api/proposals/{pid}/approve-invitations", {"version": 1, "user_ids": [str(users["eve"].id)]}).json() == NOT_FOUND
    assert eve.post(f"/api/proposals/{pid}/members/{users['maya'].id}/pass", {}).json() == NOT_FOUND
    assert members(alice, pid)["Sofia"]["status"] == "invited"


def test_invitee_view_leaks_nothing_private(users, plan_of, as_user):
    alice = as_user(users["alice"])
    pid = start_agent(alice, plan_of(users["alice"]).id)["proposal_id"]
    approve(alice, pid, users["sofia"])
    text = as_user(users["sofia"]).get(f"/api/proposals/{pid}").text
    for secret in ("Free after 5pm", "alice@ingather.example", "Maya", "Jordan", "windows", "goal_text", "public café"):
        assert secret not in text


def test_blocked_users_are_removed_and_lose_access(users, plan_of, as_user):
    alice, sofia = as_user(users["alice"]), as_user(users["sofia"])
    pid = start_agent(alice, plan_of(users["alice"]).id)["proposal_id"]
    approve(alice, pid, users["sofia"], users["jordan"])
    assert sofia.post("/api/blocks", {"user_id": str(users["alice"].id)}).status_code == 201
    assert sofia.get(f"/api/proposals/{pid}").json() == NOT_FOUND
    assert sofia.get("/api/invitations").json() == []
    assert "Sofia" not in members(alice, pid)
    assert sofia.get("/api/blocks").json() == [{"user_id": str(users["alice"].id), "display_name": "Alice"}]
    # Eve (blocked by Alice in the seed) is never suggested; Alice can't approve her either
    assert "Eve" not in members(alice, pid)
    assert sofia.delete(f"/api/blocks/{users['alice'].id}").status_code == 204
    assert sofia.get("/api/blocks").json() == []


def test_owner_blocking_a_suggested_member_removes_them(users, plan_of, as_user):
    alice = as_user(users["alice"])
    pid = start_agent(alice, plan_of(users["alice"]).id)["proposal_id"]
    alice.post("/api/blocks", {"user_id": str(users["maya"].id)})
    assert "Maya" not in members(alice, pid)
    version = alice.get(f"/api/proposals/{pid}").json()["version"]
    res = alice.post(f"/api/proposals/{pid}/approve-invitations", {"version": version, "user_ids": [str(users["maya"].id)]})
    assert res.status_code == 409


def test_cancelled_and_paused_plans_leave_discovery(users, plan_of, as_user):
    as_user(users["maya"]).post(f"/api/plans/{plan_of(users['maya']).id}/discovery", {"mode": "paused"})
    assert as_user(users["sofia"]).delete(f"/api/plans/{plan_of(users['sofia']).id}").status_code == 204
    as_user(users["jordan"]).patch("/api/me", {"discovery_paused": True})
    alice = as_user(users["alice"])
    pid = start_agent(alice, plan_of(users["alice"]).id)["proposal_id"]
    assert not {"Maya", "Sofia", "Jordan"} & set(members(alice, pid))


def test_deleting_a_plan_removes_its_proposals_for_everyone(users, plan_of, as_user):
    alice = as_user(users["alice"])
    plan_id = plan_of(users["alice"]).id
    pid = start_agent(alice, plan_id)["proposal_id"]
    approve(alice, pid, users["sofia"])
    alice.delete(f"/api/plans/{plan_id}")
    assert alice.get(f"/api/proposals/{pid}").status_code == 404
    assert as_user(users["sofia"]).get(f"/api/proposals/{pid}").status_code == 404
    assert as_user(users["sofia"]).get("/api/invitations").json() == []
    assert alice.get(f"/api/plans/{plan_id}").status_code == 404


def test_reports(as_user, users):
    api = as_user(users["alice"])
    res = api.post("/api/reports", {"reason": "harassment", "reported_user_id": str(users["eve"].id), "details": "..."})
    assert res.status_code == 201 and res.json()["status"] == "open"
    assert api.post("/api/reports", {"reason": "made-up"}).status_code == 422

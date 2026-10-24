"""Full demo journey over HTTP (spec section 5) with a deterministic fake agent."""

import pytest

from app.models import ConsentEvent, OutboxEvent
from tests.helpers import approve, members, start_agent

pytestmark = pytest.mark.usefixtures("fake_agent")


def test_full_journey(db, users, plan_of, as_user, fake_agent):
    alice, maya, sofia, jordan, taylor, eve = (as_user(users[k]) for k in ("alice", "maya", "sofia", "jordan", "taylor", "eve"))
    plan_id = plan_of(users["alice"]).id

    # 1. agent suggests a feasible group; nobody is contacted yet
    run = start_agent(alice, plan_id)
    pid = run["proposal_id"]
    assert {k: v["status"] for k, v in members(alice, pid).items()} == {
        "Alice": "accepted", "Maya": "suggested", "Jordan": "suggested", "Sofia": "suggested"
    }
    assert members(alice, pid)["Maya"]["reason"].startswith("Shares")
    assert alice.get(f"/api/plans/{plan_id}").json()["latest_proposal_id"] == pid
    assert maya.get("/api/invitations").json() == []

    # 2. pass Maya privately -> replan suggests someone else; Maya never learns anything
    res = alice.post(f"/api/proposals/{pid}/members/{users['maya'].id}/pass", {"feedback": "prefer_group"})
    assert res.status_code == 202 and res.json()["trigger"] == "pass"
    assert fake_agent.started[-1] == ("pass", {users["maya"].id})
    roster = members(alice, pid)
    assert roster["Maya"]["status"] == "passed" and roster["Taylor"]["status"] == "suggested"
    assert maya.get(f"/api/proposals/{pid}").status_code == 404
    assert maya.get("/api/invitations").json() == []

    # 3. approve only Sofia and Jordan
    out = approve(alice, pid, users["sofia"], users["jordan"])
    assert out["status"] == "invites_pending"
    assert db.query(ConsentEvent).filter_by(kind="approve_invites").count() == 1
    assert taylor.get(f"/api/proposals/{pid}").status_code == 404  # still only suggested
    [inv] = sofia.get("/api/invitations").json()
    assert inv["from_display_name"] == "Alice" and inv["city"] == "Philadelphia" and inv["date"] == "2027-01-17"

    # invitee sees only the minimal preview
    view = sofia.get(f"/api/proposals/{pid}").json()
    assert view["viewer_role"] == "invitee" and view["members"] == [] and view["venue_label"] is None
    assert view["start_at"] == "2027-01-17" and view["explanation"] == "" and view["initiator_name"] == "Alice"

    # 4. Sofia accepts, Jordan declines -> outbox -> autonomous replan, but no new invitation
    assert sofia.post(f"/api/proposals/{pid}/respond", {"accept": True}).json()["viewer_role"] == "member"
    assert jordan.post(f"/api/proposals/{pid}/respond", {"accept": False}).status_code == 200
    assert db.query(OutboxEvent).filter_by(kind="invitation_declined").one().processed_at is not None
    assert fake_agent.started[-1] == ("decline", {users["maya"].id, users["jordan"].id})
    proposal = alice.get(f"/api/proposals/{pid}").json()
    assert proposal["status"] == "pending_owner"
    statuses = {m["display_name"]: m["status"] for m in proposal["members"]}
    assert statuses["Jordan"] == "declined" and statuses["Taylor"] == "suggested"
    assert jordan.get(f"/api/proposals/{pid}").status_code == 404
    assert not any(s == "invited" for s in statuses.values())  # never auto-invite

    # member view hides suggested/passed/declined people and reasons
    seen = sofia.get(f"/api/proposals/{pid}").json()
    assert {m["display_name"] for m in seen["members"]} == {"Alice", "Sofia"}
    assert all(m["reason"] is None for m in seen["members"]) and seen["venue_label"] is None

    # 5. owner approves Taylor, Taylor accepts
    approve(alice, pid, users["taylor"])
    taylor.post(f"/api/proposals/{pid}/respond", {"accept": True})

    # 6. finalize and unanimous confirmation of the current version
    final = alice.post(f"/api/proposals/{pid}/finalize", {"venue_label": "Reading Terminal Market (public food hall)", "venue_category": "food_hall"}).json()
    assert final["status"] == "awaiting_final"
    v = final["version"]
    assert alice.post(f"/api/proposals/{pid}/confirm", {"version": v}).json()["status"] == "awaiting_final"
    assert sofia.post(f"/api/proposals/{pid}/confirm", {"version": v}).json()["status"] == "awaiting_final"
    assert alice.get(f"/api/proposals/{pid}/messages").status_code == 404  # room opens only when confirmed
    done = taylor.post(f"/api/proposals/{pid}/confirm", {"version": v}).json()
    assert done["status"] == "confirmed" and done["venue_label"].startswith("Reading Terminal")
    assert {m["display_name"] for m in done["members"]} == {"Alice", "Sofia", "Taylor"}

    # 7. Gather Room: icebreaker from the agent, then participants chat
    [ice] = sofia.get(f"/api/proposals/{pid}/messages").json()
    assert ice["sender_id"] is None and ice["sender_name"] == "Gather Agent"
    assert sofia.post(f"/api/proposals/{pid}/messages", {"body": "Hi all!"}).status_code == 201
    assert [m["body"] for m in taylor.get(f"/api/proposals/{pid}/messages").json()][-1] == "Hi all!"

    # 8. outsiders see nothing, identically
    for outsider in (eve, maya, jordan):
        for url in (f"/api/proposals/{pid}", f"/api/proposals/{pid}/messages"):
            res = outsider.get(url)
            assert res.status_code == 404 and res.json() == {"detail": "Not found"}

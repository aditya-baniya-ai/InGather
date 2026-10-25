"""Proposal state machine: consent gates, versioning, decline->outbox->replan, chat access."""

from datetime import timedelta
from uuid import UUID

import pytest

from app.models import AgentRun, Message, OutboxEvent, ProposalMember, now
from app.services.outbox import Outbox
from app.services.proposals import Proposals
from tests.helpers import approve, members, start_agent

pytestmark = pytest.mark.usefixtures("fake_agent")


@pytest.fixture
def flow(users, plan_of, as_user):
    """Alice's agent ran; returns (alice api, proposal id)."""
    alice = as_user(users["alice"])
    return alice, start_agent(alice, plan_of(users["alice"]).id)["proposal_id"]


def accept(as_user, users, pid, *names):
    for name in names:
        assert as_user(users[name]).post(f"/api/proposals/{pid}/respond", {"accept": True}).status_code == 200


def test_approve_rejects_unsuggested_ids_and_stale_versions(users, as_user, flow):
    alice, pid = flow
    version = alice.get(f"/api/proposals/{pid}").json()["version"]
    url = f"/api/proposals/{pid}/approve-invitations"
    for ids, v in (([users["taylor"].id], version), ([users["eve"].id], version), ([users["sofia"].id], version + 1)):
        res = alice.post(url, {"version": v, "user_ids": [str(i) for i in ids]})
        assert res.status_code == 409
    assert alice.post(url, {"version": version, "user_ids": []}).status_code == 422
    assert all(m["status"] != "invited" for m in members(alice, pid).values())
    assert as_user(users["taylor"]).get("/api/invitations").json() == []


def test_cannot_approve_after_owner_passed(users, flow):
    alice, pid = flow
    alice.post(f"/api/proposals/{pid}/members/{users['maya'].id}/pass", {})
    version = alice.get(f"/api/proposals/{pid}").json()["version"]
    res = alice.post(f"/api/proposals/{pid}/approve-invitations", {"version": version, "user_ids": [str(users["maya"].id)]})
    assert res.status_code == 409


def test_pass_only_suggested_members(users, as_user, flow):
    alice, pid = flow
    approve(alice, pid, users["sofia"])
    assert alice.post(f"/api/proposals/{pid}/members/{users['sofia'].id}/pass", {}).status_code == 409
    assert alice.post(f"/api/proposals/{pid}/members/{users['eve'].id}/pass", {}).status_code == 404


def test_respond_is_idempotent_and_single_use(users, as_user, flow):
    alice, pid = flow
    approve(alice, pid, users["sofia"], users["jordan"])
    sofia = as_user(users["sofia"])
    assert sofia.post(f"/api/proposals/{pid}/respond", {"accept": True}).json()["my_status"] == "accepted"
    assert sofia.post(f"/api/proposals/{pid}/respond", {"accept": True}).json()["my_status"] == "accepted"
    jordan = as_user(users["jordan"])
    assert jordan.post(f"/api/proposals/{pid}/respond", {"accept": False}).json()["my_status"] == "declined"
    assert jordan.post(f"/api/proposals/{pid}/respond", {"accept": True}).status_code == 404  # replay can't re-join


def test_expired_invitation_cannot_be_accepted(db, users, as_user, flow):
    alice, pid = flow
    approve(alice, pid, users["sofia"])
    member = db.query(ProposalMember).filter_by(proposal_id=UUID(pid), user_id=users["sofia"].id).one()
    assert member.expires_at is not None
    member.expires_at = now() - timedelta(minutes=1)
    db.commit()
    res = as_user(users["sofia"]).post(f"/api/proposals/{pid}/respond", {"accept": True})
    assert res.status_code == 409 and res.json() == {"detail": "invitation_expired"}


def test_decline_enqueues_outbox_and_never_confirms_stale_roster(db, users, as_user, flow, fake_agent):
    alice, pid = flow
    approve(alice, pid, users["sofia"], users["jordan"])
    accept(as_user, users, pid, "sofia")
    assert alice.post(f"/api/proposals/{pid}/finalize", {}).json() == {"detail": "invites_pending"}

    as_user(users["jordan"]).post(f"/api/proposals/{pid}/respond", {"accept": False})
    event = db.query(OutboxEvent).filter_by(kind="invitation_declined", aggregate_id=UUID(pid)).one()
    assert event.processed_at is not None and event.attempts == 1
    assert db.query(AgentRun).filter_by(trigger="decline").count() == 1
    assert users["jordan"].id in fake_agent.started[-1][1]

    final = alice.post(f"/api/proposals/{pid}/finalize", {}).json()
    for name in ("alice", "sofia"):
        out = as_user(users[name]).post(f"/api/proposals/{pid}/confirm", {"version": final["version"]}).json()
    assert out["status"] == "confirmed"
    assert {m["display_name"] for m in out["members"]} == {"Alice", "Sofia"}


def test_outbox_is_processed_once(db, settings, users, as_user, flow):
    alice, pid = flow
    approve(alice, pid, users["sofia"])
    as_user(users["sofia"]).post(f"/api/proposals/{pid}/respond", {"accept": False})
    assert Outbox(db, settings).process() == 0  # already handled by the background task


def test_changing_final_details_resets_confirmations(users, as_user, flow):
    alice, pid = flow
    approve(alice, pid, users["sofia"])
    accept(as_user, users, pid, "sofia")
    sofia = as_user(users["sofia"])
    v1 = alice.post(f"/api/proposals/{pid}/finalize", {}).json()["version"]
    assert sofia.post(f"/api/proposals/{pid}/confirm", {"version": v1}).json()["i_confirmed"] is True

    changed = alice.post(f"/api/proposals/{pid}/finalize", {"venue_label": "Free Library (public)", "venue_category": "library"}).json()
    assert changed["version"] == v1 + 1
    assert all(not m["confirmed"] for m in changed["members"])
    assert sofia.get(f"/api/proposals/{pid}").json()["i_confirmed"] is False
    assert sofia.post(f"/api/proposals/{pid}/confirm", {"version": v1}).json() == {"detail": "stale_version"}
    alice.post(f"/api/proposals/{pid}/confirm", {"version": changed["version"]})
    assert sofia.post(f"/api/proposals/{pid}/confirm", {"version": changed["version"]}).json()["status"] == "confirmed"


def test_finalize_validation(users, as_user, flow):
    alice, pid = flow
    assert alice.post(f"/api/proposals/{pid}/finalize", {}).json() == {"detail": "no_accepted_members"}
    approve(alice, pid, users["sofia"])
    accept(as_user, users, pid, "sofia")
    bad = {"start_at": "2027-01-17T23:00:00Z", "end_at": "2027-01-17T22:00:00Z"}
    assert alice.post(f"/api/proposals/{pid}/finalize", bad).json() == {"detail": "invalid_time"}
    assert alice.post(f"/api/proposals/{pid}/finalize", {"venue_category": "hotel_room"}).status_code == 422
    assert as_user(users["sofia"]).post(f"/api/proposals/{pid}/finalize", {}).status_code == 404


def test_member_leaving_during_final_step_bumps_version(users, as_user, flow):
    alice, pid = flow
    approve(alice, pid, users["sofia"], users["jordan"])
    accept(as_user, users, pid, "sofia", "jordan")
    v = alice.post(f"/api/proposals/{pid}/finalize", {}).json()["version"]
    alice.post(f"/api/proposals/{pid}/confirm", {"version": v})
    assert as_user(users["jordan"]).post(f"/api/proposals/{pid}/leave").status_code == 204
    after = alice.get(f"/api/proposals/{pid}").json()
    assert after["version"] == v + 1 and after["i_confirmed"] is False and "Jordan" not in members(alice, pid)


def test_messages_only_for_confirmed_participants(db, users, as_user, flow):
    alice, pid = flow
    approve(alice, pid, users["sofia"], users["jordan"])
    accept(as_user, users, pid, "sofia")
    as_user(users["jordan"]).post(f"/api/proposals/{pid}/respond", {"accept": False})
    v = alice.post(f"/api/proposals/{pid}/finalize", {}).json()["version"]
    sofia = as_user(users["sofia"])
    assert sofia.post(f"/api/proposals/{pid}/messages", {"body": "early"}).status_code == 404
    alice.post(f"/api/proposals/{pid}/confirm", {"version": v})
    sofia.post(f"/api/proposals/{pid}/confirm", {"version": v})
    assert db.query(Message).filter_by(proposal_id=UUID(pid), sender_id=None).count() == 1

    assert sofia.post(f"/api/proposals/{pid}/messages", {"body": ""}).status_code == 422
    assert sofia.post(f"/api/proposals/{pid}/messages", {"body": "   "}).status_code == 422
    assert sofia.post(f"/api/proposals/{pid}/messages", {"body": "x" * 1001}).status_code == 422
    for outsider in ("jordan", "maya", "eve"):
        assert as_user(users[outsider]).post(f"/api/proposals/{pid}/messages", {"body": "hi"}).status_code == 404
    codes = [sofia.post(f"/api/proposals/{pid}/messages", {"body": f"m{i}"}).status_code for i in range(31)]
    assert codes.count(201) == 30 and codes[-1] == 429
    sofia.post(f"/api/proposals/{pid}/leave")
    assert sofia.get(f"/api/proposals/{pid}/messages").status_code == 404


def test_replan_endpoint_adds_suggestions_without_inviting(users, as_user, flow):
    alice, pid = flow
    alice.post(f"/api/proposals/{pid}/members/{users['jordan'].id}/pass", {})
    alice.post(f"/api/proposals/{pid}/members/{users['taylor'].id}/pass", {})
    res = alice.post(f"/api/proposals/{pid}/replan", {"feedback": "schedule"})
    assert res.status_code == 202 and res.json()["trigger"] == "feedback"
    statuses = {k: v["status"] for k, v in members(alice, pid).items()}
    assert statuses["Jordan"] == statuses["Taylor"] == "passed"
    assert "invited" not in statuses.values()


class TestSaveAgentResult:
    @pytest.fixture
    def ctx(self, db, settings, users, plan_of):
        plan = plan_of(users["alice"])
        run = AgentRun(plan_id=plan.id, owner_id=users["alice"].id, excluded_user_ids=[str(users["taylor"].id)])
        db.add(run)
        db.commit()
        return Proposals(db, settings), run, plan

    @staticmethod
    def save(ctx, *people):
        svc, run, plan = ctx
        return svc.save_agent_result(run, plan, [(p.id, "r") for p in people], "T", "E", None, None, "Café", "cafe", None)

    def test_valid_picks_create_proposal_with_owner(self, ctx, users):
        proposal = self.save(ctx, users["sofia"], users["jordan"])
        assert ctx[1].proposal_id == proposal.id and proposal.status == "pending_owner"
        roles = {m.user_id: (m.status, m.is_initiator) for m in proposal.members}
        assert roles[users["alice"].id] == ("accepted", True) and roles[users["sofia"].id] == ("suggested", False)
        assert proposal.start_at is not None and proposal.venue_verified is False

    def test_second_save_attaches_and_bumps_version(self, ctx, users):
        first = self.save(ctx, users["sofia"])
        second = self.save(ctx, users["jordan"])
        assert first.id == second.id and second.version == 2

    @pytest.mark.parametrize("names", [("eve",), ("taylor",), ("noah",), ("diego",), ("alice",), ("sofia", "sofia")])
    def test_ineligible_or_excluded_picks_rejected(self, ctx, users, names):
        with pytest.raises(ValueError):
            self.save(ctx, *(users[n] for n in names))

    def test_group_max_respected(self, ctx, users):
        with pytest.raises(ValueError):
            self.save(ctx, users["sofia"], users["jordan"], users["maya"], users["priya"])

    def test_infeasible_group_rejected(self, ctx, users):
        with pytest.raises(ValueError):
            self.save(ctx, users["maya"], users["marcus"])

    def test_agent_time_outside_common_window_is_replaced(self, ctx, users):
        svc, run, plan = ctx
        p = svc.save_agent_result(
            run, plan, [(users["sofia"].id, "r")], "T", "E", "2027-01-17T12:00:00Z", "2027-01-17T13:00:00Z", "Café", "hotel", None
        )
        assert p.start_at.isoformat().startswith("2027-01-17T23:00") and p.venue_category == "cafe"


def test_mapped_venue_disclosure_selection_and_manual_changes(db, users, as_user, flow, monkeypatch):
    from app.services import places
    from app.models import Plan, Proposal
    alice, pid = flow
    proposal = db.get(Proposal, UUID(pid))
    plan = db.get(Plan, proposal.plan_id)
    plan.public_location = 'Public Conference Venue'
    place = {'id': 'node/123', 'name': 'Actual Café', 'category': 'cafe', 'latitude': 39.955,
        'longitude': -75.16, 'address': '100 Arch St', 'distance_m': 120, 'source': 'OpenStreetMap'}
    proposal.venue_label, proposal.venue_details = place['name'], place
    db.commit()
    monkeypatch.setattr(places, 'nearby', lambda *a: {'status': 'ok', 'places': [place], 'message': 'Mapped results', 'origin': {'label': 'Private event anchor'}})
    assert alice.get(f'/api/plans/{plan.id}/nearby').status_code == 200
    assert as_user(users['sofia']).get(f'/api/plans/{plan.id}/nearby').status_code == 404
    approve(alice, pid, users['sofia'])
    sofia = as_user(users['sofia'])
    assert sofia.get(f'/api/proposals/{pid}').json()['venue_details'] is None
    accept(as_user, users, pid, 'sofia')
    assert sofia.get(f'/api/proposals/{pid}').json()['venue_details'] is None
    selected = alice.post(f'/api/proposals/{pid}/finalize', {'venue_place_id': 'node/123'}).json()
    assert selected['venue_details'] == place and selected['venue_label'] == place['name']
    disclosed = sofia.get(f'/api/proposals/{pid}').json()
    assert disclosed['venue_details'] == place and 'public_location' not in disclosed and 'origin' not in disclosed
    rejected = alice.post(f'/api/proposals/{pid}/finalize', {'venue_place_id': 'node/forged'})
    assert rejected.status_code == 409
    changed = alice.post(f'/api/proposals/{pid}/finalize', {'venue_label': 'A different public café'}).json()
    assert changed['venue_details'] is None and changed['version'] > selected['version']
    assert not any(m['confirmed'] for m in changed['members'])

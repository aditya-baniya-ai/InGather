"""The gather engine end to end on the seeded demo data, with the real ML matcher (no stand-ins)."""

import pytest
from sqlalchemy import select

from app.models import AgentEvent, AgentRun, Block, MemberStatus, Plan, PlanStatus, Proposal, RunStatus
from app.services import places
from app.services.gather import GatherEngine, start_run
from app.services.proposals import Proposals

STEPS = {"gather", "matcher", "scheduler", "venue", "checks"}


@pytest.fixture
def gather(db, settings):
    def go(owner, plan, trigger="user", goal="", excluded=()):
        run = start_run(db, owner, plan, trigger, goal=goal, excluded=set(excluded))
        GatherEngine(db, settings).run(run.id)
        db.expire_all()
        return db.get(AgentRun, run.id)

    return go


def events(db, run) -> list[AgentEvent]:
    return list(db.scalars(select(AgentEvent).where(AgentEvent.run_id == run.id).order_by(AgentEvent.seq)))


def roster(db, run) -> dict[str, MemberStatus]:
    p = db.get(Proposal, run.proposal_id)
    return {m.user.display_name: m.status for m in p.members if not m.is_initiator}


def test_alice_gets_a_compatible_group_at_a_public_place(db, users, plan_of, gather):
    run = gather(users["alice"], plan_of(users["alice"]))
    assert run.status == RunStatus.completed and run.mode == "ml" and run.model == "matcher-1", run.error
    people = roster(db, run)
    assert set(people) == {"Maya", "Jordan"} and set(people.values()) == {MemberStatus.suggested}
    proposal = db.get(Proposal, run.proposal_id)
    assert proposal.venue_category == "cafe" and "Philadelphia" in proposal.venue_label
    assert (proposal.end_at - proposal.start_at).total_seconds() == 90 * 60  # 5:30-7pm: Maya until 7, Jordan from 5:30
    assert proposal.start_at.hour == 22 and proposal.start_at.minute == 30
    reasons = {m.user.display_name: m.reason for m in proposal.members if not m.is_initiator}
    assert reasons["Maya"].startswith("Shares tech, food and city exploring") and "conference" in reasons["Maya"]
    log = events(db, run)
    assert {e.agent for e in log} == STEPS
    assert [e.tool_name for e in log if e.kind == "tool"] == [
        "find_eligible_candidates", "score_candidates", "check_group_availability", "propose_group"]
    assert any(e.kind == "review" and e.agent == "checks" for e in log)
    assert not any("Muse Spark" in e.summary for e in log)


def test_never_suggests_blocked_private_or_other_city_people(db, users, plan_of, gather):
    db.add(Block(blocker_id=users["maya"].id, blocked_id=users["alice"].id))  # blocks work in both directions
    db.commit()
    run = gather(users["alice"], plan_of(users["alice"]))
    people = set(roster(db, run))
    assert people and not people & {"Maya", "Eve", "Noah", "Diego"}


def test_pass_replans_keeps_the_others_and_never_resuggests(db, users, plan_of, settings, gather):
    plan = plan_of(users["alice"])
    first = gather(users["alice"], plan)
    proposal = db.get(Proposal, first.proposal_id)
    svc = Proposals(db, settings)
    svc.pass_member(proposal, users["maya"].id)
    second = gather(users["alice"], plan, "pass", excluded=svc.exclusions(plan))
    assert second.status == RunStatus.completed and second.proposal_id == first.proposal_id
    people = roster(db, second)
    assert people["Maya"] == MemberStatus.passed and people["Jordan"] == MemberStatus.suggested
    assert len([s for s in people.values() if s == MemberStatus.suggested]) >= 2  # an open slot was filled
    assert db.get(Proposal, second.proposal_id).version == 2
    assert events(db, second)[0].summary.startswith("Replanning: you passed")


def test_note_interests_are_used_for_the_run(db, users, plan_of, gather):
    run = gather(users["alice"], plan_of(users["alice"]), goal="Also people into jazz please")
    assert any(e.summary == "Also matching on interests from your note: jazz" for e in events(db, run))


def test_prefer_group_feedback_fills_the_group(db, users, plan_of, gather):
    from app.services.runs import FEEDBACK_HINTS

    run = gather(users["alice"], plan_of(users["alice"]), "feedback", goal=FEEDBACK_HINTS["prefer_group"])
    assert run.status == RunStatus.completed and len(roster(db, run)) == 3  # group_max 4 including Alice


def test_no_one_available_ends_cleanly(db, users, plan_of, gather):
    for p in db.scalars(select(Plan).where(Plan.owner_id != users["alice"].id)):
        p.status = PlanStatus.cancelled
    db.commit()
    run = gather(users["alice"], plan_of(users["alice"]))
    assert run.status == RunStatus.failed and run.error == "no_suitable_group" and run.proposal_id is None
    assert events(db, run)[-1].summary == "Run ended without a proposal (no_suitable_group)"


def test_paused_plan_is_not_searched(db, users, plan_of, gather):
    plan = plan_of(users["alice"])
    plan.status = PlanStatus.paused
    db.commit()
    run = gather(users["alice"], plan)
    assert run.status == RunStatus.failed and run.error == "plan_inactive"
    assert not any(e.kind == "tool" for e in events(db, run))


def test_uses_the_nearest_mapped_public_place(db, users, plan_of, gather, monkeypatch):
    plan = plan_of(users["alice"])
    plan.public_location = "Pennsylvania Convention Center"
    db.commit()
    found = [
        {"name": "Hotel Lobby Bar", "category": "restaurant", "distance_m": 50, "lat": 39.95, "lon": -75.16},
        {"name": "Reading Terminal Market", "category": "food_hall", "distance_m": 120, "lat": 39.953, "lon": -75.159},
        {"name": "La Colombe", "category": "cafe", "distance_m": 300, "lat": 39.951, "lon": -75.163},
    ]
    monkeypatch.setattr(places, "nearby", lambda *a, **k: {"status": "ok", "places": found, "message": "OK."})
    run = gather(users["alice"], plan)
    proposal = db.get(Proposal, run.proposal_id)
    assert proposal.venue_label == "La Colombe" and proposal.venue_details["category"] == "cafe"
    assert any(e.tool_name == "find_nearby_places" for e in events(db, run))


def test_only_the_owner_can_start_a_run(db, users, plan_of):
    with pytest.raises(PermissionError):
        start_run(db, users["eve"], plan_of(users["alice"]), "user")

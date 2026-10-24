"""Gather Agent loop (fake Muse Spark), offline rules mode, replans and failure handling."""

import json
from datetime import datetime, timedelta

from sqlalchemy import select

from app.ai import orchestrator
from app.ai.orchestrator import GatherAgent, start_run
from app.models import AgentEvent, AgentRun, MemberStatus, Proposal, RunStatus
from tests.ai.fakes import FakeClient, call, say


def events(db, run):
    return list(db.scalars(select(AgentEvent).where(AgentEvent.run_id == run.id).order_by(AgentEvent.seq)))


def proposal_of(db, run) -> Proposal:
    db.expire_all()
    return db.get(Proposal, db.get(AgentRun, run.id).proposal_id)


def happy_script(pick=lambda cands: [c["candidate_id"] for c in cands[:2]]):
    chosen = {}

    def s1(_):
        return [say("Let me look at your plan and who is around."), call("get_my_plan_context", {}),
                call("find_eligible_candidates", {"excluded_candidate_ids": []})]

    def s2(out):
        chosen["ids"] = pick(out["call_find_eligible_candidates"]["candidates"])
        return [call("check_group_availability", {"candidate_ids": chosen["ids"]})]

    def s3(out):
        w = out["call_check_group_availability"]["windows"][0]
        start = datetime.fromisoformat(w["start"])
        a, b = chosen["ids"]
        return [call("propose_group", {
            "candidate_ids": [a, b], "activity_title": "Museum + coffee after sessions",
            "explanation": f"{a} and {b} both like AI and museums, and everyone is free Sunday afternoon.",
            "start_at": start.isoformat(), "end_at": (start + timedelta(hours=1)).isoformat(),
            "venue_label": "A café near the convention center", "venue_category": "cafe",
            "icebreaker": "What talk are you most excited about?",
            "reasons": [{"candidate_id": a, "reason": f"{a} shares ai"}, {"candidate_id": b, "reason": "Shares museums"}],
        })]

    def s4(_):
        return [say("I suggested a group of 3. Nobody is invited until you approve.")]

    return [s1, s2, s3, s4]


def test_live_loop_executes_tools_and_chains_previous_response_id(db, settings, world):
    run = start_run(db, world["alice"], world["plan"], "user")
    client = FakeClient(happy_script())
    GatherAgent(db, settings, client=client).run(run.id)

    db.refresh(run)
    assert run.status == RunStatus.completed and run.mode == "live" and run.model == settings.meta_model
    reqs = client.responses.requests
    assert len(reqs) == 4 and "previous_response_id" not in reqs[0]
    for i in (1, 2, 3):
        assert reqs[i]["previous_response_id"] == f"resp_{i}"
        assert all(x["type"] == "function_call_output" for x in reqs[i]["input"])
        assert reqs[i]["tools"] and "Gather Agent" in reqs[i]["instructions"]
    assert {x["call_id"] for x in reqs[1]["input"]} == {"call_get_my_plan_context", "call_find_eligible_candidates"}

    p = proposal_of(db, run)
    suggested = [m for m in p.members if m.status == MemberStatus.suggested]
    assert len(suggested) == 2 and p.venue_category == "cafe" and not p.venue_verified
    assert "cand_" not in p.explanation + "".join(m.reason for m in suggested)  # handles swapped for display names
    kinds = [(e.kind, e.tool_name) for e in events(db, run)]
    assert [t for k, t in kinds if k == "tool"] == [
        "get_my_plan_context", "find_eligible_candidates", "check_group_availability", "propose_group"]
    assert ("model", None) in kinds and kinds[-1] == ("system", None)
    assert run.summary.startswith("I suggested a group")


def test_unknown_tool_is_rejected_and_run_fails_honestly(db, settings, world):
    run = start_run(db, world["alice"], world["plan"], "user")
    client = FakeClient([lambda _: [call("send_invitations", {"to": "everyone"})], lambda o: [say("I couldn't do that.")]])
    GatherAgent(db, settings, client=client).run(run.id)
    db.refresh(run)
    assert run.status == RunStatus.failed and run.error == "no_suitable_group" and run.proposal_id is None
    out = json.loads(client.responses.requests[1]["input"][0]["output"])
    assert "unknown tool" in out["error"]
    assert any(e.kind == "error" and e.tool_name == "send_invitations" for e in events(db, run))
    assert not any(e.kind == "tool" for e in events(db, run))


def test_round_limit_fails_without_proposal(db, settings, world):
    settings.agent_max_tool_rounds = 2
    run = start_run(db, world["alice"], world["plan"], "user")
    loop = lambda _: [call("get_my_plan_context", {})]  # noqa: E731
    GatherAgent(db, settings, client=FakeClient([loop] * 10)).run(run.id)
    db.refresh(run)
    assert run.status == RunStatus.failed and run.error == "tool_round_limit"
    assert sum(e.kind == "tool" for e in events(db, run)) == 2


def test_api_exception_fails_with_safe_error(db, settings, world):
    class APITimeoutError(Exception):
        pass

    run = start_run(db, world["alice"], world["plan"], "user")
    GatherAgent(db, settings, client=FakeClient(raise_exc=APITimeoutError("key sk-secret-123 at /v1"))).run(run.id)
    db.refresh(run)
    assert run.status == RunStatus.failed and run.error == "Muse Spark request failed (APITimeoutError)"
    assert all("sk-secret" not in e.summary for e in events(db, run))


def test_offline_mode_produces_labeled_proposal(db, settings, world):
    run = start_run(db, world["alice"], world["plan"], "user")
    assert run.mode == "offline"
    GatherAgent(db, settings).run(run.id)
    db.refresh(run)
    assert run.status == RunStatus.completed and run.mode == "offline" and run.model is None
    evs = events(db, run)
    assert "not Muse Spark" in evs[1].summary
    tools = [e for e in evs if e.kind == "tool"]
    assert tools and all(e.summary.startswith("Rules-based: ") for e in tools)
    assert not any(e.kind == "model" for e in evs)  # no fabricated model narration offline
    p = proposal_of(db, run)
    picked = {m.user_id for m in p.members if m.status == MemberStatus.suggested}
    assert len(picked) == 2 and world["eve"].id not in picked and world["zed"].id not in picked
    assert "Rules-based" in p.explanation


def test_replan_after_pass_excludes_passed_user(db, settings, world):
    first = start_run(db, world["alice"], world["plan"], "user")
    GatherAgent(db, settings).run(first.id)
    p = proposal_of(db, first)
    passed = next(m for m in p.members if m.status == MemberStatus.suggested)
    kept = next(m for m in p.members if m.status == MemberStatus.suggested and m is not passed)
    passed.status = MemberStatus.passed
    db.commit()

    seen_ctx = {}

    def s1(_):
        return [call("get_my_plan_context", {}), call("find_eligible_candidates", {"excluded_candidate_ids": []})]

    def s2(out):
        seen_ctx.update(out)
        ids = [c["candidate_id"] for c in out["call_find_eligible_candidates"]["candidates"]][:1]
        seen_ctx["ids"] = ids
        return [call("check_group_availability", {"candidate_ids": ids})]

    def s3(out):
        w = out["call_check_group_availability"]["windows"][0]
        s = datetime.fromisoformat(w["start"])
        (a,) = seen_ctx["ids"]
        return [call("propose_group", {
            "candidate_ids": [a], "activity_title": "Coffee", "explanation": f"{a} fills the open spot.",
            "start_at": s.isoformat(), "end_at": (s + timedelta(minutes=90)).isoformat(),
            "venue_label": "A public café downtown", "venue_category": "cafe", "icebreaker": "Hi!",
            "reasons": [{"candidate_id": a, "reason": "Shares coffee"}]})]

    run = start_run(db, world["alice"], world["plan"], "pass", excluded={passed.user_id})
    client = FakeClient([s1, s2, s3])
    GatherAgent(db, settings, client=client).run(run.id)
    db.refresh(run)
    assert run.status == RunStatus.completed, run.error
    ctx = seen_ctx["call_get_my_plan_context"]
    assert ctx["trigger"] == "pass" and ctx["already_in_group"] == 1 and ctx["new_people_to_suggest"] == {"min": 1, "max": 1}
    assert "passed" in client.responses.requests[0]["input"][0]["content"]  # counts only, no names
    assert world[passed.user.display_name.lower()].display_name not in client.responses.requests[0]["input"][0]["content"]
    p = proposal_of(db, run)
    statuses = {m.user_id: m.status for m in p.members}
    assert statuses[passed.user_id] == MemberStatus.passed and statuses[kept.user_id] == MemberStatus.suggested
    assert sum(s == MemberStatus.suggested for s in statuses.values()) == 2 and p.version == 2


def test_run_in_background_uses_own_session(db, settings, world, monkeypatch):
    run = start_run(db, world["alice"], world["plan"], "user")
    calls = []
    real = orchestrator.SessionLocal
    monkeypatch.setattr(orchestrator, "SessionLocal", lambda: calls.append(1) or real())
    orchestrator.run_in_background(run.id)
    db.expire_all()
    assert calls and db.get(AgentRun, run.id).status == RunStatus.completed

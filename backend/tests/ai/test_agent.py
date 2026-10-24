"""Agent orchestra (fake Muse Spark per agent), offline rules mode, review/retry, allowlists and failure handling."""

import json
import threading
from datetime import datetime, timedelta

from sqlalchemy import select

from app.ai import orchestrator
from app.ai.orchestrator import GatherAgent, start_run
from app.models import AgentEvent, AgentRun, MemberStatus, Proposal, RunStatus
from tests.ai.fakes import OrchestraClient, answer, call, say

AGENTS = {"orchestrator", "matchmaker", "scheduler", "planner", "reviewer"}


def events(db, run):
    return list(db.scalars(select(AgentEvent).where(AgentEvent.run_id == run.id).order_by(AgentEvent.seq)))


def proposal_of(db, run) -> Proposal | None:
    db.expire_all()
    pid = db.get(AgentRun, run.id).proposal_id
    return pid and db.get(Proposal, pid)


DESIGN = {
    "activity_title": "Museum + coffee after sessions", "venue_category": "cafe",
    "venue_label": "A café near the convention center", "icebreaker": "What talk are you most excited about?",
    "explanation": "You all like AI and museums, so a relaxed coffee fits.", "note": "Planned coffee at a public café.",
}


def verdicts(**rejected):
    return answer({"verdicts": [
        {"agent": a, "approved": a not in rejected, "reason": rejected.get(a, "Looks good.")}
        for a in ("matchmaker", "scheduler", "planner")
    ]})


class Script:
    """Per-agent scripts sharing state (the handles the matchmaker shortlisted, the window the scheduler saw)."""

    def __init__(self, parallel_barrier=True):
        self.st: dict = {}
        self.barrier = threading.Barrier(2, timeout=5) if parallel_barrier else None

    def sync(self):
        if self.barrier:
            self.barrier.wait()  # only passes if scheduler and planner are in flight at the same time

    def matchmaker(self):
        def s1(_o, _r):
            return [say("Reading your plan."), call("get_my_plan_context", {}), call("find_eligible_candidates", {"excluded_candidate_ids": []})]

        def s2(out, _r):
            cands = out["call_find_eligible_candidates"]["candidates"]
            self.st["ids"] = [c["candidate_id"] for c in cands[:3]]
            return [answer({"shortlist": [{"candidate_id": h, "reason": f"{h} shares ai"} for h in self.st["ids"]],
                            "note": f"Shortlisted {self.st['ids'][0]} and others."})]

        return [s1, s2]

    def scheduler(self, offset_hours=0):
        def s1(_o, _r):
            self.sync()
            return [call("check_group_availability", {"candidate_ids": self.st["ids"][:2]})]

        def s2(out, _r):
            self.st["window"] = w = out["call_check_group_availability"]["windows"][0]
            return [self.slot(w, offset_hours)]

        return [s1, s2]

    def slot(self, w, offset_hours=0):
        start = datetime.fromisoformat(w["start"]) + timedelta(hours=offset_hours)
        return answer({"candidate_ids": self.st["ids"][:2], "start_at": start.isoformat(),
                       "end_at": (start + timedelta(hours=1)).isoformat(), "note": "Everyone is free Sunday."})

    def planner(self, design=DESIGN):
        def s1(_o, _r):
            self.sync()
            return [answer(design)]

        return [s1]


def test_orchestra_runs_each_agent_with_its_own_tools_in_parallel(db, settings, world):
    run = start_run(db, world["alice"], world["plan"], "user")
    sc = Script()
    client = OrchestraClient(
        matchmaker=sc.matchmaker(), scheduler=sc.scheduler(), planner=sc.planner(), reviewer=[lambda o, r: [verdicts()]],
    )
    agent = GatherAgent(db, settings, client=client)
    agent.run(run.id)

    db.refresh(run)
    assert run.status == RunStatus.completed and run.mode == "live" and run.model == settings.meta_model, run.error
    reqs = client.responses.requests
    tools = {a: {t["name"] for t in reqs[a][0].get("tools", [])} for a in reqs}
    assert tools == {"matchmaker": {"get_my_plan_context", "find_eligible_candidates"},
                     "scheduler": {"check_group_availability"}, "planner": set(), "reviewer": set()}
    assert all(r["text"]["format"]["type"] == "json_schema" for rs in reqs.values() for r in rs)
    assert len({reqs[a][0]["instructions"] for a in reqs}) == 4  # separate conversations, separate instructions
    assert reqs["matchmaker"][1]["previous_response_id"] == "resp_matchmaker_1"
    assert "previous_response_id" not in reqs["scheduler"][0] and "previous_response_id" not in reqs["planner"][0]
    # parallel (the barrier proved overlap); planner ran off the main thread and never saw a handle or a name
    main = threading.get_ident()
    assert client.responses.threads["scheduler"] == {main} and main not in client.responses.threads["planner"]
    planner_input = json.dumps(reqs["planner"][0]["input"])
    assert "cand_" not in planner_input and "Bob" not in planner_input and "secret goal" not in planner_input
    assert set(agent.timings) == {"matchmaker", "scheduler", "planner", "reviewer"}

    p = proposal_of(db, run)
    suggested = [m for m in p.members if m.status == MemberStatus.suggested]
    assert len(suggested) == 2 and p.venue_category == "cafe" and not p.venue_verified
    assert "cand_" not in p.explanation + "".join(m.reason for m in suggested) and "Suggested time:" in p.explanation

    evs = events(db, run)
    assert all(e.agent in AGENTS for e in evs)
    assert [(e.tool_name, e.agent) for e in evs if e.kind == "tool"] == [
        ("get_my_plan_context", "matchmaker"), ("find_eligible_candidates", "matchmaker"),
        ("check_group_availability", "scheduler"), ("propose_group", "orchestrator")]
    model = {e.agent for e in evs if e.kind == "model"}
    assert model == {"matchmaker", "scheduler", "planner"}
    assert all("cand_" not in e.summary for e in evs)
    reviews = [e for e in evs if e.kind == "review"]
    assert len(reviews) == 3 and all(e.agent == "reviewer" and e.summary.startswith("Approved: ") for e in reviews)
    assert evs[-1].kind == "system" and evs[-1].agent == "orchestrator"
    assert run.summary.startswith("Suggested “Museum + coffee")


def test_reviewer_rejection_gets_one_retry_then_proposal_is_saved(db, settings, world):
    run = start_run(db, world["alice"], world["plan"], "user")
    sc = Script()
    fixed = {**DESIGN, "venue_label": "A public café near the convention center"}
    client = OrchestraClient(
        matchmaker=sc.matchmaker(), scheduler=sc.scheduler(),
        planner=[*sc.planner(), lambda o, r: [answer(fixed)]],
        reviewer=[lambda o, r: [verdicts(planner="Say it is a public café.")], lambda o, r: [verdicts()]],
    )
    GatherAgent(db, settings, client=client).run(run.id)
    db.refresh(run)
    assert run.status == RunStatus.completed, run.error
    retry = client.responses.requests["planner"][1]
    assert retry["previous_response_id"] == "resp_planner_1" and "Say it is a public café." in retry["input"][0]["content"]
    assert len(client.responses.requests["scheduler"]) == 2  # approved agents are not re-asked
    reviews = [e.summary for e in events(db, run) if e.kind == "review"]
    assert reviews[2] == "Sent back to planner: Say it is a public café." and len(reviews) == 6
    assert sum(s.startswith("Approved: ") for s in reviews) == 5
    assert proposal_of(db, run).venue_label == fixed["venue_label"]


def test_hard_checks_override_reviewer_approval(db, settings, world):
    """The scheduler picks a time outside the checked window; even an approving reviewer cannot let it through."""
    run = start_run(db, world["alice"], world["plan"], "user")
    sc = Script()
    client = OrchestraClient(
        matchmaker=sc.matchmaker(), scheduler=[*sc.scheduler(offset_hours=10), lambda o, r: [sc.slot(sc.st["window"])]],
        planner=sc.planner(), reviewer=[lambda o, r: [verdicts()], lambda o, r: [verdicts()]],
    )
    GatherAgent(db, settings, client=client).run(run.id)
    db.refresh(run)
    assert run.status == RunStatus.completed, run.error
    first_review = json.loads(client.responses.requests["reviewer"][0]["input"][0]["content"].split(": ", 1)[1])
    assert first_review["automated_checks"]["scheduler"]
    reviews = [e.summary for e in events(db, run) if e.kind == "review"]
    assert reviews[1].startswith("Sent back to scheduler: the time must fall inside a window")
    assert client.responses.requests["scheduler"][2]["previous_response_id"] == "resp_scheduler_2"


def test_double_rejection_fails_without_proposal(db, settings, world):
    run = start_run(db, world["alice"], world["plan"], "user")
    sc = Script()
    no = lambda o, r: [verdicts(scheduler="Pick a later, more sociable time.")]  # noqa: E731
    client = OrchestraClient(
        matchmaker=sc.matchmaker(), scheduler=[*sc.scheduler(), lambda o, r: [sc.slot(sc.st["window"])]],
        planner=sc.planner(), reviewer=[no, no],
    )
    GatherAgent(db, settings, client=client).run(run.id)
    db.refresh(run)
    assert run.status == RunStatus.failed and run.error == "review_rejected" and run.proposal_id is None
    assert db.scalars(select(Proposal).where(Proposal.plan_id == world["plan"].id)).first() is None
    assert not any(e.tool_name == "propose_group" for e in events(db, run))
    assert sum(e.summary.startswith("Sent back to scheduler:") for e in events(db, run)) == 2


def test_agents_cannot_call_tools_outside_their_allowlist(db, settings, world):
    run = start_run(db, world["alice"], world["plan"], "user")
    sc = Script(parallel_barrier=False)
    sneaky = lambda o, r: [call("find_eligible_candidates", {"excluded_candidate_ids": []}), call("propose_group", {})]  # noqa: E731
    seen = {}

    def after(out, r):
        seen.update(out)
        return sc.scheduler()[0](out, r)

    client = OrchestraClient(
        matchmaker=[lambda o, r: [call("send_invitations", {"to": "everyone"})], *sc.matchmaker()],
        scheduler=[sneaky, after, sc.scheduler()[1]],
        planner=[lambda o, r: [call("get_my_plan_context", {})], *sc.planner()],
        reviewer=[lambda o, r: [verdicts()]],
    )
    GatherAgent(db, settings, client=client).run(run.id)
    db.refresh(run)
    assert run.status == RunStatus.completed, run.error
    assert "not available to you" in seen["call_find_eligible_candidates"]["error"]
    errors = {(e.agent, e.tool_name) for e in events(db, run) if e.kind == "error"}
    assert errors == {("matchmaker", "send_invitations"), ("scheduler", "find_eligible_candidates"),
                      ("scheduler", "propose_group"), ("planner", "get_my_plan_context")}
    tools = [(e.agent, e.tool_name) for e in events(db, run) if e.kind == "tool"]
    assert ("scheduler", "find_eligible_candidates") not in tools and ("planner", "get_my_plan_context") not in tools
    assert tools.count(("orchestrator", "propose_group")) == 1


def test_round_limit_and_empty_shortlist_fail_honestly(db, settings, world):
    settings.agent_max_tool_rounds = 2
    run = start_run(db, world["alice"], world["plan"], "user")
    loop = lambda o, r: [call("get_my_plan_context", {})]  # noqa: E731
    GatherAgent(db, settings, client=OrchestraClient(matchmaker=[loop] * 10)).run(run.id)
    db.refresh(run)
    assert run.status == RunStatus.failed and run.error == "tool_round_limit"

    run2 = start_run(db, world["alice"], world["plan"], "user")
    client = OrchestraClient(matchmaker=[lambda o, r: [answer({"shortlist": [], "note": "Nobody fits right now."})]])
    GatherAgent(db, settings, client=client).run(run2.id)
    db.refresh(run2)
    assert run2.status == RunStatus.failed and run2.error == "no_suitable_group" and run2.proposal_id is None
    assert set(client.responses.requests) == {"matchmaker"}


def test_api_exception_fails_with_safe_error(db, settings, world):
    class APITimeoutError(Exception):
        pass

    run = start_run(db, world["alice"], world["plan"], "user")
    GatherAgent(db, settings, client=OrchestraClient(raise_exc=APITimeoutError("key sk-secret-123 at /v1"))).run(run.id)
    db.refresh(run)
    assert run.status == RunStatus.failed and run.error == "Muse Spark request failed (APITimeoutError)"
    assert all("sk-secret" not in e.summary for e in events(db, run))


def test_offline_orchestra_produces_labeled_proposal(db, settings, world):
    run = start_run(db, world["alice"], world["plan"], "user")
    assert run.mode == "offline"
    GatherAgent(db, settings).run(run.id)
    db.refresh(run)
    assert run.status == RunStatus.completed and run.mode == "offline" and run.model is None, run.error
    evs = events(db, run)
    assert "not Muse Spark" in evs[1].summary and all(e.agent in AGENTS for e in evs)
    tools = [e for e in evs if e.kind == "tool"]
    assert tools and all(e.summary.startswith("Rules-based: ") for e in tools)
    assert {e.agent for e in tools} == {"matchmaker", "scheduler", "orchestrator"}
    assert not any(e.kind == "model" for e in evs)  # no fabricated model narration offline
    notes = [e for e in evs if e.kind == "system" and e.agent in ("matchmaker", "scheduler", "planner")]
    assert {e.agent for e in notes} == {"matchmaker", "scheduler", "planner"} and all(e.summary.startswith("Rules-based: ") for e in notes)
    assert [e.summary.split(" — ")[0] for e in evs if e.kind == "review"] == [
        "Approved: matchmaker", "Approved: scheduler", "Approved: planner"]
    p = proposal_of(db, run)
    picked = {m.user_id for m in p.members if m.status == MemberStatus.suggested}
    assert len(picked) == 2 and world["eve"].id not in picked and world["zed"].id not in picked
    assert "Rules-based" in p.explanation


def test_replan_after_pass_excludes_passed_user(db, settings, world):
    first = start_run(db, world["alice"], world["plan"], "user")
    GatherAgent(db, settings).run(first.id)
    p = proposal_of(db, first)
    passed, kept = [m for m in p.members if m.status == MemberStatus.suggested]
    passed.status = MemberStatus.passed
    db.commit()

    run = start_run(db, world["alice"], world["plan"], "pass", excluded={passed.user_id})
    agent = GatherAgent(db, settings)
    agent.run(run.id)
    db.refresh(run)
    assert run.status == RunStatus.completed, run.error
    p = proposal_of(db, run)
    statuses = {m.user_id: m.status for m in p.members}
    assert statuses[passed.user_id] == MemberStatus.passed and statuses[kept.user_id] == MemberStatus.suggested
    assert sum(s == MemberStatus.suggested for s in statuses.values()) == 2 and p.version == 2


def test_replan_kickoff_shares_counts_not_names(db, settings, world):
    first = start_run(db, world["alice"], world["plan"], "user")
    GatherAgent(db, settings).run(first.id)
    p = proposal_of(db, first)
    passed = next(m for m in p.members if m.status == MemberStatus.suggested)
    passed.status = MemberStatus.passed
    db.commit()
    run = start_run(db, world["alice"], world["plan"], "pass", excluded={passed.user_id})
    client = OrchestraClient(matchmaker=[lambda o, r: [answer({"shortlist": [], "note": "Nobody new fits."})]])
    GatherAgent(db, settings, client=client).run(run.id)
    kickoff = client.responses.requests["matchmaker"][0]["input"][0]["content"]
    assert "Trigger: pass" in kickoff and '"passed": 1' in kickoff and passed.user.display_name not in kickoff


def test_run_in_background_uses_own_session(db, settings, world, monkeypatch):
    run = start_run(db, world["alice"], world["plan"], "user")
    calls = []
    real = orchestrator.SessionLocal
    monkeypatch.setattr(orchestrator, "SessionLocal", lambda: calls.append(1) or real())
    orchestrator.run_in_background(run.id)
    db.expire_all()
    assert calls and db.get(AgentRun, run.id).status == RunStatus.completed


def test_matchmaker_rejection_reruns_scheduler_and_planner_fresh(db, settings, world):
    run = start_run(db, world["alice"], world["plan"], "user")
    sc = Script(parallel_barrier=False)
    redesign = {**DESIGN, "activity_title": "Coffee crew meetup"}
    client = OrchestraClient(
        matchmaker=[*sc.matchmaker(), lambda o, r: [answer({
            "shortlist": [{"candidate_id": h, "reason": "Shares ai and coffee"} for h in sc.st["ids"]], "note": "Refined."})]],
        scheduler=[*sc.scheduler(), *sc.scheduler()],
        planner=[*sc.planner(), lambda o, r: [answer(redesign)]],
        reviewer=[lambda o, r: [verdicts(matchmaker="Use more specific reasons.")], lambda o, r: [verdicts()]],
    )
    GatherAgent(db, settings, client=client).run(run.id)
    db.refresh(run)
    assert run.status == RunStatus.completed, run.error
    reqs = client.responses.requests
    assert reqs["matchmaker"][2]["previous_response_id"] == "resp_matchmaker_2"  # matchmaker revises in its conversation
    for name in ("scheduler", "planner"):  # the others start over on the new shortlist
        retry = reqs[name][-1] if name == "planner" else reqs[name][2]
        assert "previous_response_id" not in retry
    assert proposal_of(db, run).activity_title == "Coffee crew meetup"

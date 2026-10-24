"""Public Gather Agent API (docs/api-contract.md): `start_run`, `run_in_background`, `GatherAgent`.

The work is done by the agent orchestra in app/ai/orchestra (matchmaker -> scheduler || planner -> reviewer ->
propose_group). Live mode uses Muse Spark for every agent; offline (no MODEL_API_KEY) each agent falls back to
deterministic rules, labeled "Rules-based" so it is never mistaken for Muse Spark.
"""

import logging
import uuid

from sqlalchemy.orm import Session

from app.ai.orchestra.conductor import Conductor
from app.config import get_settings
from app.db import SessionLocal
from app.models import AgentEvent, AgentRun, Plan, RunStatus, User

log = logging.getLogger("ingather.agent")

TRIGGER_EVENTS = {
    "user": "Started by you",
    "pass": "Replanning: you passed on a suggested person (they won't be told)",
    "decline": "Replanning: an invitation was declined",
    "feedback": "Replanning with your feedback",
}


class GatherAgent(Conductor):
    """Contract name for the orchestra conductor: `GatherAgent(db, settings, client=None).run(run_id)`."""


def start_run(
    db: Session, owner: User, plan: Plan, trigger: str, goal: str = "", excluded: set[uuid.UUID] = ()
) -> AgentRun:
    """Create a running AgentRun (caller schedules run_in_background). Authorization was checked by the caller;
    ownership is re-checked here because the run inherits the owner's scope."""
    if plan.owner_id != owner.id:
        raise PermissionError("not the plan owner")
    s = get_settings()
    run = AgentRun(
        plan_id=plan.id,
        owner_id=owner.id,
        trigger=trigger if trigger in TRIGGER_EVENTS else "user",
        mode="live" if s.ai_live else "offline",
        model=s.meta_model if s.ai_live else None,
        status=RunStatus.running,
        goal=(goal or "")[:2000],
        excluded_user_ids=sorted({str(x) for x in excluded}),
    )
    db.add(run)
    db.flush()
    db.add(AgentEvent(run_id=run.id, seq=1, kind="system", agent="orchestrator", tool_name=None, summary=TRIGGER_EVENTS[run.trigger]))
    db.commit()
    return run


def run_in_background(run_id: uuid.UUID) -> None:
    """Entry point for BackgroundTasks / outbox workers. Opens its own Session."""
    try:
        with SessionLocal() as db:
            GatherAgent(db, get_settings()).run(run_id)
    except Exception as exc:
        log.warning("background agent run %s crashed: %s", run_id, type(exc).__name__)

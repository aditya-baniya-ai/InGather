"""Gate in front of the Gather Agent: every run (user, pass, decline, feedback) goes through the same checks."""

import importlib
from collections.abc import Iterable
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import AgentRun, DiscoveryMode, Plan, PlanStatus, User
from app.services.policy import Policy, conflict

FEEDBACK_HINTS = {
    "prefer_same_event": "The owner prefers people attending the same event.",
    "prefer_group": "The owner prefers a larger group.",
    "different_activity": "The owner would like a different kind of activity.",
    "schedule": "The owner wants a better schedule fit.",
}


def orchestrator():
    """Imported lazily so the services work (and are testable) independently of app.ai."""
    return importlib.import_module("app.ai.orchestrator")


class AgentRuns:
    def __init__(self, db: Session, settings: Settings):
        self.db, self.settings = db, settings
        self.policy = Policy(db, settings)

    def check(self, owner: User, plan: Plan) -> None:
        if not self.policy.can_discover(owner):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "not_eligible")
        if plan.status != PlanStatus.active or plan.discovery_mode == DiscoveryMode.paused:
            raise conflict("plan_inactive")
        if plan.ai_consent_at is None:
            raise conflict("ai_consent_required")

    def start(self, owner: User, plan: Plan, trigger: str, goal: str = "", excluded: Iterable[UUID] = ()) -> AgentRun:
        self.check(owner, plan)
        return orchestrator().start_run(self.db, owner, plan, trigger, goal=goal, excluded=set(excluded))

    @staticmethod
    def run_in_background(run_id: UUID) -> None:
        orchestrator().run_in_background(run_id)

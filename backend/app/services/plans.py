"""Owner-only plan management. Callers must already have resolved the plan through Policy.own_plan."""

from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import AgentRun, AvailabilityWindow, ConsentEvent, DiscoveryMode, Plan, PlanStatus, Proposal, User, now
from app.schemas import DiscoveryIn, PlanIn, PlanOut, PlanPatch
from app.services.policy import conflict
from app.services.proposals import Proposals


class Plans:
    def __init__(self, db: Session, settings: Settings):
        self.db, self.settings = db, settings

    def mine(self, user: User) -> list[Plan]:
        return self.db.scalars(select(Plan).where(Plan.owner_id == user.id).order_by(Plan.created_at.desc())).all()

    def create(self, user: User, body: PlanIn) -> Plan:
        plan = Plan(owner_id=user.id)  # owner is the token's user, never the body
        self._apply(plan, body)
        self.db.add(plan)
        self.db.commit()
        return plan

    def update(self, plan: Plan, patch: PlanPatch) -> Plan:
        current = {f: getattr(plan, f) for f in PlanIn.model_fields if f != "windows"}
        current["windows"] = [{"starts_at": w.starts_at, "ends_at": w.ends_at} for w in plan.windows]
        try:
            merged = PlanIn.model_validate({**current, **patch.model_dump(exclude_unset=True, exclude_none=True)})
        except ValidationError as e:
            raise RequestValidationError(e.errors())
        self._apply(plan, merged)
        self.db.commit()
        return plan

    def set_discovery(self, user: User, plan: Plan, body: DiscoveryIn) -> Plan:
        if plan.status in (PlanStatus.cancelled, PlanStatus.expired):
            raise conflict("plan_inactive")
        plan.discovery_mode = DiscoveryMode(body.mode)
        plan.status = PlanStatus.paused if body.mode == DiscoveryMode.paused else PlanStatus.active
        self.db.add(ConsentEvent(user_id=user.id, kind="discovery", plan_id=plan.id, scope={"mode": body.mode}))
        if body.ai_consent is not None:
            plan.ai_consent_at = now() if body.ai_consent else None
            self.db.add(
                ConsentEvent(user_id=user.id, kind="ai_processing", plan_id=plan.id, scope={"granted": body.ai_consent})
            )
        self.db.commit()
        return plan

    def cancel(self, plan: Plan) -> None:
        plan.status = PlanStatus.cancelled
        Proposals(self.db, self.settings).cancel_for_plan(plan)
        self.db.commit()

    def out(self, plan: Plan) -> PlanOut:
        return PlanOut.build(plan, self._latest(Proposal, plan), self._latest(AgentRun, plan))

    def _latest(self, model, plan: Plan):
        q = select(model.id).where(model.plan_id == plan.id).order_by(model.created_at.desc()).limit(1)
        return self.db.scalar(q)

    @staticmethod
    def _apply(plan: Plan, body: PlanIn) -> None:
        for field, value in body.model_dump(exclude={"windows"}).items():
            setattr(plan, field, value)
        plan.windows = [AvailabilityWindow(starts_at=w.starts_at, ends_at=w.ends_at) for w in body.windows]

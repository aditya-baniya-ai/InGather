from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db import get_db
from app.models import User
from app.schemas import RunIn, RunOut
from app.security import current_user
from app.services.policy import Policy
from app.services.proposals import Proposals
from app.services.ratelimit import limiter
from app.services.runs import AgentRuns

router = APIRouter(prefix="/api/agent", tags=["agent"])


@router.post("/runs", response_model=RunOut, status_code=202)
def start_run(
    body: RunIn,
    background: BackgroundTasks,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
    s: Settings = Depends(get_settings),
):
    plan = Policy(db, s).own_plan(user, body.plan_id)
    runs = AgentRuns(db, s)
    runs.check(user, plan)
    limiter.hit("agent_run", user.id)
    run = runs.start(user, plan, "user", body.goal, Proposals(db, s).exclusions(plan))
    background.add_task(AgentRuns.run_in_background, run.id)
    return RunOut.build(run)


@router.get("/runs/{run_id}", response_model=RunOut)
def get_run(run_id: UUID, user: User = Depends(current_user), db: Session = Depends(get_db), s: Settings = Depends(get_settings)):
    return RunOut.build(Policy(db, s).own_run(user, run_id))

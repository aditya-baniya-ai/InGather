from uuid import UUID

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db import get_db
from app.models import User
from app.schemas import DiscoveryIn, PlanIn, PlanOut, PlanPatch
from app.security import current_user
from app.services.plans import Plans
from app.services.policy import Policy

router = APIRouter(prefix="/api/plans", tags=["plans"])


def plans(db: Session = Depends(get_db), s: Settings = Depends(get_settings)) -> Plans:
    return Plans(db, s)


def policy(db: Session = Depends(get_db), s: Settings = Depends(get_settings)) -> Policy:
    return Policy(db, s)


@router.post("", response_model=PlanOut, status_code=201)
def create_plan(body: PlanIn, user: User = Depends(current_user), svc: Plans = Depends(plans)):
    return svc.out(svc.create(user, body))


@router.get("", response_model=list[PlanOut])
def list_plans(user: User = Depends(current_user), svc: Plans = Depends(plans)):
    return [svc.out(p) for p in svc.mine(user)]


@router.get("/{plan_id}", response_model=PlanOut)
def get_plan(plan_id: UUID, user: User = Depends(current_user), svc: Plans = Depends(plans), pol: Policy = Depends(policy)):
    return svc.out(pol.own_plan(user, plan_id))


@router.patch("/{plan_id}", response_model=PlanOut)
def update_plan(
    plan_id: UUID,
    body: PlanPatch,
    user: User = Depends(current_user),
    svc: Plans = Depends(plans),
    pol: Policy = Depends(policy),
):
    return svc.out(svc.update(pol.own_plan(user, plan_id), body))


@router.post("/{plan_id}/discovery", response_model=PlanOut)
def set_discovery(
    plan_id: UUID,
    body: DiscoveryIn,
    user: User = Depends(current_user),
    svc: Plans = Depends(plans),
    pol: Policy = Depends(policy),
):
    return svc.out(svc.set_discovery(user, pol.own_plan(user, plan_id), body))


@router.delete("/{plan_id}", status_code=204)
def delete_plan(plan_id: UUID, user: User = Depends(current_user), svc: Plans = Depends(plans), pol: Policy = Depends(policy)):
    svc.cancel(pol.own_plan(user, plan_id))
    return Response(status_code=204)

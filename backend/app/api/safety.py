from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db import get_db
from app.models import Block, Report, User
from app.schemas import BlockIn, BlockOut, ReportIn
from app.security import current_user, not_found
from app.services.proposals import Proposals

router = APIRouter(prefix="/api", tags=["safety"])


@router.post("/blocks", status_code=201)
def block(body: BlockIn, user: User = Depends(current_user), db: Session = Depends(get_db), s: Settings = Depends(get_settings)):
    if body.user_id == user.id:
        raise HTTPException(422, "cannot_block_self")
    if db.get(User, body.user_id) is None:
        raise not_found()
    exists = db.scalar(select(Block.id).where(Block.blocker_id == user.id, Block.blocked_id == body.user_id))
    if exists is None:
        db.add(Block(blocker_id=user.id, blocked_id=body.user_id))
    Proposals(db, s).remove_blocked(user.id, body.user_id)
    return {"user_id": body.user_id}


@router.get("/blocks", response_model=list[BlockOut])
def list_blocks(user: User = Depends(current_user), db: Session = Depends(get_db)):
    q = select(User.id, User.display_name).join(Block, Block.blocked_id == User.id).where(Block.blocker_id == user.id)
    return [BlockOut(user_id=uid, display_name=name) for uid, name in db.execute(q.order_by(Block.created_at))]


@router.delete("/blocks/{user_id}", status_code=204)
def unblock(user_id: UUID, user: User = Depends(current_user), db: Session = Depends(get_db)):
    db.execute(delete(Block).where(Block.blocker_id == user.id, Block.blocked_id == user_id))
    db.commit()
    return Response(status_code=204)


@router.post("/reports", status_code=201)
def report(body: ReportIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    r = Report(reporter_id=user.id, **body.model_dump())
    db.add(r)
    db.commit()
    return {"id": r.id, "status": r.status}

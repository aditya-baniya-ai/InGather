"""Durable background triggers. `invitation_declined` makes the owner's agent replan autonomously; the
result is only ever a new *suggestion* awaiting the owner's approval."""

import logging

from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db import SessionLocal
from app.models import OutboxEvent, Plan, Proposal, User, now
from app.services.proposals import OPEN, Proposals
from app.services.runs import AgentRuns

log = logging.getLogger(__name__)
MAX_ATTEMPTS = 3


class Outbox:
    def __init__(self, db: Session, settings: Settings):
        self.db, self.settings = db, settings
        self.handlers = {"invitation_declined": self._invitation_declined}

    def process(self) -> int:
        pending = self.db.scalars(
            select(OutboxEvent)
            .where(OutboxEvent.processed_at.is_(None), OutboxEvent.attempts < MAX_ATTEMPTS)
            .order_by(OutboxEvent.created_at)
        ).all()
        done = 0
        for event in pending:
            if not self._claim(event):
                continue  # another worker took it
            try:
                self.handlers[event.kind](event)
                done += 1
            except Exception:
                log.exception("outbox event %s (%s) failed", event.id, event.kind)
                self.db.rollback()
                self.db.execute(
                    update(OutboxEvent).where(OutboxEvent.id == event.id).values(processed_at=None)
                )
                self.db.commit()
        return done

    def _claim(self, event: OutboxEvent) -> bool:
        claimed = self.db.execute(
            update(OutboxEvent)
            .where(OutboxEvent.id == event.id, OutboxEvent.processed_at.is_(None))
            .values(processed_at=now(), attempts=OutboxEvent.attempts + 1)
        )
        self.db.commit()
        return claimed.rowcount == 1

    def _invitation_declined(self, event: OutboxEvent) -> None:
        proposal = self.db.get(Proposal, event.aggregate_id)
        if proposal is None or proposal.status not in OPEN:
            return
        plan, owner = self.db.get(Plan, proposal.plan_id), self.db.get(User, proposal.owner_id)
        runs = AgentRuns(self.db, self.settings)
        try:
            run = runs.start(owner, plan, "decline", excluded=Proposals(self.db, self.settings).exclusions(plan))
        except HTTPException:
            return  # owner no longer eligible / plan paused: no replan
        self.db.commit()
        runs.run_in_background(run.id)  # already off the request path

    @staticmethod
    def process_in_background() -> None:
        with SessionLocal() as db:
            Outbox(db, get_settings()).process()

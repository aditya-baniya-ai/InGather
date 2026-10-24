"""Muse connector: a tiny stateless MCP server (JSON-RPC 2.0 over streamable HTTP, JSON responses).

Lets the user's own Muse agent check plans and ask the Gather Agent to plan. Authenticated by a
personal connector token (`igc_...`, only its sha256 is stored). Every tool acts as that user only.
There are deliberately NO tools to approve invitations, confirm meetups, or read others' data.
"""

import json
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.orchestrator import run_in_background, start_run
from app.ai.routes import hash_token
from app.config import Settings, get_settings
from app.db import get_db
from app.models import (
    AgentRun, ConnectorToken, MemberStatus, Plan, PlanStatus, Proposal, ProposalMember, ProposalStatus, User,
)

router = APIRouter(tags=["connector"])

SUPPORTED_VERSIONS = ("2025-06-18", "2025-03-26", "2024-11-05")
SERVER_INFO = {"name": "ingather", "title": "InGather", "version": "0.1.0"}
INSTRUCTIONS = (
    "InGather coordinates small, consensual group meetups. These tools act only as the connected user. "
    "Inviting people and confirming meetups always require the user's own click in the InGather app."
)
_PLAN_ARG = {
    "type": "object",
    "properties": {"plan_id": {"type": "string", "description": "Id from list_my_plans."}},
    "required": ["plan_id"],
    "additionalProperties": False,
}
_NO_ARGS = {"type": "object", "properties": {}, "additionalProperties": False}
TOOLS = [
    {"name": "list_my_plans", "description": "List the connected user's own InGather plans.", "inputSchema": _NO_ARGS,
     "annotations": {"readOnlyHint": True}},
    {"name": "get_plan_status", "description": "Status of one of the user's plans: latest group proposal (counts only) and latest agent run.",
     "inputSchema": _PLAN_ARG, "annotations": {"readOnlyHint": True}},
    {"name": "ask_gather_agent", "description": "Ask InGather's Gather Agent to find a compatible group for one of the user's plans. "
     "It only proposes; nobody is invited until the user approves in the app. Requires AI consent on the plan.",
     "inputSchema": _PLAN_ARG, "annotations": {"readOnlyHint": False, "destructiveHint": False}},
    {"name": "list_my_invitations", "description": "Invitations addressed to the connected user (activity, city, date, group size, host name).",
     "inputSchema": _NO_ARGS, "annotations": {"readOnlyHint": True}},
]
OPEN = (ProposalStatus.pending_owner, ProposalStatus.invites_pending, ProposalStatus.awaiting_final)


class PlanArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    plan_id: uuid.UUID


class NoArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ToolFailure(Exception):
    pass


def _iso(dt):
    return dt.isoformat() if dt else None


class ConnectorTools:
    def __init__(self, db: Session, settings: Settings, user: User, background: BackgroundTasks):
        self.db, self.settings, self.user, self.background = db, settings, user, background
        from app.services.policy import Policy

        self.policy = Policy(db, settings)

    def call(self, name: str, args: dict) -> dict | list:
        return getattr(self, f"t_{name}")(args)

    def _plan(self, args: dict) -> Plan:
        plan_id = PlanArgs.model_validate(args).plan_id
        try:
            return self.policy.own_plan(self.user, plan_id)
        except HTTPException:
            raise ToolFailure("Not found")

    def t_list_my_plans(self, args: dict):
        NoArgs.model_validate(args)
        plans = self.db.scalars(select(Plan).where(Plan.owner_id == self.user.id).order_by(Plan.created_at.desc()))
        return [
            {"plan_id": str(p.id), "title": p.title, "activity_type": p.activity_type, "city": p.city,
             "start_date": p.start_date.isoformat(), "end_date": p.end_date.isoformat(), "status": p.status.value,
             "discovery_mode": p.discovery_mode.value, "ai_consent": p.ai_consent_at is not None}
            for p in plans
        ]

    def t_get_plan_status(self, args: dict):
        plan = self._plan(args)
        prop = self.db.scalars(select(Proposal).where(Proposal.plan_id == plan.id).order_by(Proposal.created_at.desc())).first()
        run = self.db.scalars(select(AgentRun).where(AgentRun.plan_id == plan.id).order_by(AgentRun.created_at.desc())).first()
        counts: dict[str, int] = {}
        for m in prop.members if prop else []:
            if not m.is_initiator and m.status != MemberStatus.removed:
                counts[m.status.value] = counts.get(m.status.value, 0) + 1
        return {
            "plan_id": str(plan.id), "title": plan.title, "status": plan.status.value,
            "discovery_mode": plan.discovery_mode.value, "ai_consent": plan.ai_consent_at is not None,
            "latest_proposal": prop and {
                "status": prop.status.value, "version": prop.version, "activity_title": prop.activity_title,
                "start_at": _iso(prop.start_at), "member_counts": counts,
            },
            "latest_run": run and {"status": run.status.value, "mode": run.mode, "summary": run.summary, "error": run.error},
            "next_step": "Review suggestions and approve invitations in the InGather app.",
        }

    def t_ask_gather_agent(self, args: dict):
        plan = self._plan(args)
        if plan.ai_consent_at is None:
            raise ToolFailure("ai_consent_required: turn on AI matching for this plan in the InGather app first.")
        if not self.policy.can_discover(self.user):
            raise ToolFailure("not_eligible: this account cannot use discovery yet.")
        if plan.status != PlanStatus.active:
            raise ToolFailure("plan_inactive")
        from app.services.ratelimit import limiter

        try:
            limiter.hit("agent_run", self.user.id)
        except HTTPException:
            raise ToolFailure("rate_limited: try again in a minute.")
        run = start_run(self.db, self.user, plan, "user")
        self.background.add_task(run_in_background, run.id)
        return {"run_id": str(run.id), "status": "running", "mode": run.mode,
                "next_step": "The agent only proposes. Open InGather to review and approve any invitations."}

    def t_list_my_invitations(self, args: dict):
        NoArgs.model_validate(args)
        rows = self.db.scalars(
            select(ProposalMember).where(
                ProposalMember.user_id == self.user.id,
                ProposalMember.is_initiator.is_(False),
                ProposalMember.status.in_((MemberStatus.invited, MemberStatus.accepted)),
            )
        )
        out = []
        for m in rows:
            prop = self.db.get(Proposal, m.proposal_id)
            if prop is None or self.policy.viewer_role(self.user, prop) not in ("invitee", "member"):
                continue
            plan, host = self.db.get(Plan, prop.plan_id), self.db.get(User, prop.owner_id)
            size = sum(1 for x in prop.members if x.is_initiator or x.status in (MemberStatus.invited, MemberStatus.accepted))
            out.append({
                "proposal_id": str(prop.id), "activity_title": prop.activity_title, "city": plan.city if plan else None,
                "date": prop.start_at.date().isoformat() if prop.start_at else None, "group_size": size,
                "from_display_name": host.display_name if host else None, "status": m.status.value,
                "expires_at": _iso(m.expires_at),
            })
        return out


def connector_user(request: Request, db: Session) -> User | None:
    auth = request.headers.get("authorization", "")
    scheme, _, token = auth.partition(" ")
    if scheme.lower() != "bearer" or not token.startswith("igc_"):
        return None
    row = db.scalar(
        select(ConnectorToken).where(ConnectorToken.token_hash == hash_token(token.strip()), ConnectorToken.revoked_at.is_(None))
    )
    return db.get(User, row.user_id) if row else None


def _ok(id_, result) -> JSONResponse:
    return JSONResponse({"jsonrpc": "2.0", "id": id_, "result": result})


def _err(id_, code: int, message: str, http: int = 200) -> JSONResponse:
    return JSONResponse({"jsonrpc": "2.0", "id": id_, "error": {"code": code, "message": message}}, status_code=http)


@router.get("/mcp", include_in_schema=False)
def mcp_get():
    return Response(status_code=405, headers={"Allow": "POST"})  # stateless: no server-initiated SSE stream


@router.post("/mcp")
async def mcp(
    request: Request,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    origin = request.headers.get("origin")
    if origin and origin not in settings.cors_list:  # DNS-rebinding guard per MCP transport spec
        return JSONResponse({"detail": "Forbidden origin"}, status_code=403)
    user = connector_user(request, db)
    if user is None:
        return JSONResponse({"detail": "invalid_token"}, status_code=401, headers={"WWW-Authenticate": "Bearer"})
    try:
        msg = json.loads(await request.body())
    except (json.JSONDecodeError, UnicodeDecodeError):
        return _err(None, -32700, "Parse error", 400)
    if not isinstance(msg, dict) or msg.get("jsonrpc") != "2.0" or not isinstance(msg.get("method"), str):
        return _err(msg.get("id") if isinstance(msg, dict) else None, -32600, "Invalid Request", 400)

    method, id_, params = msg["method"], msg.get("id"), msg.get("params") or {}
    if "id" not in msg:  # notification (e.g. notifications/initialized) or a response: accept, no body
        return Response(status_code=202)
    if method == "initialize":
        requested = params.get("protocolVersion") if isinstance(params, dict) else None
        return _ok(id_, {
            "protocolVersion": requested if requested in SUPPORTED_VERSIONS else SUPPORTED_VERSIONS[0],
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": SERVER_INFO,
            "instructions": INSTRUCTIONS,
        })
    if method == "ping":
        return _ok(id_, {})
    if method == "tools/list":
        return _ok(id_, {"tools": TOOLS})
    if method == "tools/call":
        name = params.get("name") if isinstance(params, dict) else None
        if name not in {t["name"] for t in TOOLS}:
            return _err(id_, -32602, f"Unknown tool: {str(name)[:60]}")
        args = params.get("arguments") or {}
        if not isinstance(args, dict):
            return _err(id_, -32602, "arguments must be an object")
        try:
            data, is_error = ConnectorTools(db, settings, user, background).call(name, args), False
        except ValidationError:
            data, is_error = {"error": "invalid arguments"}, True
        except ToolFailure as e:
            data, is_error = {"error": str(e)}, True
        return _ok(id_, {"content": [{"type": "text", "text": json.dumps(data, default=str)}], "isError": is_error})
    return _err(id_, -32601, f"Method not found: {method[:60]}")

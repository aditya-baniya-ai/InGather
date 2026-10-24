"""AI routes and the MCP connector."""

import io
import wave

from app.models import AgentRun, Plan
from tests.ai.conftest import bearer


def wav_bytes() -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1), w.setsampwidth(2), w.setframerate(16000), w.writeframes(b"\0\0" * 1600)
    return buf.getvalue()


def test_transcribe_and_cover_503_without_key(api, world):
    h = bearer(world["alice"])
    r = api.post("/api/voice/transcribe", headers=h, files={"audio": ("a.wav", wav_bytes(), "audio/wav")})
    assert r.status_code == 503 and r.json() == {"detail": "ai_unavailable"}
    r = api.post(f"/api/plans/{world['plan'].id}/cover", headers=h)
    assert r.status_code == 503 and r.json() == {"detail": "ai_unavailable"}
    assert api.post(f"/api/plans/{world['plan'].id}/cover", headers=bearer(world["bob"])).status_code == 404
    assert api.post("/api/voice/transcribe", files={"audio": ("a.wav", wav_bytes(), "audio/wav")}).status_code == 401


def test_cover_prompt_has_no_personal_data(world):
    from app.ai.routes import cover_prompt

    prompt = cover_prompt(world["plan"])
    assert "Philadelphia" in prompt and "Alice" not in prompt and "secret" not in prompt and "Find 2" not in prompt


def mcp(api, token, method, params=None, id_=1):
    body = {"jsonrpc": "2.0", "method": method, **({"params": params} if params is not None else {})}
    if id_ is not None:
        body["id"] = id_
    return api.post("/mcp", json=body, headers={"Authorization": f"Bearer {token}"} if token else {})


def test_connector_auth_and_tools(api, db, world):
    import json

    assert mcp(api, None, "tools/list").status_code == 401
    assert mcp(api, "igc_nope", "tools/list").status_code == 401
    token = api.post("/api/connector/tokens", headers=bearer(world["alice"])).json()["token"]
    assert token.startswith("igc_")
    from app.models import ConnectorToken

    assert all(token not in t.token_hash for t in db.query(ConnectorToken))  # only the hash is stored

    init = mcp(api, token, "initialize", {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "t"}}).json()
    assert init["result"]["protocolVersion"] == "2025-06-18" and "tools" in init["result"]["capabilities"]
    assert mcp(api, token, "notifications/initialized", id_=None).status_code == 202
    assert mcp(api, token, "ping").json()["result"] == {}
    names = {t["name"] for t in mcp(api, token, "tools/list").json()["result"]["tools"]}
    assert names == {"list_my_plans", "get_plan_status", "ask_gather_agent", "list_my_invitations"}
    assert not any("approve" in n or "confirm" in n for n in names)

    res = mcp(api, token, "tools/call", {"name": "list_my_plans", "arguments": {}}).json()["result"]
    plans = json.loads(res["content"][0]["text"])
    assert [p["plan_id"] for p in plans] == [str(world["plan"].id)] and res["isError"] is False

    bob_plan = db.query(Plan).filter(Plan.owner_id == world["bob"].id).one()
    res = mcp(api, token, "tools/call", {"name": "get_plan_status", "arguments": {"plan_id": str(bob_plan.id)}}).json()["result"]
    assert res["isError"] and "Not found" in res["content"][0]["text"]

    res = mcp(api, token, "tools/call", {"name": "ask_gather_agent", "arguments": {"plan_id": str(world["plan"].id)}}).json()["result"]
    started = json.loads(res["content"][0]["text"])
    assert not res["isError"] and started["status"] == "running" and started["mode"] == "offline"
    status = json.loads(mcp(api, token, "tools/call", {"name": "get_plan_status", "arguments": {"plan_id": str(world["plan"].id)}}).json()["result"]["content"][0]["text"])
    assert status["latest_run"] is not None
    assert db.query(AgentRun).filter(AgentRun.plan_id == world["plan"].id).count() == 1

    assert mcp(api, token, "tools/call", {"name": "approve_invitations", "arguments": {}}).json()["error"]["code"] == -32602
    assert mcp(api, token, "resources/list").json()["error"]["code"] == -32601

    assert api.delete("/api/connector/tokens", headers=bearer(world["alice"])).status_code == 204
    assert mcp(api, token, "tools/list").status_code == 401

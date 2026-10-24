"""Shared flow helpers for HTTP tests."""


def start_agent(api, plan_id) -> dict:
    res = api.post("/api/agent/runs", {"plan_id": str(plan_id)})
    assert res.status_code == 202, res.text
    run = api.get(f"/api/agent/runs/{res.json()['id']}").json()
    assert run["status"] == "completed" and run["proposal_id"], run
    return run


def members(api, proposal_id) -> dict[str, dict]:
    return {m["display_name"]: m for m in api.get(f"/api/proposals/{proposal_id}").json()["members"]}


def approve(api, proposal_id, *users) -> dict:
    version = api.get(f"/api/proposals/{proposal_id}").json()["version"]
    res = api.post(f"/api/proposals/{proposal_id}/approve-invitations", {"version": version, "user_ids": [str(u.id) for u in users]})
    assert res.status_code == 200, res.text
    return res.json()

"""Intake agent (POST /api/plans/draft): structured output validated through PlanIn's rules."""

from datetime import date, datetime, timezone

from app.ai import routes
from app.ai.orchestra.intake import clean_draft
from app.services.ratelimit import limiter
from tests.ai.conftest import bearer
from tests.ai.fakes import OrchestraClient, answer, say

TEXT = ("I'm planning to go to HackTX from October 24 to October 25 at UT Austin at 10 am and then I'm trying to find "
        "some people who are also going there.")
RAW = {
    "activity_type": "hackathon", "title": "HackTX at UT Austin", "goal_text": "Find people also going to HackTX.",
    "city": "Austin", "timezone": "America/Chicago", "start_date": "2026-10-24", "end_date": "2026-10-25",
    "intent": "friends", "interests": ["Hackathons", "coding"], "group_min": None, "group_max": None, "group_only": True,
    "windows": [{"start_local": "2026-10-24T10:00", "end_local": "2026-10-24T21:00"},
                {"start_local": "2026-10-25T10:00", "end_local": "2026-10-25T21:00"}],
    "missing": ["group_min", "group_max"], "notes": "Assumed 2026 because the dates are upcoming.",
}


def test_clean_draft_converts_local_windows_to_utc():
    d = clean_draft(RAW, TEXT)
    assert (d.activity_type, d.city, d.timezone, d.intent) == ("hackathon", "Austin", "America/Chicago", "friends")
    assert (d.start_date, d.end_date) == (date(2026, 10, 24), date(2026, 10, 25))
    assert d.windows[0].starts_at == datetime(2026, 10, 24, 15, tzinfo=timezone.utc)  # 10:00 CDT
    assert d.windows[1].ends_at == datetime(2026, 10, 26, 2, tzinfo=timezone.utc)
    assert d.interests == ["hackathons", "coding"] and d.missing == ["group_min", "group_max"] and d.mode == "live"


def test_invalid_fields_go_to_missing():
    bad = {**RAW, "group_min": 1, "group_max": 6, "activity_type": "rave", "timezone": "Mars/Olympus", "end_date": "2026-10-01"}
    d = clean_draft(bad, TEXT)
    assert d.group_min is None and d.group_max is None and d.activity_type is None and d.end_date is None
    assert d.timezone is None and d.windows == []  # windows can't be placed without a valid zone
    assert {"group_min", "group_max", "activity_type", "timezone", "end_date", "windows"} <= set(d.missing)
    flipped = clean_draft({**RAW, "group_min": 4, "group_max": 3}, TEXT)
    assert flipped.group_min is None and flipped.group_max is None and "group_min" in flipped.missing
    outside = clean_draft({**RAW, "windows": [{"start_local": "2026-11-02T10:00", "end_local": "2026-11-02T12:00"},
                                             {"start_local": "2026-10-24T12:00", "end_local": "2026-10-24T11:00"}]}, TEXT)
    assert outside.windows == [] and "windows" in outside.missing


def test_draft_endpoint_uses_structured_output_without_tools(api, world):
    client = OrchestraClient(intake=[lambda o, r: [answer(RAW)]])
    api.app.dependency_overrides[routes.muse] = lambda: client
    limiter.reset()
    r = api.post("/api/plans/draft", headers=bearer(world["alice"]), json={"text": TEXT, "timezone_hint": "America/Chicago"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["city"] == "Austin" and body["windows"][0]["starts_at"] == "2026-10-24T15:00:00Z" and body["mode"] == "live"
    req = client.responses.requests["intake"][0]
    assert "tools" not in req and req["text"]["format"]["type"] == "json_schema"
    prompt = req["input"][0]["content"]
    assert "TODAY: " in prompt and "America/Chicago" in prompt and f"<<<{TEXT}>>>" in prompt
    assert api.post("/api/plans/draft", headers=bearer(world["alice"]), json={"text": ""}).status_code == 422
    assert api.post("/api/plans/draft", json={"text": TEXT}).status_code == 401


def test_draft_503_without_key_and_rate_limited(api, world):
    h = bearer(world["alice"])
    r = api.post("/api/plans/draft", headers=h, json={"text": TEXT})
    assert r.status_code == 503 and r.json() == {"detail": "ai_unavailable"}
    client = OrchestraClient(intake=[lambda o, r: [answer(RAW)]] * 20)
    api.app.dependency_overrides[routes.muse] = lambda: client
    limiter.reset()
    codes = [api.post("/api/plans/draft", headers=h, json={"text": TEXT}).status_code for _ in range(11)]
    assert codes[:10] == [200] * 10 and codes[10] == 429
    limiter.reset()


def test_bad_model_answer_is_502(api, world):
    client = OrchestraClient(intake=[lambda o, r: [say("Sure! Here is your plan.")]])
    api.app.dependency_overrides[routes.muse] = lambda: client
    limiter.reset()
    r = api.post("/api/plans/draft", headers=bearer(world["alice"]), json={"text": TEXT})
    assert r.status_code == 502 and r.json() == {"detail": "draft_failed"}


def test_past_dates_go_to_missing():
    d = clean_draft({**RAW, "start_date": "2025-10-24", "end_date": "2025-10-25"}, TEXT, today=date(2026, 10, 24))
    assert d.start_date is None and d.end_date is None and {"start_date", "end_date"} <= set(d.missing)
    ok = clean_draft(RAW, TEXT, today=date(2026, 10, 24))  # today itself is fine
    assert ok.start_date == date(2026, 10, 24) and "start_date" not in ok.missing

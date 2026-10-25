"""The toolbox, not the model, enforces ownership, exclusions, caps and privacy."""

import json
import re
from datetime import datetime, timedelta

import pytest

from app.ai.orchestrator import start_run
from app.ai.tools import TOOL_SPECS, AgentToolbox, EventLog


def box(db, settings, world, excluded=()):
    run = start_run(db, world["alice"], world["plan"], "user", excluded=set(excluded))
    return AgentToolbox(db, settings, run, world["plan"], world["alice"], EventLog(db, run))


def handles(tb):
    return {tb._handles[h][1].display_name: h for h in tb._handles}


def propose(tb, ids, **over):
    w = tb.execute("check_group_availability", {"candidate_ids": ids}) if ids and all(i in tb._handles for i in ids) else {}
    start = datetime.fromisoformat(w["windows"][0]["start"]) if w.get("windows") else datetime(2027, 1, 17, 12)
    args = {"candidate_ids": ids, "activity_title": "T", "explanation": "E", "start_at": start.isoformat(),
            "end_at": (start + timedelta(hours=1)).isoformat(), "venue_label": "A café", "venue_category": "cafe",
            "icebreaker": "Hi", "reasons": [{"candidate_id": i, "reason": "r"} for i in ids]}
    return tb.execute("propose_group", {**args, **over})


def test_schemas_are_closed():
    for spec in TOOL_SPECS:
        assert spec["parameters"]["additionalProperties"] is False


def test_blocked_and_other_city_never_found(db, settings, world):
    tb = box(db, settings, world)
    tb.execute("find_eligible_candidates", {"excluded_candidate_ids": []})
    names = set(handles(tb))
    assert {"Bob", "Cara", "Dan"} <= names and not names & {"Eve", "Zed", "Alice"}


def test_never_found_or_forged_ids_rejected(db, settings, world):
    tb = box(db, settings, world)
    assert "unknown candidate" in tb.execute("check_group_availability", {"candidate_ids": ["cand_99"]})["error"]
    tb.execute("find_eligible_candidates", {"excluded_candidate_ids": []})
    forged = str(world["eve"].id)  # model somehow learns a raw account id
    assert "unknown candidate" in propose(tb, [forged, "cand_1"])["error"]
    assert tb.proposal is None


def test_excluded_candidate_rejected_even_if_found_earlier(db, settings, world):
    tb = box(db, settings, world)
    tb.execute("find_eligible_candidates", {"excluded_candidate_ids": []})
    bob = handles(tb)["Bob"]
    tb.run.excluded_user_ids = [str(world["bob"].id)]  # owner passed mid-run
    assert "excluded" in tb.execute("check_group_availability", {"candidate_ids": [bob]})["error"]
    tb2 = box(db, settings, world, excluded={world["bob"].id})
    tb2.execute("find_eligible_candidates", {"excluded_candidate_ids": []})
    assert "Bob" not in handles(tb2)


def test_caps_venue_and_args_validation(db, settings, world):
    tb = box(db, settings, world)
    tb.execute("find_eligible_candidates", {"excluded_candidate_ids": []})
    h = list(tb._handles)
    assert "between 2 and 2" in propose(tb, h[:1])["error"]  # group_min=3 incl. owner
    assert "invalid arguments" in propose(tb, h[:4])["error"]  # max_length on the schema
    assert "public place" in propose(tb, h[:2], venue_label="My hotel room")["error"]
    assert "venue_category" in propose(tb, h[:2], venue_category="home")["error"]
    assert "invalid arguments" in tb.execute("propose_group", {"candidate_ids": h[:2], "is_admin": True})["error"]
    assert "JSON object" in tb.execute("find_eligible_candidates", "not json")["error"]
    late = datetime(2027, 1, 18, 3).isoformat() + "+00:00"
    assert "inside a window" in propose(tb, h[:2], start_at=late, end_at=late.replace("T03", "T04"))["error"]
    assert tb.proposal is None
    ok = propose(tb, h[:2])
    assert ok["saved"] and tb.proposal is not None


def test_prompt_injection_grants_nothing_and_outputs_stay_minimal(db, settings, world):
    tb = box(db, settings, world)
    outputs = [tb.execute("get_my_plan_context", {}), tb.execute("find_eligible_candidates", {"excluded_candidate_ids": []})]
    mallory = handles(tb)["Mallory"]
    found = outputs[1]["candidates"]
    assert any("IGNORE ALL PREVIOUS" in c["preview_text_untrusted"] for c in found)
    assert set(found[0]) == {"candidate_id", "activity_type", "intent", "shared_interests", "preview_text_untrusted"}
    outputs.append(tb.execute("check_group_availability", {"candidate_ids": [mallory, handles(tb)["Bob"]]}))
    outputs.append(tb.execute("read_proposal_status", {}))
    outputs.append(tb.execute("reveal_emails", {"all": True}))
    text = json.dumps(outputs)
    assert "@" not in text  # no emails
    for name in ("bob", "cara", "dan", "mallory", "eve"):
        assert str(world[name].id) not in text and world[name].display_name not in text
        assert f"of {world[name].display_name}" not in text  # nobody else's goal_text
    assert outputs[0]["owner_goal"] == world["plan"].goal_text  # the owner's own goal, for the owner's own agent
    assert not re.search(r"starts_at|ends_at|password|verification", text)


def test_toolbox_requires_matching_owner(db, settings, world):
    run = start_run(db, world["alice"], world["plan"], "user")
    with pytest.raises(PermissionError):
        AgentToolbox(db, settings, run, world["plan"], world["bob"])


def test_humanize_replaces_handles_case_insensitively(db, settings, world):
    tb = box(db, settings, world)
    tb.execute("find_eligible_candidates", {"excluded_candidate_ids": []})
    h = handles(tb)["Bob"]
    assert tb.humanize(f"{h.capitalize()} and cand_77 fit") == "Bob and another person fit"

@pytest.mark.parametrize('mapped', [True, False])
def test_event_anchor_grounds_venue_in_provider_results(db, settings, world, monkeypatch, mapped):
    from app.services import places
    world['plan'].public_location = 'Public Conference Venue'
    db.commit()
    place = {'id': 'node/1', 'name': 'Mapped café', 'category': 'cafe', 'latitude': 39.955,
             'longitude': -75.16, 'address': 'Public street', 'distance_m': 50, 'source': 'OpenStreetMap'}
    calls = []
    def lookup(location, city, enabled):
        calls.append((location, city))
        return {'status': 'ok' if mapped else 'unavailable', 'places': [place] if mapped else [], 'message': 'Test lookup'}
    monkeypatch.setattr(places, 'nearby', lookup)
    tb = box(db, settings, world)
    tb.execute('find_eligible_candidates', {'excluded_candidate_ids': []})
    result = propose(tb, list(tb._handles)[:2], venue_label='An invented café near the conference')
    assert result['saved']
    assert calls == [('Public Conference Venue', 'Philadelphia')]
    if mapped:
        assert tb.proposal.venue_label == 'Mapped café'
        assert tb.proposal.venue_details == place
    else:
        assert tb.proposal.venue_label == 'A public cafe in Philadelphia (choose exact location)'
        assert tb.proposal.venue_details is None

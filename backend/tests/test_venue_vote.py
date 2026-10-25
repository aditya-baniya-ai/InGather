"""Venue vote: midpoint privacy, auth, one vote per person, tie-break, version bump, re-roll, .ics."""

from types import SimpleNamespace

import pytest

from app.ai.venues import VenueAgent, VenueRequest, validate
from app.services.geo import coarse, midpoint
from app.services.venue_votes import pick_winner
from tests.ai.fakes import FakeMuse, answer
from tests.helpers import approve, start_agent

pytestmark = pytest.mark.usefixtures("fake_agent")


# --- location ----------------------------------------------------------------------------------
def test_coarse_rounds_to_about_1km_and_midpoint_is_rounded():
    assert coarse(39.952583, -75.165222) == (39.95, -75.17)
    assert midpoint([(39.95, -75.17), (39.97, -75.13), (39.94, -75.19)]) == (39.95, -75.16)
    assert midpoint([]) is None
    with pytest.raises(ValueError):
        coarse(91, 0)


def test_home_area_is_private_to_owner(users, as_user, client):
    alice = as_user(users["alice"])
    me = alice.patch("/api/me", {"home_area": "19107"}).json()
    assert me["home_area"] == "19107" and "home_lat" not in me  # geocoding disabled in tests -> not located
    assert me["home_area_located"] is False


# --- group setup -------------------------------------------------------------------------------
@pytest.fixture
def group(users, plan_of, as_user):
    """Alice + two accepted members; returns (apis by name, proposal id)."""
    alice = as_user(users["alice"])
    pid = start_agent(alice, plan_of(users["alice"]).id)["proposal_id"]
    body = alice.get(f"/api/proposals/{pid}").json()
    picked = [m["display_name"].lower() for m in body["members"] if m["status"] == "suggested"][:2]
    assert len(picked) == 2
    approve(alice, pid, *(users[n] for n in picked))
    apis = {"alice": alice}
    for n in picked:
        apis[n] = as_user(users[n])
        assert apis[n].post(f"/api/proposals/{pid}/respond", {"accept": True}).status_code == 200
    return apis, pid


def poll_url(pid, rest=""):
    return f"/api/proposals/{pid}/venue-poll{rest}"


def test_cannot_start_while_invites_pending(users, plan_of, as_user):
    alice = as_user(users["alice"])
    pid = start_agent(alice, plan_of(users["alice"]).id)["proposal_id"]
    approve(alice, pid, users["sofia"])
    assert alice.post(poll_url(pid)).json() == {"detail": "invites_pending"}


def test_non_participants_get_404(users, as_user, group):
    apis, pid = group
    for outsider in ("eve", "taylor", "noah"):
        api = as_user(users[outsider])
        assert api.get(poll_url(pid)).status_code == 404
        assert api.post(poll_url(pid)).status_code == 404
        assert api.get(f"/api/proposals/{pid}/calendar.ics").status_code == 404


def test_offline_fallback_is_labeled_unverified(group):
    apis, pid = group
    poll = apis["alice"].post(poll_url(pid)).json()
    assert poll["status"] == "open" and poll["source"] == "fallback" and len(poll["options"]) == 3
    assert all(not o["verified"] and o["source_url"] is None for o in poll["options"])
    assert apis["alice"].post(poll_url(pid)).json()["options"] == poll["options"]  # idempotent start


def test_one_vote_per_person_change_vote_and_winner_bumps_version(group):
    apis, pid = group
    names = list(apis)
    alice = apis["alice"]
    before = alice.get(f"/api/proposals/{pid}").json()["version"]
    opts = alice.post(poll_url(pid)).json()["options"]
    a, b = opts[0]["id"], opts[1]["id"]
    alice.post(poll_url(pid, "/vote"), {"option_id": a})
    p = alice.post(poll_url(pid, "/vote"), {"option_id": b}).json()  # change of mind, still one vote
    assert p["my_vote"] == b and sum(o["votes"] for o in p["options"]) == 1
    assert [v["voted"] for v in p["voters"]].count(True) == 1
    apis[names[1]].post(poll_url(pid, "/vote"), {"option_id": b})
    assert alice.get(poll_url(pid)).json()["status"] == "open"
    done = apis[names[2]].post(poll_url(pid, "/vote"), {"option_id": a}).json()
    assert done["status"] == "decided" and done["winner_option_id"] == b
    prop = alice.get(f"/api/proposals/{pid}").json()
    assert prop["version"] == before + 1 and prop["status"] == "awaiting_final"
    assert prop["venue_label"] == opts[1]["name"] and prop["venue_verified"] is False
    assert alice.post(poll_url(pid, "/vote"), {"option_id": a}).json() == {"detail": "venue_poll_closed"}


def test_winner_resets_confirmations(users, group):
    apis, pid = group
    alice = apis["alice"]
    alice.post(f"/api/proposals/{pid}/finalize", {})
    v = alice.get(f"/api/proposals/{pid}").json()["version"]
    alice.post(f"/api/proposals/{pid}/confirm", {"version": v})
    assert alice.get(f"/api/proposals/{pid}").json()["i_confirmed"] is True
    opt = alice.post(poll_url(pid)).json()["options"][2]["id"]
    for api in apis.values():
        api.post(poll_url(pid, "/vote"), {"option_id": opt})
    prop = alice.get(f"/api/proposals/{pid}").json()
    assert prop["version"] == v + 1 and prop["i_confirmed"] is False
    assert not any(m["confirmed"] for m in prop["members"])
    assert alice.post(f"/api/proposals/{pid}/confirm", {"version": v}).json() == {"detail": "stale_version"}


def test_tie_goes_to_higher_ranked_option():
    opts = [SimpleNamespace(id=i, rank=i) for i in (1, 2, 3)]
    votes = [SimpleNamespace(option_id=3), SimpleNamespace(option_id=2), SimpleNamespace(option_id=1)]
    assert pick_winner(opts, votes).id == 1
    assert pick_winner(opts, votes + [SimpleNamespace(option_id=3)]).id == 3
    assert pick_winner(opts, votes[:2]).id == 2


def test_reroll_once_resets_votes(group):
    apis, pid = group
    alice = apis["alice"]
    first = alice.post(poll_url(pid)).json()
    alice.post(poll_url(pid, "/vote"), {"option_id": first["options"][0]["id"]})
    second = alice.post(poll_url(pid, "/reroll")).json()
    assert second["round"] == 2 and second["rerolls_left"] == 0 and second["my_vote"] is None
    assert all(o["votes"] == 0 for o in second["options"])
    assert {o["id"] for o in second["options"]}.isdisjoint({o["id"] for o in first["options"]})
    assert alice.post(poll_url(pid, "/vote"), {"option_id": first["options"][0]["id"]}).json() == {"detail": "option_not_found"}
    assert alice.post(poll_url(pid, "/reroll")).json() == {"detail": "reroll_used"}


def test_ics_for_confirmed_participants_only(users, as_user, group):
    apis, pid = group
    alice = apis["alice"]
    assert alice.get(f"/api/proposals/{pid}/calendar.ics").status_code == 404  # not confirmed yet
    opt = alice.post(poll_url(pid)).json()["options"][0]
    for api in apis.values():
        api.post(poll_url(pid, "/vote"), {"option_id": opt["id"]})
    v = alice.get(f"/api/proposals/{pid}").json()["version"]
    for api in apis.values():
        api.post(f"/api/proposals/{pid}/confirm", {"version": v})
    res = apis[list(apis)[1]].get(f"/api/proposals/{pid}/calendar.ics")
    assert res.status_code == 200 and res.headers["content-type"].startswith("text/calendar")
    text = res.text
    for needle in ("BEGIN:VEVENT", f"UID:{pid}-v{v}@ingather", "SUMMARY:", f"/proposals/{pid}/room", "END:VCALENDAR"):
        assert needle in text.replace("\r\n ", "")
    assert "DTSTART:" in text and text.split("DTSTART:")[1][:16].endswith("Z")
    assert "LOCATION:" + opt["name"].replace(",", "\\,") in text.replace("\r\n ", "")
    for u in users.values():  # no one's email or home area in the invite
        assert u.email not in text and (u.home_area or "@@") not in text
    assert as_user(users["eve"]).get(f"/api/proposals/{pid}/calendar.ics").status_code == 404


# --- venue agent validation --------------------------------------------------------------------
SRC = "https://example-cafe.com/"


def grounded(*venues, results=(SRC,)):
    search = SimpleNamespace(type="web_search_call", status="completed", results=[{"url": u, "title": "t"} for u in results])
    return [search, answer({"venues": list(venues)})]


def venue(name, category="cafe", source=SRC, reservation=None, area="Rittenhouse"):
    return {"name": name, "area": area, "category": category, "why": "Central and quiet.", "reservation_url": reservation, "source_url": source}


REQ = VenueRequest(city="Philadelphia", midpoint=(39.95, -75.16), local_time="Sunday 18:00", activity="Coffee", interests=["coffee"])


def test_agent_rejects_private_places_caps_at_3_and_verifies_sources(settings):
    fake = FakeMuse(grounded(
        venue("Hotel Lobby Bar"), venue("Alice's apartment"), venue("Bad Category", category="nightclub"),
        venue("La Colombe", reservation="https://resy.com/cities/phl/la-colombe"),
        venue("la colombe"),  # duplicate
        venue("Unsourced Cafe", source="https://not-in-results.com/x"),
        venue("Library Cafe", category="library", reservation="https://evil.example/pay"),
        venue("Fourth One"),
    ))
    result = VenueAgent(fake, settings).suggest(REQ)
    names = [o["name"] for o in result.options]
    assert names == ["La Colombe", "Unsourced Cafe", "Library Cafe"]
    assert [o["verified"] for o in result.options] == [True, False, True]
    assert result.options[0]["reservation_url"].startswith("https://resy.com/")
    assert result.options[2]["reservation_url"] is None and result.options[1]["source_url"] is None
    assert result.source == "grounded"
    req = fake.responses.requests[0]
    assert req["tools"][0]["type"] == "web_search" and req["text"]["format"]["type"] == "json_schema"
    sent = str(req)
    assert "39.95" in sent and "Philadelphia" in sent and "Alice" not in sent


def test_agent_without_search_is_never_verified(settings):
    fake = FakeMuse([answer({"venues": [venue("Real Sounding Cafe")]})])
    result = VenueAgent(fake, settings).suggest(REQ)
    assert all(not o["verified"] for o in result.options) and result.source == "fallback"


def test_agent_failure_or_no_key_falls_back_without_invented_names(settings):
    class Boom:
        class responses:
            @staticmethod
            def create(**_):
                raise RuntimeError("down")

    for client in (None, Boom()):
        result = VenueAgent(client, settings).suggest(REQ)
        assert result.source == "fallback" and len(result.options) == 3
        assert all(o["name"].startswith("A ") and not o["verified"] for o in result.options)


def test_validate_drops_non_https_sources():
    out = validate([venue("X", source="http://example-cafe.com/")], {"example-cafe.com"}, True)
    assert out[0]["verified"] is False

"""Venue rating: midpoint privacy, auth, 1-10 ratings, average + tie-break, version bump, more places, locations, .ics."""

from types import SimpleNamespace
from uuid import UUID

import pytest

from app.ai.venues import VenueAgent, VenueRequest, validate
from app.config import get_settings
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


def rate(api, pid, option_id, score):
    return api.post(poll_url(pid, "/rate"), {"option_id": option_id, "score": score})


def rate_all(api, pid, options, scores):
    for o, sc in zip(options, scores):
        res = rate(api, pid, o["id"], sc)
    return res.json()


def test_everyone_rates_every_place_and_the_best_average_wins(group):
    apis, pid = group
    names = list(apis)
    alice = apis["alice"]
    before = alice.get(f"/api/proposals/{pid}").json()["version"]
    opts = alice.post(poll_url(pid)).json()["options"]
    a, b, c = (o["id"] for o in opts)
    rate(alice, pid, a, 9)
    p = rate(alice, pid, a, 4).json()  # change of mind, still one score
    mine = {o["id"]: o["my_score"] for o in p["options"]}
    assert mine == {a: 4, b: None, c: None} and [o["ratings"] for o in p["options"]] == [1, 0, 0]
    assert next(v for v in p["voters"] if v["display_name"] == "Alice")["rated"] == 1
    assert rate(alice, pid, a, 11).status_code == 422 and rate(alice, pid, a, 0).status_code == 422
    rate_all(alice, pid, opts, [4, 8, 6])
    rate_all(apis[names[1]], pid, opts, [10, 7, 2])
    assert alice.get(poll_url(pid)).json()["status"] == "open"  # one person still has places to rate
    done = rate_all(apis[names[2]], pid, opts, [3, 9, 9])
    # averages: a = 5.67, b = 8.0, c = 5.67 -> b
    assert done["status"] == "decided" and done["winner_option_id"] == b
    assert [o["average"] for o in done["options"]] == [5.7, 8.0, 5.7]
    prop = alice.get(f"/api/proposals/{pid}").json()
    assert prop["version"] == before + 1 and prop["status"] == "awaiting_final"
    assert prop["venue_label"] == opts[1]["name"] and prop["venue_verified"] is False
    assert rate(alice, pid, a, 5).json() == {"detail": "venue_poll_closed"}


def test_winner_resets_confirmations(users, group):
    apis, pid = group
    alice = apis["alice"]
    alice.post(f"/api/proposals/{pid}/finalize", {})
    v = alice.get(f"/api/proposals/{pid}").json()["version"]
    alice.post(f"/api/proposals/{pid}/confirm", {"version": v})
    assert alice.get(f"/api/proposals/{pid}").json()["i_confirmed"] is True
    opts = alice.post(poll_url(pid)).json()["options"]
    for api in apis.values():
        rate_all(api, pid, opts, [2, 3, 10])
    prop = alice.get(f"/api/proposals/{pid}").json()
    assert prop["version"] == v + 1 and prop["i_confirmed"] is False and prop["venue_label"] == opts[2]["name"]
    assert not any(m["confirmed"] for m in prop["members"])
    assert alice.post(f"/api/proposals/{pid}/confirm", {"version": v}).json() == {"detail": "stale_version"}


def test_tie_goes_to_higher_ranked_option():
    opts = [SimpleNamespace(id=i, rank=i) for i in (1, 2, 3)]
    r = lambda o, s: SimpleNamespace(option_id=o, score=s)  # noqa: E731
    assert pick_winner(opts, [r(1, 7), r(2, 7), r(3, 7)]).id == 1
    assert pick_winner(opts, [r(1, 7), r(2, 7), r(3, 9)]).id == 3
    assert pick_winner(opts, [r(1, 5), r(1, 9), r(2, 7), r(3, 6)]).id == 1  # 7.0 vs 7.0 -> better rank


def test_find_more_places_up_to_three_times(group):
    apis, pid = group
    alice = apis["alice"]
    first = alice.post(poll_url(pid)).json()
    rate(alice, pid, first["options"][0]["id"], 8)
    second = alice.post(poll_url(pid, "/reroll")).json()
    assert second["round"] == 2 and second["rerolls_left"] == 2
    assert all(o["my_score"] is None and o["ratings"] == 0 for o in second["options"])
    assert {o["id"] for o in second["options"]}.isdisjoint({o["id"] for o in first["options"]})
    assert rate(alice, pid, first["options"][0]["id"], 5).json() == {"detail": "option_not_found"}
    alice.post(poll_url(pid, "/reroll"))
    assert alice.post(poll_url(pid, "/reroll")).json()["rerolls_left"] == 0
    assert alice.post(poll_url(pid, "/reroll")).json() == {"detail": "reroll_used"}


def test_locations_are_opt_in_rounded_group_only_and_move_the_midpoint(users, as_user, group, db, settings):
    from app.models import Proposal
    from app.services.venue_votes import VenueVoting

    apis, pid = group
    alice = apis["alice"]
    assert alice.get(poll_url(pid)).json()["people"] == []
    res = alice.put(f"/api/proposals/{pid}/location", {"latitude": 30.267153, "longitude": -97.743057})
    body = res.json()
    assert res.status_code == 200 and body["i_shared_location"] is True
    [me] = body["people"]
    assert (me["latitude"], me["longitude"], me["is_me"]) == (30.267, -97.743, True)
    other = apis[list(apis)[1]].get(poll_url(pid)).json()
    assert other["people"][0]["is_me"] is False and other["i_shared_location"] is False
    assert as_user(users["eve"]).put(f"/api/proposals/{pid}/location", {"latitude": 1, "longitude": 1}).status_code == 404
    assert alice.put(f"/api/proposals/{pid}/location", {"latitude": 91, "longitude": 0}).status_code == 422
    proposal = db.get(Proposal, UUID(pid))
    assert VenueVoting(db, settings).request_for(proposal).midpoint is not None
    assert alice.delete(f"/api/proposals/{pid}/location").json()["people"] == []


def test_ics_for_confirmed_participants_only(users, as_user, group):
    apis, pid = group
    alice = apis["alice"]
    assert alice.get(f"/api/proposals/{pid}/calendar.ics").status_code == 404  # not confirmed yet
    opts = alice.post(poll_url(pid)).json()["options"]
    opt = opts[0]
    for api in apis.values():
        rate_all(api, pid, opts, [10, 1, 1])
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


def test_agent_pins_photos_and_descriptions_are_validated(settings):
    near = venue("Near Cafe")
    near.update(latitude=39.951, longitude=-75.163, image_url="https://example-cafe.com/photo.jpg", description="Espresso bar with big tables.")
    far = venue("Far Cafe")
    far.update(latitude=40.71, longitude=-74.0, image_url="javascript:alert(1)", description="")  # New York: too far from the group
    result = VenueAgent(FakeMuse(grounded(near, far)), settings).suggest(REQ)
    a, b = result.options[:2]
    assert (a["latitude"], a["longitude"], a["image_url"]) == (39.951, -75.163, "https://example-cafe.com/photo.jpg")
    assert a["description"] == "Espresso bar with big tables."
    assert b["latitude"] is None and b["image_url"] is None


# --- Google Places ---------------------------------------------------------------------------------
def gplace(pid, name, lat, lng, types=("cafe",), rating=4.6, count=800, **extra):
    return {"id": pid, "displayName": {"text": name}, "formattedAddress": f"{pid} Main St, Philadelphia", "types": list(types),
            "location": {"latitude": lat, "longitude": lng}, "rating": rating, "userRatingCount": count,
            "priceLevel": "PRICE_LEVEL_MODERATE", "currentOpeningHours": {"openNow": True},
            "regularOpeningHours": {"weekdayDescriptions": ["Monday: 7 AM – 6 PM"]}, "googleMapsUri": f"https://maps.google.com/?cid={pid}",
            "photos": [{"name": f"places/{pid}/photos/p1", "authorAttributions": [{"displayName": "Sam"}]}], **extra}


def test_google_results_are_summarized_and_private_or_closed_places_dropped():
    from app.services.gplaces import category, summarize

    s = summarize(gplace("a", "La Colombe", 39.95, -75.16))
    assert s["category"] == "cafe" and s["price"] == "$$" and s["open_now"] is True and s["photos"][0]["author"] == "Sam"
    assert summarize(gplace("h", "Hotel Bar", 39.95, -75.16, types=("bar", "lodging"))) is None
    assert summarize(gplace("c", "Gone Cafe", 39.95, -75.16, businessStatus="CLOSED_PERMANENTLY")) is None
    assert category(["thai_restaurant"]) == "restaurant" and category(["hiking_area"]) == "park" and category(["store"]) == "public_venue"


@pytest.fixture
def google(monkeypatch, settings):
    """A Maps key and a fake Places API: four cafés near the group, one far away."""
    from app.services import gplaces

    monkeypatch.setattr(settings, "google_maps_api_key", "test-key")
    places = [gplace("a", "Alpha Cafe", 39.951, -75.161), gplace("b", "Beta Books", 39.955, -75.17, types=("book_store", "cafe")),
              gplace("c", "Gamma Library", 39.96, -75.15, types=("library",), rating=4.8),
              gplace("d", "Delta Diner", 39.94, -75.17, types=("diner_restaurant",), rating=4.0, count=50),
              gplace("far", "Far Cafe", 40.71, -74.0)]
    calls = []

    def search(query, key, near=None, radius_km=15, n=10):
        calls.append((query, key, near))
        return [s for s in map(gplaces.summarize, places) if s][:n]

    monkeypatch.setattr(gplaces, "search", search)
    monkeypatch.setattr(gplaces, "photo_uri", lambda name, key, width=800: f"https://lh3.googleusercontent.com/{name}")
    return calls


def test_with_a_maps_key_google_finds_places_with_pins_photos_and_details(group, google):
    apis, pid = group
    poll = apis["alice"].post(poll_url(pid)).json()
    assert poll["source"] == "google" and len(poll["options"]) == 3
    assert "Far Cafe" not in [o["name"] for o in poll["options"]]  # too far from the group
    for o in poll["options"]:
        assert o["verified"] and o["latitude"] and o["source_url"].startswith("https://maps.google.com/")
        assert o["place"]["rating"] and o["place"]["hours"] and o["place"]["photos"][0]["url"] == f"/api/venue-photos/{o['id']}/0"
    query, key, near = google[0]
    assert key == "test-key" and near is not None and "Alice" not in query  # only the activity, city and rounded midpoint
    # photos redirect to Google without exposing the key; unknown photos 404
    o = poll["options"][0]
    res = apis["alice"].client.get(o["place"]["photos"][0]["url"], follow_redirects=False)
    assert res.status_code == 302 and res.headers["location"].startswith("https://lh3.googleusercontent.com/") and "key" not in res.headers["location"]
    assert apis["alice"].client.get(f"/api/venue-photos/{o['id']}/9", follow_redirects=False).status_code == 404


def test_muse_picks_from_google_candidates_and_unknown_ids_are_ignored(settings, google):
    fake = FakeMuse([answer({"venues": [
        {"id": "c", "why": "Quiet and central.", "description": "Big reading rooms."},
        {"id": "made-up", "why": "x", "description": "y"},
        {"id": "a", "why": "Great espresso near everyone.", "description": "Espresso bar."},
    ]})])
    result = VenueAgent(fake, settings).suggest(REQ)
    assert [o["name"] for o in result.options][:2] == ["Gamma Library", "Alpha Cafe"] and len(result.options) == 3
    assert result.options[0]["why"] == "Quiet and central." and result.options[0]["category"] == "library"
    req = fake.responses.requests[0]
    assert "tools" not in req and "Alpha Cafe" in str(req["input"])  # no slow web search: Google already found them


def test_web_search_picks_get_google_details_or_a_checked_osm_pin(group, monkeypatch, settings):
    from app.services import gplaces, venue_votes

    apis, pid = group
    near, lost = venue("Near Cafe"), venue("Lost Cafe", area="1 Elm St")
    agent = VenueAgent(FakeMuse(grounded(near, lost)), settings)
    monkeypatch.setattr(venue_votes.VenueVoting, "__init__", lambda self, db, s, a=None: (setattr(self, "db", db), setattr(self, "settings", s), setattr(self, "agent", agent))[0])
    monkeypatch.setattr(settings, "google_maps_api_key", "test-key")
    monkeypatch.setattr(gplaces, "search", lambda *a, **k: [])  # Google has no candidates: Muse web search runs
    monkeypatch.setattr(gplaces, "lookup", lambda name, *a, **k: gplaces.summarize(gplace("n", name, 39.952, -75.162)) if name == "Near Cafe" else None)
    tried = []

    def geocode(q, enabled=True):
        tried.append(q)
        return (40.71, -74.0) if q == "Lost Cafe, 1 Elm St" else (39.97, -75.14) if q == "1 Elm St" else None  # first hit is in New York

    monkeypatch.setattr(venue_votes, "geocode_place", geocode)
    opts = {o["name"]: o for o in apis["alice"].post(poll_url(pid)).json()["options"]}
    assert opts["Near Cafe"]["place"]["rating"] == 4.6 and opts["Near Cafe"]["latitude"] == 39.952
    assert (opts["Lost Cafe"]["latitude"], opts["Lost Cafe"]["longitude"]) == (39.97, -75.14) and opts["Lost Cafe"]["place"] is None
    assert tried[:2] == ["Lost Cafe, 1 Elm St", "1 Elm St"]


def test_a_far_away_member_still_gets_places_with_pins_in_the_plan_city(settings, google, monkeypatch):
    """Someone sharing from ~45 km away moves the middle out of town: places in the plan's city still count."""
    from app.services import gplaces

    far_mid = VenueRequest(city="Philadelphia", midpoint=(40.35, -75.16), local_time="Sunday 18:00", activity="Coffee")
    result = VenueAgent(None, settings).suggest(far_mid)
    assert result.source == "google" and len(result.options) == 3 and all(o["latitude"] for o in result.options)
    assert "Far Cafe" not in [o["name"] for o in result.options]  # New York: not near, not in the city
    hit = gplaces.summarize(gplace("z", "Zed Cafe", 39.95, -75.16))
    assert gplaces.near_enough(hit, (40.35, -75.16), 30, "Philadelphia")  # "... Main St, Philadelphia" is in the city
    assert not gplaces.near_enough(hit, (40.35, -75.16), 30, "Pittsburgh")


def test_spread_out_group_widens_the_reach(group, users, db):
    from app.models import Proposal
    from app.services.venue_votes import VenueVoting

    apis, pid = group
    near = VenueVoting(db, get_settings()).request_for(db.get(Proposal, UUID(pid)))
    assert near.reach_km == 30
    assert apis["alice"].put(f"/api/proposals/{pid}/location", {"latitude": 39.95, "longitude": -75.16}).status_code == 200
    names = [n for n in apis if n != "alice"]
    assert apis[names[0]].put(f"/api/proposals/{pid}/location", {"latitude": 40.45, "longitude": -75.16}).status_code == 200  # ~55 km north
    db.expire_all()
    wide = VenueVoting(db, get_settings()).request_for(db.get(Proposal, UUID(pid)))
    assert wide.reach_km > 40

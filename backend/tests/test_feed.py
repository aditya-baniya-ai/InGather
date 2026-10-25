"""Synthetic Austin demo, Home feed and join requests (a small seed: 80 people, 8 groups, to keep tests fast)."""

import re

import pytest
from sqlalchemy import select

from app.demo.austin import DOMAIN, AustinSeeder, is_synthetic
from app.demo.people import generate
from app.models import Block, JoinRequest, JoinStatus, MemberStatus, Plan, Proposal, User
from app.services.feed import Feed, auto_respond


@pytest.fixture
def austin(db, users, settings):
    stats = AustinSeeder(db, settings, n=80, groups=8).run()
    assert stats["created"] == 80 and stats["groups"] == 8, stats
    return stats


def groups(db) -> list[Proposal]:
    return [p for p in db.scalars(select(Proposal)) if p.open_to_requests]


def test_people_look_real_and_say_when_they_are_free():
    people = generate(300)
    assert len({p.email for p in people}) == 300 and len({p.name for p in people}) == 300
    for p in people[:50]:
        assert re.fullmatch(r"[A-Z][a-z]+ [A-Z][a-z]+", p.name)
        assert 60 < len(p.bio) <= 280 and "free" in p.bio.lower() and p.area[0] in p.bio
        assert 3 <= len(p.interests) <= 6 and p.patterns
    assert generate(5) == generate(5)  # same people on every machine


def test_seed_is_idempotent_and_plans_are_in_austin(db, settings, austin):
    again = AustinSeeder(db, settings, n=80, groups=8).run()
    assert again["created"] == 0 and again["groups"] == 8
    people = list(db.scalars(select(User).where(User.email.like(f"%{DOMAIN}"))))
    assert len(people) == 80 and all(is_synthetic(u) and u.avatar_url.startswith("/api/demo/avatars/") for u in people)
    plans = list(db.scalars(select(Plan).where(Plan.owner_id.in_([u.id for u in people]))))
    assert {p.city for p in plans} == {"Austin"} and all(p.windows for p in plans)


def test_seeded_groups_have_one_or_two_open_spots(db, settings, austin):
    feed = Feed(db, settings)
    for p in groups(db):
        plan = db.get(Plan, p.plan_id)
        assert feed.joinable(p, plan) and 1 <= feed.spots_left(p, plan) <= 2
        assert all(m.status == MemberStatus.accepted for m in p.members)
        assert plan.title in p.activity_title or plan.title[1:] in p.activity_title


def test_feed_ranks_open_groups_without_revealing_details(db, users, settings, austin):
    items = Feed(db, settings).items(users["alice"])
    assert len(items) == 8
    for i in items:
        assert 0 <= i.match <= 100 and i.spots_left >= 1 and i.city == "Austin"
        assert i.part_of_day in ("morning", "afternoon", "evening") and " " not in i.host.first_name
        assert i.request_status is None and i.free_then is None  # Alice has no Austin plan
    dumped = items[0].model_dump()
    assert "venue_label" not in dumped and "start_at" not in dumped and "email" not in str(dumped)


def test_feed_sorts_by_match_or_soonest_and_keeps_requests_on_top(db, users, settings, austin):
    feed, alice = Feed(db, settings), users["alice"]
    by_match = feed.items(alice, sort="match")
    assert [i.match for i in by_match] == sorted((i.match for i in by_match), reverse=True)
    starts = {p.id: p.start_at for p in groups(db)}
    soonest = feed.items(alice, sort="soonest")
    assert [starts[i.proposal_id] for i in soonest] == sorted(starts[i.proposal_id] for i in soonest)
    assert {i.proposal_id for i in by_match} == {i.proposal_id for i in soonest}
    last = soonest[-1].proposal_id
    feed.request(alice, last, None)
    for order in ("match", "soonest"):
        assert feed.items(alice, sort=order)[0].proposal_id == last  # a pending request stays first


def test_feed_filters_by_category_and_seeding_covers_every_category(db, users, settings, austin):
    from collections import Counter

    feed = Feed(db, settings)
    kinds = Counter(i.activity_type for i in feed.items(users["alice"]))
    assert len(kinds) >= 3  # groups aren't all coffee meetups
    for kind in kinds:
        only = feed.items(users["alice"], activity=kind)
        assert len(only) == kinds[kind] and {i.activity_type for i in only} == {kind}


def test_repeated_first_names_get_a_last_initial():
    from types import SimpleNamespace

    from app.services.feed import short_names
    people = [SimpleNamespace(display_name=n) for n in ("Jamal Reyes", "Jamal Tran", "Jose Cruz")]
    assert short_names(people) == ["Jamal R.", "Jamal T.", "Jose"]


def test_blocked_hosts_and_members_are_hidden(db, users, settings, austin):
    target = groups(db)[0]
    db.add(Block(blocker_id=target.members[-1].user_id, blocked_id=users["alice"].id))
    db.commit()
    assert target.id not in {i.proposal_id for i in Feed(db, settings).items(users["alice"])}


def test_join_request_accept_adds_member_and_welcomes(db, users, settings, austin):
    feed, alice = Feed(db, settings), users["alice"]
    target = groups(db)[0]
    version = target.version
    req = feed.request(alice, target.id, "Hi! I'd love to come.")
    assert req.status == JoinStatus.pending and 0 < req.score < 1
    assert feed.request(alice, target.id, "again") is req  # no duplicates
    assert [r.display_name for r in feed.for_owner(target)] == ["Alice"]
    feed.decide(target, req.id, accept=True)
    db.refresh(target)
    me = next(m for m in target.members if m.user_id == alice.id)
    assert me.status == MemberStatus.accepted and target.version == version + 1
    assert req.welcome and "Alice" in req.welcome
    item = next(i for i in feed.items(alice) if i.proposal_id == target.id)
    assert item.request_status == "accepted" and item.welcome == req.welcome
    from app.services.policy import Policy
    assert Policy(db, settings).viewer_role(alice, target) == "member"


def test_declined_requests_disappear_and_full_groups_close(db, users, settings, austin):
    feed = Feed(db, settings)
    target = groups(db)[1]
    req = feed.request(users["alice"], target.id, None)
    feed.decide(target, req.id, accept=False)
    assert target.id not in {i.proposal_id for i in feed.items(users["alice"])}
    with pytest.raises(Exception):
        feed.request(users["alice"], target.id, None)  # 404: not asking again
    plan = db.get(Plan, target.plan_id)
    for name in ("maya", "jordan", "sofia", "taylor"):
        if not feed.joinable(target, plan):
            break
        r = feed.request(users[name], target.id, None)
        feed.decide(target, r.id, accept=True)
    assert not feed.joinable(target, plan) and target.id not in {i.proposal_id for i in feed.items(users["priya"])}


def test_demo_hosts_answer_on_their_own(db, users, settings, austin):
    target = groups(db)[2]
    req = Feed(db, settings).request(users["alice"], target.id, None)
    auto_respond(req.id, delay=0)
    db.expire_all()
    assert db.get(JoinRequest, req.id).status in (JoinStatus.accepted, JoinStatus.declined)


def test_feed_api_join_draft_and_avatars(db, users, as_user, austin, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app import db as app_db
    from app.api import feed as feed_api

    monkeypatch.setattr(feed_api, "auto_respond", lambda rid: auto_respond(rid, delay=0))
    app = FastAPI()
    app.include_router(feed_api.router)

    def get_db():
        with app_db.SessionLocal() as session:
            yield session

    app.dependency_overrides[app_db.get_db] = get_db
    c = TestClient(app)
    alice = as_user(users["alice"])
    alice.client = c
    items = alice.get("/api/feed").json()
    assert len(items) == 8
    pid = items[0]["proposal_id"]
    draft = alice.post(f"/api/proposals/{pid}/join/draft").json()
    assert draft["mode"] == "template" and draft["message"].startswith("Hi!")  # no Muse key in tests
    res = alice.post(f"/api/proposals/{pid}/join", {"message": draft["message"]})
    assert res.status_code == 201 and res.json()["request_status"] in ("pending", "accepted", "declined")
    assert c.get("/api/feed").status_code == 401
    svg = c.get("/api/demo/avatars/atx-0001.svg")
    assert svg.status_code == 200 and svg.headers["content-type"].startswith("image/svg") and svg.text.startswith("<svg")
    assert c.get("/api/demo/avatars/alice.svg").status_code == 404


def test_your_groups_lists_hosted_and_joined_groups(db, users, settings, austin, as_user, client):
    """After a join is accepted, the group shows up for the new member and for the host, with the same people."""
    target = groups(db)[0]
    feed = Feed(db, settings)
    req = feed.request(users["alice"], target.id, None)
    feed.decide(target, req.id, accept=True)
    host = db.get(User, target.owner_id)
    mine = as_user(users["alice"]).get("/api/groups").json()
    theirs = as_user(host).get("/api/groups").json()
    a = next(g for g in mine if g["proposal_id"] == str(target.id))
    h = next(g for g in theirs if g["proposal_id"] == str(target.id))
    assert a["role"] == "member" and h["role"] == "host" and a["host_name"] == host.display_name
    assert a["members"] == h["members"] and "Alice" in [m["first_name"] for m in a["members"]]
    assert a["members"][0]["first_name"] == host.display_name.split(" ")[0]  # host first
    assert as_user(users["eve"]).get("/api/groups").json() == []


def test_public_plan_is_posted_to_the_feed_and_private_takes_it_down(users, plan_of, as_user):
    alice, maya = as_user(users["alice"]), as_user(users["maya"])
    plan_id = plan_of(users["alice"]).id  # Alice's plan starts private
    first = maya.get("/api/feed")
    assert not [i for i in first.json() if i["host"]["first_name"] == "Alice"]
    assert alice.post(f"/api/plans/{plan_id}/discovery", {"mode": "mutual_discovery", "ai_consent": True}).status_code == 200
    posted = [i for i in maya.get("/api/feed").json() if i["host"]["first_name"] == "Alice"]
    assert len(posted) == 1 and posted[0]["spots_left"] >= 1
    assert maya.post(f"/api/proposals/{posted[0]['proposal_id']}/join", {"message": "Hi!"}).status_code == 201
    alice.post(f"/api/plans/{plan_id}/discovery", {"mode": "private_browse", "ai_consent": True})
    assert not [i for i in as_user(users["sofia"]).get("/api/feed").json() if i["host"]["first_name"] == "Alice"]

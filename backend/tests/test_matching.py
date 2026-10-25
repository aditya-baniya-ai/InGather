from datetime import date

import pytest

from app.config import Settings
from app.models import Block, DiscoveryMode, PlanStatus, Verification
from app.services.matching import Matching


@pytest.fixture
def matching(db, settings):
    return Matching(db, settings)


def names(cands):
    return {c.display_name for c in cands}


def test_alice_finds_at_least_four_opted_in_candidates(users, plan_of, matching):
    found = names(matching.find_candidates(plan_of(users["alice"]), set(), 12))
    assert {"Maya", "Sofia", "Jordan", "Taylor"} <= found
    assert not found & {"Alice", "Eve", "Noah", "Diego"}  # self, blocked, private_browse, other city


def test_matcher_ranks_best_fit_first(users, plan_of, matching):
    cands = matching.find_candidates(plan_of(users["alice"]), set(), 12)
    # Maya and Jordan: same conference, most shared interests. Sofia: shares coffee and city exploring.
    assert [c.display_name for c in cands[:3]] == ["Maya", "Jordan", "Sofia"]
    assert cands == sorted(cands, key=lambda c: -c.score) and all(0 < c.score < 1 for c in cands)
    maya = cands[0]
    assert maya.shared_interests == ["tech", "food", "city exploring"]
    assert not hasattr(maya, "goal_text") and not hasattr(maya, "windows")


def test_eligible_is_unscored_and_stable(users, plan_of, matching):
    pool = matching.eligible(plan_of(users["alice"]), set())
    assert [c.display_name for c in pool] == sorted(c.display_name for c in pool) and all(c.score == 0 for c in pool)
    assert {c.display_name for c in pool} == names(matching.find_candidates(plan_of(users["alice"]), set(), 99))


def test_note_interests_change_the_ranking(users, plan_of, matching):
    plan = plan_of(users["alice"])
    before = {c.display_name: c.score for c in matching.find_candidates(plan, set(), 12)}
    after = {c.display_name: c.score for c in matching.find_candidates(plan, set(), 12, extra_interests=["jazz", "live music"])}
    assert after["Marcus"] > before["Marcus"]  # Marcus is into jazz


def test_excluded_users_are_skipped(users, plan_of, matching):
    found = names(matching.find_candidates(plan_of(users["alice"]), {users["maya"].id}, 12))
    assert "Maya" not in found and "Sofia" in found


def test_block_excludes_both_directions(db, users, plan_of, matching):
    db.add(Block(blocker_id=users["maya"].id, blocked_id=users["sofia"].id))
    db.commit()
    assert "Sofia" not in names(matching.find_candidates(plan_of(users["maya"]), set(), 12))
    assert "Maya" not in names(matching.find_candidates(plan_of(users["sofia"]), set(), 12))


def test_paused_cancelled_and_unverified_are_never_candidates(db, users, plan_of, matching):
    plan_of(users["maya"]).status = PlanStatus.cancelled
    plan_of(users["sofia"]).discovery_mode = DiscoveryMode.paused
    users["jordan"].discovery_paused = True
    users["taylor"].verification = Verification.unverified
    users["priya"].is_adult = False
    db.commit()
    found = names(matching.find_candidates(plan_of(users["alice"]), set(), 12))
    assert not found & {"Maya", "Sofia", "Jordan", "Taylor", "Priya"}
    assert found  # others still there


def test_verified_demo_only_counts_in_demo_mode(db, users, plan_of):
    prod = Matching(db, Settings(demo_mode=False, model_api_key=""))
    assert prod.find_candidates(plan_of(users["alice"]), set(), 12) == []


def test_non_overlapping_dates_or_times_excluded(db, users, plan_of, matching):
    plan_of(users["maya"]).start_date, plan_of(users["maya"]).end_date = date(2027, 2, 1), date(2027, 2, 2)
    db.commit()
    assert "Maya" not in names(matching.find_candidates(plan_of(users["alice"]), set(), 12))


def test_city_match_is_case_insensitive(db, users, plan_of, matching):
    plan_of(users["sofia"]).city = "PHILADELPHIA"
    db.commit()
    assert "Sofia" in names(matching.find_candidates(plan_of(users["alice"]), set(), 12))


def test_group_availability_is_group_level_intersection(users, plan_of, matching):
    alice = plan_of(users["alice"])
    ok = matching.group_availability(alice, [users["sofia"].id, users["jordan"].id])
    assert ok.possible
    assert all((e - s).total_seconds() == 90 * 60 for s, e in ok.windows)  # 18:00-19:30 local each day
    assert ok.windows[0][0].isoformat() == "2027-01-17T23:00:00+00:00"
    # Maya (5-7pm) and Marcus (7-11pm) never overlap
    bad = matching.group_availability(alice, [users["maya"].id, users["marcus"].id])
    assert not bad.possible and bad.windows == []


def test_group_availability_ignores_ineligible_users(users, plan_of, matching):
    # Eve is blocked by Alice and Noah is private: they contribute no windows, so no group is possible
    alice = plan_of(users["alice"])
    assert not matching.group_availability(alice, [users["eve"].id]).possible
    assert not matching.group_availability(alice, [users["noah"].id]).possible

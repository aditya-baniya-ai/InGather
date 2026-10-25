"""The InGather matcher: shipped artifacts, interest embeddings, features and model behavior."""

import json
import math

import numpy as np
import pytest

from app.ml.features import FEATURES, MONOTONIC, Context, interest_features, pair_features
from app.ml.interests import InterestSpace, normalize, spellings
from app.ml.model import ARTIFACTS, TreeEnsemble, load_matcher


@pytest.fixture(scope="module")
def matcher():
    return load_matcher()


def fit(matcher, owner, theirs, **ctx):
    c = Context(ctx.get("same_activity", False), ctx.get("same_intent", False), ctx.get("same_event", False), ctx.get("hours", 2.0))
    return float(matcher.predict([pair_features(matcher.space.profile(owner), matcher.space.profile(theirs), c)])[0])


def test_artifacts_load_and_describe_themselves(matcher):
    card = json.loads((ARTIFACTS / "metrics.json").read_text())
    assert matcher.version == card["version"] and card["features"] == list(FEATURES)
    assert len(matcher.space.tags) == card["vocabulary"] and matcher.space.matrix.shape[1] == card["embedding_dim"]
    assert card["export_max_abs_diff"] < 1e-6  # exported trees reproduce scikit-learn exactly
    # Trained on real data: the model must beat the old hand-written shared-interest rule on held-out groups.
    real = card["real_interest_eval"]
    assert real["gradient_boosting"]["auc"] > real["old_rule_shared_interests"]["auc"] + 0.05
    assert real["gradient_boosting"]["precision_at_5"] > real["old_rule_shared_interests"]["precision_at_5"]


def test_spellings_and_aliases_reach_the_meetup_vocabulary(matcher):
    s = matcher.space
    assert normalize("  Live   Music ") == "live music"
    assert "livemusic" in spellings("live music") and "museum" in spellings("museums")
    assert s.key("Museums") == s.key("museum")  # exact matching ignores spelling variants
    for term in ("ai", "tech", "food", "coffee", "jazz", "city exploring", "hackathons", "books", "running"):
        assert s.vector(term) is not None, term
    assert s.vector("zzz-not-an-interest") is None


def test_embeddings_put_related_interests_close(matcher):
    v = matcher.space.vector
    assert v("ai") @ v("machine learning") > v("ai") @ v("knitting")
    assert v("hiking") @ v("camping") > v("hiking") @ v("programming")
    assert v("jazz") @ v("live music") > v("jazz") @ v("startups")


def test_interest_features_are_scale_free():
    space = InterestSpace(["a", "b", "c"], np.eye(3, dtype=np.float32))
    f = dict(zip(FEATURES, interest_features(space.profile(["a", "b"]), space.profile(["b", "c", "x"]))))
    assert f["shared"] == 1 and f["jaccard"] == pytest.approx(1 / 4) and f["coverage"] == pytest.approx(1 / 2)
    assert f["best_match"] == pytest.approx(0.5) and f["known_frac"] == pytest.approx(4 / 5)
    unknown = interest_features(space.profile(["x"]), space.profile(["y"]))
    assert math.isnan(unknown[3]) and unknown[0] == 0  # no embeddings: the model handles NaN


def test_scores_are_probabilities_and_handle_unknown_interests(matcher):
    p = fit(matcher, ["ai", "coffee"], ["quidditch-on-mars"])
    assert 0 < p < 1 and math.isfinite(p)
    assert fit(matcher, [], []) > 0


def test_more_fit_never_lowers_the_score(matcher):
    base = fit(matcher, ["tech", "food", "museums"], ["tech"])
    assert fit(matcher, ["tech", "food", "museums"], ["tech", "food"]) >= base
    assert fit(matcher, ["tech", "food", "museums"], ["tech"], same_activity=True) >= base
    assert fit(matcher, ["tech", "food", "museums"], ["tech"], hours=4) >= base
    assert fit(matcher, ["tech", "food", "museums"], ["tech"], same_event=True) >= base


def test_shared_and_related_interests_beat_unrelated_ones(matcher):
    owner = ["ai", "coffee", "museums"]
    assert fit(matcher, owner, ["ai", "coffee"]) > fit(matcher, owner, ["knitting", "motorcycle"])
    assert fit(matcher, owner, ["machine learning", "art"]) > fit(matcher, owner, ["knitting", "motorcycle"])


def test_monotonic_constraints_cover_every_feature():
    assert len(MONOTONIC) == len(FEATURES)


def test_tree_ensemble_follows_missing_value_branches():
    leaf = lambda v: {"feature": [0], "threshold": [0.0], "missing_left": [False], "left": [0], "right": [0], "leaf": [True], "value": [v]}  # noqa: E731
    split = {"feature": [3, 0, 0], "threshold": [0.5, 0, 0], "missing_left": [True, False, False], "left": [1, 0, 0],
             "right": [2, 0, 0], "leaf": [False, True, True], "value": [0.0, -1.0, 1.0]}
    model = TreeEnsemble({"features": list(FEATURES), "baseline": 0.0, "trees": [split, leaf(0.5)]})
    row = [0.0] * len(FEATURES)
    raw = model.raw(np.array([[*row[:3], 0.9, *row[4:]], [*row[:3], 0.1, *row[4:]], [*row[:3], math.nan, *row[4:]]]))
    assert raw.tolist() == [1.5, -0.5, -0.5]  # right, left, and NaN goes left
    with pytest.raises(ValueError):
        TreeEnsemble({"features": ["other"], "baseline": 0, "trees": []})

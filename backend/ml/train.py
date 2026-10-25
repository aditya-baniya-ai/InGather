"""Train the InGather matcher.

    uv run python ml/fetch_data.py                # once: public Meetup.com dataset -> ml/data/
    uv run --group train python ml/train.py       # -> app/ml/artifacts/{interests.npz, matcher.json, metrics.json}

1. Interest embeddings (real data). Topic co-occurrence across 1.7M real Meetup members' topic lists, as PPMI and
   then truncated SVD, so related interests sit close together.
2. Interest-fit examples (real data). Positives: a group's topics vs. a member's topics. Negatives: people from
   the same local network (members of groups that this group's members also joined) who did not join. That
   mirrors InGather, where every candidate is already nearby and available, and the question is who fits.
   Topic lists are subsampled to InGather's size (2-6 plan interests, 1-8 person interests).
3. Context (simulated). The Meetup data has no activity type, intent, shared event or free-time overlap, so those
   are drawn per example, and a real positive only stays positive if a simulated "the context works too" draw
   succeeds (CONTEXT_PRIOR below). This part is synthetic: retrain on real InGather outcomes once there are any.
4. Gradient-boosted trees (scikit-learn HistGradientBoosting, monotonic in every similarity), evaluated on groups
   never seen in training, then exported as JSON trees so serving needs only numpy.
"""

import hashlib
import json
import math
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import scipy.sparse as sp
import sklearn
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score
from sklearn.model_selection import GroupKFold
from sklearn.utils.extmath import randomized_svd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.ml.features import FEATURES, INTEREST_FEATURES, MONOTONIC, Context, context_features, interest_features  # noqa: E402
from app.ml.interests import ALIASES, InterestSpace  # noqa: E402
from app.ml.model import ARTIFACTS, TreeEnsemble  # noqa: E402

DATA = Path(__file__).parent / "data"
SEED = 7
VOCAB = 5000         # most common topics get an embedding
DIM = 64             # embedding size
GROUPS = 15000       # groups sampled for examples
PER_GROUP = 10       # positives (and as many negatives) per group
OOV_RATE = 0.08      # share of topics hidden from the vocabulary, so the model learns to handle unknown interests
VERSION = "matcher-1"

# Simulated context: logit of "the plan context also works for this person", given a real interest fit.
CONTEXT_PRIOR = {"bias": -1.0, "same_activity": 1.2, "same_intent": 0.5, "same_event": 0.9, "overlap_4h": 1.4}

rng = np.random.default_rng(SEED)
log = lambda *a: print(f"[{time.strftime('%H:%M:%S')}]", *a, flush=True)  # noqa: E731


# ---------- data ----------
def load():
    for f in ("tag_text.csv", "group_tag.csv", "user_tag.csv", "user_group.csv"):
        if not (DATA / f).exists():
            sys.exit(f"missing ml/data/{f}: run `uv run python ml/fetch_data.py` first")
    read = lambda f, cols: pd.read_csv(DATA / f, header=None, names=cols, dtype=np.int32)  # noqa: E731
    text = pd.read_csv(DATA / "tag_text.csv", header=None, names=["t", "text"], dtype={"t": np.int32, "text": str})
    return text.set_index("t").text, read("user_tag.csv", ["u", "t"]), read("group_tag.csv", ["g", "t"]), read("user_group.csv", ["u", "g"])


def digest(f: str) -> str:
    h = hashlib.sha256()
    with open(DATA / f, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


# ---------- 1. embeddings ----------
def embeddings(text: pd.Series, user_tag: pd.DataFrame) -> InterestSpace:
    top = user_tag.t.value_counts().index[:VOCAB].to_numpy()
    col = {t: i for i, t in enumerate(top)}
    x = user_tag[user_tag.t.isin(col)]
    users, row = np.unique(x.u.to_numpy(), return_inverse=True)
    M = sp.csr_matrix((np.ones(len(x), np.float32), (row, x.t.map(col).to_numpy())), shape=(len(users), len(top)))
    C = (M.T @ M).toarray().astype(np.float64)
    np.fill_diagonal(C, 0)
    total = C.sum()
    ctx = C.sum(0) ** 0.75  # context distribution smoothing (Levy et al. 2015)
    pmi = np.log(np.maximum(C * total, 1e-12) / (C.sum(1, keepdims=True) * (ctx / ctx.sum() * total)[None, :]))
    U, S, _ = randomized_svd(np.maximum(pmi, 0), DIM, random_state=SEED)
    E = (U * np.sqrt(S)).astype(np.float32)
    E /= np.linalg.norm(E, axis=1, keepdims=True) + 1e-9
    E = E.astype(np.float16).astype(np.float32)  # exactly what serving loads from interests.npz
    tags = [str(text.get(t, f"tag{t}")) for t in top]
    log(f"embeddings: {len(tags)} topics x {DIM} dims from {len(users):,} members")
    return InterestSpace(tags, E)


# ---------- 2. real interest-fit examples ----------
def subsample(tags: np.ndarray, lo: int, hi: int) -> list[str]:
    k = int(rng.integers(lo, hi + 1))
    pick = tags if len(tags) <= k else rng.choice(tags, k, replace=False)
    return [f"unknown-{rng.integers(1e9)}" if rng.random() < OOV_RATE else str(t) for t in pick]


def examples(space: InterestSpace, text, user_tag, group_tag, user_group, conservative=False) -> pd.DataFrame:
    known = set(space.tags)
    name = text.to_dict()
    utags = {u: np.array([name[t] for t in s if name.get(t) in known]) for u, s in user_tag.groupby("u").t}
    gtags = {g: np.array([name[t] for t in s if name.get(t) in known]) for g, s in group_tag.groupby("g").t}
    utags = {u: t for u, t in utags.items() if len(t)}
    gtags = {g: t for g, t in gtags.items() if len(t) >= 2}
    ug = user_group[user_group.u.isin(utags.keys()) & user_group.g.isin(gtags.keys())]
    members = ug.groupby("g").u.apply(np.array)
    joined = ug.groupby("u").g.apply(np.array)
    size = members.map(len)
    eligible = size[(size >= 30) & (size <= 3000)].index.to_numpy()
    groups = rng.choice(eligible, min(GROUPS, len(eligible)), replace=False)
    log(f"examples from {len(groups):,} of {len(eligible):,} eligible groups ({len(ug):,} memberships)")
    rows = []
    for n, g in enumerate(groups):
        mem = members[g]
        inside = set(mem.tolist())
        nearby = np.concatenate([joined[u] for u in rng.choice(mem, min(40, len(mem)), replace=False)])
        nearby = nearby[nearby != g]
        if not len(nearby):
            continue
        group_topics = set(gtags[g].tolist())
        plan = space.profile(subsample(gtags[g], 2, 6))

        def person(u):
            t = utags[u]
            if conservative:  # drop topics the group itself lists: only the person's *other* interests count
                t = np.array([x for x in t if x not in group_topics])
            return space.profile(subsample(t, 1, 8)) if len(t) else None

        pos = 0
        for u in rng.choice(mem, min(PER_GROUP, len(mem)), replace=False):
            if (p := person(u)) is not None:
                rows.append((g, 1, *interest_features(plan, p)))
                pos += 1
        for _ in range(pos * 3):
            if pos <= 0:
                break
            v = rng.choice(members[rng.choice(nearby)])
            if v in inside or (p := person(v)) is None:
                continue
            rows.append((g, 0, *interest_features(plan, p)))
            pos -= 1
        if n % 3000 == 2999:
            log(f"  {n + 1:,} groups, {len(rows):,} examples")
    return pd.DataFrame(rows, columns=["group", "y", *INTEREST_FEATURES])


# ---------- 3. simulated context ----------
def add_context(d: pd.DataFrame) -> pd.DataFrame:
    n = len(d)
    same_event = rng.random(n) < 0.3
    same_activity = same_event | (rng.random(n) < 0.45)
    same_intent = rng.random(n) < 0.55
    overlap = np.round(rng.uniform(0.5, 8.0, n) * 2) / 2
    ctx = np.array([context_features(Context(a, b, c, h)) for a, b, c, h in zip(same_activity, same_intent, same_event, overlap)])
    p = CONTEXT_PRIOR
    logit = p["bias"] + p["same_activity"] * ctx[:, 0] + p["same_intent"] * ctx[:, 1] + p["same_event"] * ctx[:, 2] + p["overlap_4h"] * np.minimum(ctx[:, 3], 4) / 4
    works = rng.random(n) < 1 / (1 + np.exp(-logit))
    out = d.copy()
    out[list(FEATURES[7:])] = ctx
    out["y_interest"] = d.y
    out["y"] = (d.y.astype(bool) & works).astype(int)
    return out


# ---------- models & metrics ----------
def gbm(features, iters=400):
    mono = [MONOTONIC[FEATURES.index(f)] for f in features]
    return HistGradientBoostingClassifier(
        max_iter=iters, learning_rate=0.06, max_leaf_nodes=24, min_samples_leaf=80, l2_regularization=1.0,
        monotonic_cst=mono, early_stopping=True, validation_fraction=0.1, n_iter_no_change=30, random_state=SEED,
    )


def precision_at(d: pd.DataFrame, score: np.ndarray, k=5) -> float:
    """Of the k people ranked highest for each group, the share who really joined it (ties broken at random)."""
    t = d.assign(s=score + rng.random(len(d)) * 1e-6)
    return float(t.sort_values("s", ascending=False).groupby("group").head(k).y.mean())


def ece(y, p, bins=10) -> float:
    edges = np.linspace(0, 1, bins + 1)
    idx = np.clip(np.digitize(p, edges) - 1, 0, bins - 1)
    return float(sum(abs(p[idx == b].mean() - y[idx == b].mean()) * (idx == b).mean() for b in range(bins) if (idx == b).any()))


def report(y, p, d=None, scores_only=False) -> dict:
    """Ranking quality always; probability quality (log loss, Brier, calibration error) for models, not hand scores."""
    out = {"auc": roc_auc_score(y, p)}
    if not scores_only:
        out |= {"log_loss": log_loss(y, np.clip(p, 1e-6, 1 - 1e-6)), "brier": brier_score_loss(y, p), "ece": ece(y, p)}
    if d is not None:
        out["precision_at_5"] = precision_at(d, p)
    return {k: round(float(v), 4) for k, v in out.items()}


def cross_validated(d: pd.DataFrame, features, make) -> np.ndarray:
    pred = np.zeros(len(d))
    for tr, te in GroupKFold(5).split(d, d.y, d.group):
        pred[te] = make().fit(d.iloc[tr][features], d.y.iloc[tr]).predict_proba(d.iloc[te][features])[:, 1]
    return pred


def lr():
    from sklearn.impute import SimpleImputer
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    return make_pipeline(SimpleImputer(strategy="median"), StandardScaler(), LogisticRegression(max_iter=1000))


def old_rule(d: pd.DataFrame) -> np.ndarray:
    """The hand-written score the app used before: 3/shared interest + 2 same activity + 1 same intent + 1/hour (max 4)."""
    return 3 * d.shared + 2 * d.get("same_activity", 0) + d.get("same_intent", 0) + np.minimum(d.get("overlap_hours", 0) // 1, 4)


# ---------- export ----------
def export(clf: HistGradientBoostingClassifier) -> dict:
    trees = []
    for (pred,) in clf._predictors:
        n = pred.nodes
        trees.append({
            "feature": n["feature_idx"].tolist(), "threshold": [float(x) for x in n["num_threshold"]],
            "missing_left": n["missing_go_to_left"].astype(bool).tolist(), "left": n["left"].tolist(),
            "right": n["right"].tolist(), "leaf": n["is_leaf"].astype(bool).tolist(), "value": [float(x) for x in n["value"]],
        })
    return {"features": list(FEATURES), "baseline": float(np.ravel(clf._baseline_prediction)[0]), "trees": trees}


def main() -> int:
    t0 = time.time()
    text, user_tag, group_tag, user_group = load()
    log(f"loaded {len(user_tag):,} member topics, {len(group_tag):,} group topics, {len(user_group):,} memberships")
    space = embeddings(text, user_tag)
    missing = sorted({a for tags in ALIASES.values() for a in tags if a not in space.index})
    if missing:
        log(f"note: alias topics outside the vocabulary (ignored): {missing}")

    real = examples(space, text, user_tag, group_tag, user_group)
    log(f"real interest examples: {len(real):,} ({real.y.mean():.0%} positive)")
    feats = list(INTEREST_FEATURES)
    real_eval = {
        "examples": len(real), "groups": int(real.group.nunique()), "positive_rate": round(float(real.y.mean()), 4),
        "old_rule_shared_interests": report(real.y, real.shared.to_numpy(float), real, scores_only=True),
        "logistic_regression": report(real.y, cross_validated(real, feats, lr), real),
        "gradient_boosting": report(real.y, cross_validated(real, feats, lambda: gbm(feats)), real),
    }
    log("real data, 5-fold by group:", json.dumps(real_eval))

    strict = examples(space, text, user_tag, group_tag, user_group, conservative=True)
    real_eval["leak_check_other_interests_only"] = report(strict.y, cross_validated(strict, feats, lambda: gbm(feats)), strict)
    log("leak check:", real_eval["leak_check_other_interests_only"])

    full = add_context(real)
    groups = full.group.unique()
    test_groups = set(rng.choice(groups, len(groups) // 5, replace=False).tolist())
    is_test = full.group.isin(test_groups).to_numpy()
    train, test = full[~is_test], full[is_test]
    clf = gbm(list(FEATURES)).fit(train[list(FEATURES)], train.y)
    p = clf.predict_proba(test[list(FEATURES)])[:, 1]
    full_eval = {
        "train_examples": len(train), "test_examples": len(test), "iterations": int(clf.n_iter_),
        "positive_rate": round(float(full.y.mean()), 4),
        "old_rule": report(test.y.to_numpy(), old_rule(test).to_numpy(float), test, scores_only=True),
        "matcher": report(test.y.to_numpy(), p, test),
        "matcher_vs_real_interest_label": report(test.y_interest.to_numpy(), p, test.assign(y=test.y_interest)),
    }
    log("held-out groups (semi-synthetic):", json.dumps(full_eval))

    final = gbm(list(FEATURES), iters=clf.n_iter_)
    final.set_params(early_stopping=False)
    final.fit(full[list(FEATURES)], full.y)
    spec = export(final)
    check = full[list(FEATURES)].sample(5000, random_state=SEED)
    drift = float(np.abs(TreeEnsemble(spec).predict(check.to_numpy()) - final.predict_proba(check)[:, 1]).max())
    if drift > 1e-6:
        sys.exit(f"exported trees disagree with scikit-learn by {drift}")

    probes = {}
    for a, b in [("ai", "machine learning"), ("ai", "data science"), ("hiking", "camping"), ("coffee", "brunch"),
                 ("jazz", "live music"), ("museums", "art"), ("startups", "entrepreneurs"), ("ai", "knitting")]:
        va, vb = space.vector(a), space.vector(b)
        probes[f"{a} ~ {b}"] = round(float(va @ vb), 3) if va is not None and vb is not None else None

    card = {
        "version": VERSION, "trained_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "sklearn": sklearn.__version__, "seed": SEED, "features": list(FEATURES), "trees": len(spec["trees"]),
        "vocabulary": len(space.tags), "embedding_dim": DIM, "context_prior": CONTEXT_PRIOR,
        "data": {"source": "Meetup.com dataset, Liu et al. KDD 2012 (github.com/wuyuehit/meetup_dataset)",
                 "sha256": {f: digest(f) for f in ("tag_text.csv", "group_tag.csv", "user_tag.csv", "user_group.csv")}},
        "real_interest_eval": real_eval, "held_out_eval": full_eval, "similarity_probes": probes,
        "export_max_abs_diff": drift, "seconds": round(time.time() - t0),
    }
    spec["card"] = {k: card[k] for k in ("version", "trained_at", "features", "trees", "vocabulary")}
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(ARTIFACTS / "interests.npz", tags=np.array(space.tags), matrix=space.matrix.astype(np.float16))
    (ARTIFACTS / "matcher.json").write_text(json.dumps(spec, separators=(",", ":")))
    (ARTIFACTS / "metrics.json").write_text(json.dumps(card, indent=2))
    log(f"saved artifacts to {ARTIFACTS} in {card['seconds']}s")
    log("similarity probes:", probes)
    return 0


if __name__ == "__main__":
    sys.exit(main())

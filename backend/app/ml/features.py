"""Pair features for the matcher. The single definition used by both training (backend/ml/train.py) and serving
(app/services/gather.py), so the model always sees features computed the same way.

`a` is the side that defines the activity (the owner's plan, or a Meetup group in training) and `b` the person
being considered. Interest features are scale-free (ratios and similarities), so they mean the same thing for a
Meetup member with 20 topics and an InGather user with 4 interests.
"""

import math
from dataclasses import dataclass

import numpy as np

from app.ml.interests import Profile

FEATURES: tuple[str, ...] = (
    "shared",          # interests in common (exact, after canonicalizing spellings)
    "jaccard",         # shared / all distinct interests
    "coverage",        # share of the plan's interests the person has
    "centroid_cos",    # cosine between the two interest profiles in embedding space
    "best_match",      # for each plan interest, the closest interest the person has (mean)
    "best_match_rev",  # for each of the person's interests, the closest plan interest (mean)
    "known_frac",      # how much of both profiles the embedding vocabulary covers
    "same_activity",   # same kind of plan (conference, travel, ...)
    "same_intent",     # both want friends / networking / an activity partner
    "same_event",      # both gave the same public event location
    "overlap_hours",   # hours of free time the two have in common (capped at 12)
)
# More of any similarity, shared context or shared time never lowers the score. known_frac is unconstrained.
MONOTONIC: tuple[int, ...] = (1, 1, 1, 1, 1, 1, 0, 1, 1, 1, 1)
INTEREST_FEATURES = FEATURES[:7]


@dataclass
class Context:
    same_activity: bool
    same_intent: bool
    same_event: bool
    overlap_hours: float


def interest_features(a: Profile, b: Profile) -> list[float]:
    A, B = set(a.keys), set(b.keys)
    shared = len(A & B)
    union = len(A | B)
    ka, kb = a.known, b.known
    if len(ka) and len(kb):
        sims = ka @ kb.T
        ca, cb = ka.mean(0), kb.mean(0)
        denom = float(np.linalg.norm(ca) * np.linalg.norm(cb))
        cos = float(ca @ cb / denom) if denom else math.nan
        best, rev = float(sims.max(1).mean()), float(sims.max(0).mean())
    else:
        cos = best = rev = math.nan  # the model was trained to handle unknown interests (NaN)
    total = len(a.keys) + len(b.keys)
    return [
        float(shared),
        shared / union if union else 0.0,
        shared / len(A) if A else 0.0,
        cos,
        best,
        rev,
        (len(ka) + len(kb)) / total if total else 0.0,
    ]


def context_features(c: Context) -> list[float]:
    return [float(c.same_activity), float(c.same_intent), float(c.same_event), min(max(c.overlap_hours, 0.0), 12.0)]


def pair_features(a: Profile, b: Profile, c: Context) -> list[float]:
    return interest_features(a, b) + context_features(c)

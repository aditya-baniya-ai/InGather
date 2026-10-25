"""Serving side of the matcher: loads the exported gradient-boosted trees and the interest embeddings.

The model is trained with scikit-learn (backend/ml/train.py) and exported as plain JSON trees, so serving needs
only numpy: no pickle files, and no scikit-learn version has to match at runtime.
"""

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np

from app.ml.features import FEATURES
from app.ml.interests import InterestSpace

ARTIFACTS = Path(__file__).parent / "artifacts"


@dataclass
class Tree:
    feature: np.ndarray
    threshold: np.ndarray
    missing_left: np.ndarray
    left: np.ndarray
    right: np.ndarray
    leaf: np.ndarray
    value: np.ndarray


class TreeEnsemble:
    """Binary gradient-boosted trees: p = sigmoid(baseline + sum of leaf values)."""

    def __init__(self, spec: dict):
        if tuple(spec["features"]) != FEATURES:
            raise ValueError("model was trained on a different feature list; retrain with backend/ml/train.py")
        self.baseline = float(spec["baseline"])
        self.trees = [
            Tree(
                np.asarray(t["feature"], np.int64), np.asarray(t["threshold"], np.float64),
                np.asarray(t["missing_left"], bool), np.asarray(t["left"], np.int64), np.asarray(t["right"], np.int64),
                np.asarray(t["leaf"], bool), np.asarray(t["value"], np.float64),
            )
            for t in spec["trees"]
        ]

    def raw(self, X: np.ndarray) -> np.ndarray:
        X = np.asarray(X, np.float64)
        out = np.full(len(X), self.baseline)
        rows = np.arange(len(X))
        for t in self.trees:
            node = np.zeros(len(X), np.int64)
            while not t.leaf[node].all():
                live = ~t.leaf[node]
                n = node[live]
                x = X[rows[live], t.feature[n]]
                go_left = np.where(np.isnan(x), t.missing_left[n], x <= t.threshold[n])
                node[live] = np.where(go_left, t.left[n], t.right[n])
            out += t.value[node]
        return out

    def predict(self, X: np.ndarray) -> np.ndarray:
        return 1.0 / (1.0 + np.exp(-self.raw(X)))


@dataclass
class Matcher:
    space: InterestSpace
    model: TreeEnsemble
    card: dict

    @property
    def version(self) -> str:
        return self.card.get("version", "unknown")

    def predict(self, rows: list[list[float]]) -> np.ndarray:
        return self.model.predict(np.asarray(rows, np.float64)) if rows else np.zeros(0)


@lru_cache
def load_matcher(directory: str | None = None) -> Matcher:
    root = Path(directory) if directory else ARTIFACTS
    emb = np.load(root / "interests.npz", allow_pickle=False)
    space = InterestSpace([str(t) for t in emb["tags"]], emb["matrix"].astype(np.float32))
    spec = json.loads((root / "matcher.json").read_text())
    return Matcher(space, TreeEnsemble(spec), spec.get("card", {}))

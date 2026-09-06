from __future__ import annotations

import json
import math
import random
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

CATEGORICAL_FEATURES = ("extension", "mime_category", "magic_signature_category")


@dataclass
class FeatureEncoder:
    numeric: list[str]
    categories: dict[str, list[str]]

    @classmethod
    def fit(cls, rows: list[dict[str, Any]]) -> "FeatureEncoder":
        if not rows:
            raise ValueError("cannot fit feature encoder without rows")
        numeric = sorted(
            key
            for key, value in rows[0].items()
            if key not in CATEGORICAL_FEATURES and isinstance(value, (int, float, bool))
        )
        categories = {
            key: sorted({str(row.get(key, "<missing>")) for row in rows})
            for key in CATEGORICAL_FEATURES
        }
        return cls(numeric, categories)

    @property
    def names(self) -> list[str]:
        result = list(self.numeric)
        for key in CATEGORICAL_FEATURES:
            result.extend(f"{key}={value}" for value in self.categories.get(key, []))
            result.append(f"{key}=<unknown>")
        return result

    def transform_one(self, row: dict[str, Any]) -> list[float]:
        values = [float(row.get(key, 0.0)) for key in self.numeric]
        for key in CATEGORICAL_FEATURES:
            observed = str(row.get(key, "<missing>"))
            choices = self.categories.get(key, [])
            values.extend(1.0 if observed == choice else 0.0 for choice in choices)
            values.append(0.0 if observed in choices else 1.0)
        if not all(math.isfinite(value) for value in values):
            raise ValueError("feature vector contains NaN/Inf")
        return values

    def transform(self, rows: list[dict[str, Any]]) -> np.ndarray:
        return np.asarray([self.transform_one(row) for row in rows], dtype=np.float64)

    def to_dict(self) -> dict[str, Any]:
        return {"numeric": self.numeric, "categories": self.categories, "feature_names": self.names}

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "FeatureEncoder":
        return cls(list(value["numeric"]), {key: list(items) for key, items in value["categories"].items()})


def _gini(labels: np.ndarray, classes: int) -> float:
    if len(labels) == 0:
        return 0.0
    counts = np.bincount(labels, minlength=classes) / len(labels)
    return 1.0 - float(np.sum(counts * counts))


def _leaf(labels: np.ndarray, classes: int) -> dict[str, Any]:
    counts = np.bincount(labels, minlength=classes).astype(float) + 1e-6
    probabilities = counts / counts.sum()
    return {"leaf": probabilities.tolist(), "samples": int(len(labels))}


def _build_tree(
    x: np.ndarray,
    y: np.ndarray,
    indices: np.ndarray,
    classes: int,
    depth: int,
    max_depth: int,
    max_features: int,
    rng: random.Random,
) -> dict[str, Any]:
    labels = y[indices]
    if depth >= max_depth or len(indices) < 4 or len(set(labels.tolist())) <= 1:
        return _leaf(labels, classes)
    feature_pool = list(range(x.shape[1]))
    rng.shuffle(feature_pool)
    parent = _gini(labels, classes)
    best: tuple[float, int, float, np.ndarray, np.ndarray] | None = None
    for feature in feature_pool[: max(1, min(max_features, len(feature_pool)))]:
        values = x[indices, feature]
        unique = np.unique(values)
        if len(unique) <= 1:
            continue
        positions = np.linspace(0, len(unique) - 2, min(8, len(unique) - 1), dtype=int)
        thresholds = [(float(unique[pos]) + float(unique[pos + 1])) / 2 for pos in positions]
        for threshold in thresholds:
            left_mask = values <= threshold
            if not left_mask.any() or left_mask.all():
                continue
            left, right = indices[left_mask], indices[~left_mask]
            impurity = (len(left) * _gini(y[left], classes) + len(right) * _gini(y[right], classes)) / len(indices)
            gain = parent - impurity
            candidate = (gain, feature, threshold, left, right)
            if best is None or (gain, -feature, -threshold) > (best[0], -best[1], -best[2]):
                best = candidate
    if best is None or best[0] <= 1e-12:
        return _leaf(labels, classes)
    _, feature, threshold, left, right = best
    return {
        "feature": feature,
        "threshold": threshold,
        "left": _build_tree(x, y, left, classes, depth + 1, max_depth, max_features, rng),
        "right": _build_tree(x, y, right, classes, depth + 1, max_depth, max_features, rng),
    }


def _tree_predict(tree: dict[str, Any], row: np.ndarray) -> np.ndarray:
    node = tree
    while "leaf" not in node:
        node = node["left"] if row[int(node["feature"])] <= float(node["threshold"]) else node["right"]
    return np.asarray(node["leaf"], dtype=np.float64)


class RandomForestSelector:
    model_type = "random_forest"

    def __init__(self, n_estimators: int = 31, max_depth: int = 6, seed: int = 20260901):
        self.n_estimators = n_estimators
        self.max_depth = max_depth
        self.seed = seed
        self.classes: list[str] = []
        self.trees: list[dict[str, Any]] = []

    def fit(self, x: np.ndarray, labels: list[str]) -> "RandomForestSelector":
        self.classes = sorted(set(labels))
        encoded = np.asarray([self.classes.index(label) for label in labels], dtype=np.int64)
        rng = random.Random(self.seed)
        maximum = max(1, int(math.sqrt(x.shape[1])))
        self.trees = []
        for _ in range(self.n_estimators):
            indices = np.asarray([rng.randrange(len(labels)) for _ in labels], dtype=np.int64)
            self.trees.append(_build_tree(x, encoded, indices, len(self.classes), 0, self.max_depth, maximum, rng))
        return self

    def predict_proba(self, x: np.ndarray) -> np.ndarray:
        result = np.zeros((len(x), len(self.classes)), dtype=np.float64)
        for tree in self.trees:
            for index, row in enumerate(x):
                result[index] += _tree_predict(tree, row)
        result /= max(1, len(self.trees))
        return result

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_type": self.model_type,
            "n_estimators": self.n_estimators,
            "max_depth": self.max_depth,
            "seed": self.seed,
            "classes": self.classes,
            "trees": self.trees,
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "RandomForestSelector":
        model = cls(value["n_estimators"], value["max_depth"], value["seed"])
        model.classes = list(value["classes"])
        model.trees = list(value["trees"])
        return model


class DecisionTreeSelector(RandomForestSelector):
    """Deterministic full-feature decision-tree baseline."""

    model_type = "decision_tree"

    def __init__(self, n_estimators: int = 1, max_depth: int = 8, seed: int = 20260901):
        super().__init__(n_estimators=1, max_depth=max_depth, seed=seed)

    def fit(self, x: np.ndarray, labels: list[str]) -> "DecisionTreeSelector":
        self.classes = sorted(set(labels))
        encoded = np.asarray([self.classes.index(label) for label in labels], dtype=np.int64)
        indices = np.arange(len(labels), dtype=np.int64)
        self.trees = [
            _build_tree(
                x, encoded, indices, len(self.classes), 0, self.max_depth,
                x.shape[1], random.Random(self.seed),
            )
        ]
        return self


class ExtraTreesSelector(RandomForestSelector):
    """Randomized-feature forest without bootstrap resampling."""

    model_type = "extra_trees"

    def fit(self, x: np.ndarray, labels: list[str]) -> "ExtraTreesSelector":
        self.classes = sorted(set(labels))
        encoded = np.asarray([self.classes.index(label) for label in labels], dtype=np.int64)
        rng = random.Random(self.seed)
        maximum = max(1, int(math.sqrt(x.shape[1])))
        indices = np.arange(len(labels), dtype=np.int64)
        self.trees = [
            _build_tree(x, encoded, indices, len(self.classes), 0, self.max_depth, maximum, rng)
            for _ in range(self.n_estimators)
        ]
        return self


def _regression_stump(x: np.ndarray, target: np.ndarray) -> dict[str, float]:
    best: tuple[float, int, float, float, float] | None = None
    baseline = float(np.mean((target - np.mean(target)) ** 2))
    for feature in range(x.shape[1]):
        unique = np.unique(x[:, feature])
        if len(unique) <= 1:
            continue
        positions = np.linspace(0, len(unique) - 2, min(8, len(unique) - 1), dtype=int)
        for position in positions:
            threshold = (float(unique[position]) + float(unique[position + 1])) / 2
            mask = x[:, feature] <= threshold
            if not mask.any() or mask.all():
                continue
            left = float(np.mean(target[mask]))
            right = float(np.mean(target[~mask]))
            prediction = np.where(mask, left, right)
            mse = float(np.mean((target - prediction) ** 2))
            gain = baseline - mse
            candidate = (gain, feature, threshold, left, right)
            if best is None or (gain, -feature, -threshold) > (best[0], -best[1], -best[2]):
                best = candidate
    if best is None:
        mean = float(np.mean(target))
        return {"feature": 0, "threshold": float("inf"), "left": mean, "right": mean}
    _, feature, threshold, left, right = best
    return {"feature": feature, "threshold": threshold, "left": left, "right": right}


class GradientBoostedStumpsSelector:
    model_type = "gradient_boosted_stumps"

    def __init__(self, rounds: int = 24, learning_rate: float = 0.15):
        self.rounds = rounds
        self.learning_rate = learning_rate
        self.classes: list[str] = []
        self.initial: list[float] = []
        self.stumps: list[list[dict[str, float]]] = []

    def fit(self, x: np.ndarray, labels: list[str]) -> "GradientBoostedStumpsSelector":
        self.classes = sorted(set(labels))
        encoded = np.asarray([self.classes.index(label) for label in labels], dtype=np.int64)
        counts = np.bincount(encoded, minlength=len(self.classes)).astype(float) + 1.0
        priors = counts / counts.sum()
        self.initial = np.log(priors).tolist()
        scores = np.tile(np.asarray(self.initial), (len(x), 1))
        self.stumps = []
        for _ in range(self.rounds):
            shifted = scores - scores.max(axis=1, keepdims=True)
            probabilities = np.exp(shifted)
            probabilities /= probabilities.sum(axis=1, keepdims=True)
            round_stumps = []
            for class_index in range(len(self.classes)):
                target = (encoded == class_index).astype(float) - probabilities[:, class_index]
                stump = _regression_stump(x, target)
                mask = x[:, int(stump["feature"])] <= float(stump["threshold"])
                scores[:, class_index] += self.learning_rate * np.where(mask, stump["left"], stump["right"])
                round_stumps.append(stump)
            self.stumps.append(round_stumps)
        return self

    def predict_proba(self, x: np.ndarray) -> np.ndarray:
        scores = np.tile(np.asarray(self.initial), (len(x), 1))
        for round_stumps in self.stumps:
            for class_index, stump in enumerate(round_stumps):
                mask = x[:, int(stump["feature"])] <= float(stump["threshold"])
                scores[:, class_index] += self.learning_rate * np.where(mask, stump["left"], stump["right"])
        scores -= scores.max(axis=1, keepdims=True)
        probabilities = np.exp(scores)
        probabilities /= probabilities.sum(axis=1, keepdims=True)
        return probabilities

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_type": self.model_type,
            "rounds": self.rounds,
            "learning_rate": self.learning_rate,
            "classes": self.classes,
            "initial": self.initial,
            "stumps": self.stumps,
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "GradientBoostedStumpsSelector":
        model = cls(value["rounds"], value["learning_rate"])
        model.classes = list(value["classes"])
        model.initial = list(value["initial"])
        model.stumps = list(value["stumps"])
        return model


class HistogramGradientBoostingSelector(GradientBoostedStumpsSelector):
    """Boosted stumps over the eight deterministic quantile bins per feature."""

    model_type = "histogram_gradient_boosting"


def load_model(value: dict[str, Any]):
    if value.get("model_type") == RandomForestSelector.model_type:
        return RandomForestSelector.from_dict(value)
    if value.get("model_type") == GradientBoostedStumpsSelector.model_type:
        return GradientBoostedStumpsSelector.from_dict(value)
    if value.get("model_type") == DecisionTreeSelector.model_type:
        return DecisionTreeSelector.from_dict(value)
    if value.get("model_type") == ExtraTreesSelector.model_type:
        return ExtraTreesSelector.from_dict(value)
    if value.get("model_type") == HistogramGradientBoostingSelector.model_type:
        return HistogramGradientBoostingSelector.from_dict(value)
    raise ValueError(f"unsupported selector model: {value.get('model_type')}")


class SelectorArtifact:
    def __init__(
        self,
        encoder: FeatureEncoder,
        models: dict[str, Any],
        metrics: dict | None = None,
        artifact_format: str = "xai-codec-selector-v1",
    ):
        self.encoder = encoder
        self.models = models
        self.metrics = metrics or {}
        self.artifact_format = artifact_format

    def predict_top_k(self, features: dict[str, Any], profile: str, top_k: int) -> list[tuple[str, float]]:
        if profile not in self.models:
            raise ValueError(f"profile unavailable in selector: {profile}")
        model = self.models[profile]
        probabilities = model.predict_proba(self.encoder.transform([features]))[0]
        ranked = sorted(zip(model.classes, probabilities.tolist()), key=lambda item: (-item[1], item[0]))
        return ranked[: max(1, int(top_k))]

    def to_dict(self) -> dict[str, Any]:
        return {
            "format": self.artifact_format,
            "encoder": self.encoder.to_dict(),
            "models": {profile: model.to_dict() for profile, model in self.models.items()},
            "metrics": self.metrics,
        }

    def save(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps(self.to_dict(), indent=2, sort_keys=True), encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path) -> "SelectorArtifact":
        value = json.loads(Path(path).read_text(encoding="utf-8"))
        if value.get("format") not in {"xai-codec-selector-v1", "xai-codec-selector-v2"}:
            raise ValueError("unsupported selector artifact format")
        return cls(
            FeatureEncoder.from_dict(value["encoder"]),
            {profile: load_model(model) for profile, model in value["models"].items()},
            value.get("metrics"),
            value.get("format", "xai-codec-selector-v1"),
        )

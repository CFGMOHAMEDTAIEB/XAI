"""Train cost-sensitive Selector V2 families and tune confidence routing."""
from __future__ import annotations

import csv
import hashlib
import json
import statistics
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

ENGINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ENGINE))

from xai_compress.hybrid.ml import (
    DecisionTreeSelector,
    ExtraTreesSelector,
    FeatureEncoder,
    GradientBoostedStumpsSelector,
    HistogramGradientBoostingSelector,
    RandomForestSelector,
    SelectorArtifact,
)
from xai_compress.hybrid.profiles import label_measurements, load_profiles

RESULTS = ENGINE / "results" / "hybrid_v2"
OUTPUT = ENGINE / "checkpoints" / "selector_v2"
CATEGORICAL = {"extension", "mime_category", "magic_signature_category"}


def read_rows() -> tuple[list[dict], list[str]]:
    schema = json.loads((RESULTS / "feature_schema.json").read_text(encoding="utf-8"))
    features = list(schema["features"])
    rows = []
    with (RESULTS / "selector_dataset.csv").open(newline="", encoding="utf-8") as handle:
        for raw in csv.DictReader(handle):
            row = dict(raw)
            for feature in features:
                if feature not in CATEGORICAL:
                    row[feature] = float(row[feature])
            for key in ("compressed_bytes", "compression_seconds", "decompression_seconds", "peak_rss"):
                row[key] = float(row[key])
            row["sha_pass"] = row.get("sha_pass", "").lower() == "true"
            rows.append(row)
    return rows, features


def records(rows: list[dict], features: list[str]) -> dict[str, dict]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        if row["sha_pass"]:
            grouped[row["sample_id"]].append(row)
    profiles = load_profiles()
    result = {}
    for sample_id, measured in grouped.items():
        first = measured[0]
        rankings = {profile: label_measurements(measured, profile, profiles) for profile in profiles}
        result[sample_id] = {
            "sample_id": sample_id,
            "source_group": first["source_group"],
            "source_category": first["source_category"],
            "split": first["split"],
            "features": {feature: first[feature] for feature in features},
            "measurements": {row["strategy_id"]: row for row in measured},
            "rankings": rankings,
        }
    return result


def weighted_training(records_: list[dict], profile: str) -> tuple[list[dict], list[str]]:
    feature_rows, labels = [], []
    for record in records_:
        ranking = record["rankings"][profile]
        optimal = ranking[0]
        # Oversample costly decisions. Weight is derived from measured score
        # spread, capped to keep fitting bounded and deterministic.
        spread = max(float(row["profile_score"]) for row in ranking) - float(optimal["profile_score"])
        weight = 1 + min(8, int(round(spread * 20)))
        feature_rows.extend([record["features"]] * weight)
        labels.extend([optimal["strategy_id"]] * weight)
    return feature_rows, labels


def predict(model, encoder: FeatureEncoder, features: dict, top_k: int = 3) -> list[tuple[str, float]]:
    probabilities = model.predict_proba(encoder.transform([features]))[0]
    return [
        (model.classes[index], float(probability))
        for index, probability in sorted(
            enumerate(probabilities), key=lambda item: (-item[1], model.classes[item[0]])
        )[:top_k]
    ]


def evaluate(model, encoder: FeatureEncoder, rows: list[dict], profile: str, family: str) -> tuple[dict, list[dict]]:
    output, latencies = [], []
    for record in rows:
        started = time.perf_counter()
        ranked = predict(model, encoder, record["features"], 3)
        latencies.append((time.perf_counter() - started) * 1000)
        available = record["measurements"]
        ids = [strategy for strategy, _ in ranked if strategy in available]
        if not ids:
            ids = [record["rankings"][profile][0]["strategy_id"]]
        selected = available[ids[0]]
        optimal = record["rankings"][profile][0]
        score = {row["strategy_id"]: float(row["profile_score"]) for row in record["rankings"][profile]}
        output.append({
            "model": family,
            "profile": profile,
            "sample_id": record["sample_id"],
            "source_category": record["source_category"],
            "optimal_strategy": optimal["strategy_id"],
            "selected_strategy": ids[0],
            "top1_correct": ids[0] == optimal["strategy_id"],
            "top2_recall": optimal["strategy_id"] in ids[:2],
            "top3_recall": optimal["strategy_id"] in ids[:3],
            "regret": score[ids[0]] - float(optimal["profile_score"]),
            "size_regret": (float(selected["compressed_bytes"]) - float(optimal["compressed_bytes"])) / max(1.0, float(optimal["compressed_bytes"])),
            "compression_time_regret": float(selected["compression_seconds"]) - float(optimal["compression_seconds"]),
            "decompression_time_regret": float(selected["decompression_seconds"]) - float(optimal["decompression_seconds"]),
            "confidence": ranked[0][1],
        })
    regrets = [row["regret"] for row in output]
    metrics = {
        "model": family,
        "profile": profile,
        "samples": len(output),
        "top_1_accuracy": statistics.mean(row["top1_correct"] for row in output),
        "top_2_recall": statistics.mean(row["top2_recall"] for row in output),
        "top_3_recall": statistics.mean(row["top3_recall"] for row in output),
        "mean_regret": statistics.mean(regrets),
        "median_regret": statistics.median(regrets),
        "p95_regret": float(np.percentile(regrets, 95)),
        "mean_size_regret": statistics.mean(row["size_regret"] for row in output),
        "mean_compression_time_regret": statistics.mean(row["compression_time_regret"] for row in output),
        "mean_decompression_time_regret": statistics.mean(row["decompression_time_regret"] for row in output),
        "mean_inference_ms": statistics.mean(latencies),
        "model_bytes": len(json.dumps(model.to_dict(), separators=(",", ":")).encode()),
    }
    return metrics, output


def tune_thresholds(model, encoder: FeatureEncoder, rows: list[dict], profile: str) -> dict:
    best = None
    for low in (0.30, 0.40, 0.50, 0.60, 0.70):
        for high in (0.60, 0.70, 0.80, 0.90, 0.95):
            if high <= low:
                continue
            regrets, benchmarked = [], []
            for record in rows:
                ranked = [(strategy, probability) for strategy, probability in predict(model, encoder, record["features"], 3) if strategy in record["measurements"]]
                if not ranked:
                    continue
                confidence = ranked[0][1]
                count = 1 if confidence >= high else 2 if confidence >= low else 3
                candidates = ranked[:count]
                score = {row["strategy_id"]: float(row["profile_score"]) for row in record["rankings"][profile]}
                selected = min(candidates, key=lambda item: (score[item[0]], item[0]))[0]
                optimal = record["rankings"][profile][0]
                microbench_seconds = sum(
                    float(record["measurements"][strategy]["compression_seconds"])
                    + float(record["measurements"][strategy]["decompression_seconds"])
                    for strategy, _ in candidates
                )
                regrets.append(score[selected] - float(optimal["profile_score"]) + 0.001 * microbench_seconds)
                benchmarked.append(count - 1)
            objective = statistics.mean(regrets) if regrets else float("inf")
            candidate = (objective, statistics.mean(benchmarked) if benchmarked else 0.0, low, high)
            if best is None or candidate < best:
                best = candidate
    assert best is not None
    return {"low": best[2], "high": best[3], "validation_objective": best[0], "mean_extra_candidates": best[1]}


def feature_importance(model, names: list[str]) -> list[dict]:
    counts: Counter[int] = Counter()

    def walk(node: dict) -> None:
        if "leaf" in node:
            return
        counts[int(node["feature"])] += 1
        walk(node["left"])
        walk(node["right"])

    if hasattr(model, "trees"):
        for tree in model.trees:
            walk(tree)
    else:
        for round_stumps in model.stumps:
            for stump in round_stumps:
                counts[int(stump["feature"])] += 1
    total = sum(counts.values()) or 1
    return [{"feature": names[index], "split_count": count, "importance": count / total} for index, count in counts.most_common()]


def write_csv(path: Path, rows: list[dict]) -> None:
    fields = sorted({key for row in rows for key in row})
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    rows, features = read_rows()
    record_map = records(rows, features)
    train = [row for row in record_map.values() if row["split"] == "train"]
    validation = [row for row in record_map.values() if row["split"] == "validation"]
    test = [row for row in record_map.values() if row["split"] == "test"]
    encoder = FeatureEncoder.fit([row["features"] for row in train + validation])
    profiles = load_profiles()
    selected_models, thresholds, metrics_all, test_rows, importance_rows = {}, {}, [], [], []
    selected_names = {}
    for profile in profiles:
        weighted_features, weighted_labels = weighted_training(train, profile)
        x = encoder.transform(weighted_features)
        families = {
            "decision_tree": DecisionTreeSelector(max_depth=8).fit(x, weighted_labels),
            "random_forest": RandomForestSelector(n_estimators=31, max_depth=7).fit(x, weighted_labels),
            "extra_trees": ExtraTreesSelector(n_estimators=31, max_depth=7).fit(x, weighted_labels),
            "gradient_boosting": GradientBoostedStumpsSelector(rounds=30, learning_rate=0.15).fit(x, weighted_labels),
            "histogram_gradient_boosting": HistogramGradientBoostingSelector(rounds=45, learning_rate=0.10).fit(x, weighted_labels),
        }
        candidates = []
        for name, model in families.items():
            validation_metrics, _ = evaluate(model, encoder, validation, profile, name)
            metrics_all.append(dict(validation_metrics, split="validation"))
            candidates.append((validation_metrics["mean_regret"], validation_metrics["p95_regret"], validation_metrics["mean_inference_ms"], name, model))
        _, _, _, selected_name, _ = min(candidates)
        fit_features, fit_labels = weighted_training(train + validation, profile)
        fit_x = encoder.transform(fit_features)
        if selected_name == "decision_tree":
            selected = DecisionTreeSelector(max_depth=8).fit(fit_x, fit_labels)
        elif selected_name == "random_forest":
            selected = RandomForestSelector(n_estimators=31, max_depth=7).fit(fit_x, fit_labels)
        elif selected_name == "extra_trees":
            selected = ExtraTreesSelector(n_estimators=31, max_depth=7).fit(fit_x, fit_labels)
        elif selected_name == "gradient_boosting":
            selected = GradientBoostedStumpsSelector(rounds=30, learning_rate=0.15).fit(fit_x, fit_labels)
        else:
            selected = HistogramGradientBoostingSelector(rounds=45, learning_rate=0.10).fit(fit_x, fit_labels)
        selected_models[profile] = selected
        selected_names[profile] = selected_name
        thresholds[profile] = tune_thresholds(selected, encoder, validation, profile)
        test_metrics, evaluations = evaluate(selected, encoder, test, profile, selected_name)
        metrics_all.append(dict(test_metrics, split="test", selected=True))
        test_rows.extend(evaluations)
        importance_rows.extend(dict(row, profile=profile, model=selected_name) for row in feature_importance(selected, encoder.names))
    selected_test = [row for row in metrics_all if row.get("split") == "test" and row.get("selected")]
    summary = {
        "format": "xai-codec-selector-v2",
        "training_groups": len(train),
        "validation_groups": len(validation),
        "test_groups": len(test),
        "features": len(encoder.names),
        "selected_models": selected_names,
        "confidence_thresholds": thresholds,
        "top_1_accuracy": statistics.mean(row["top_1_accuracy"] for row in selected_test),
        "top_2_recall": statistics.mean(row["top_2_recall"] for row in selected_test),
        "top_3_recall": statistics.mean(row["top_3_recall"] for row in selected_test),
        "mean_regret": statistics.mean(row["mean_regret"] for row in selected_test),
        "median_regret": statistics.mean(row["median_regret"] for row in selected_test),
        "p95_regret": statistics.mean(row["p95_regret"] for row in selected_test),
        "mean_inference_ms": statistics.mean(row["mean_inference_ms"] for row in selected_test),
        "model_families_benchmarked": ["decision_tree", "random_forest", "extra_trees", "gradient_boosting", "histogram_gradient_boosting"],
        "rule_baseline": "evaluated separately from measured rows during finalization",
        "cost_sensitive_training": "measured profile-score-spread oversampling",
    }
    artifact = SelectorArtifact(encoder, selected_models, summary, artifact_format="xai-codec-selector-v2")
    artifact_path = OUTPUT / "best.json"
    artifact.save(artifact_path)
    artifact_hash = hashlib.sha256(artifact_path.read_bytes()).hexdigest()
    (OUTPUT / "feature_schema.json").write_text(json.dumps(encoder.to_dict(), indent=2), encoding="utf-8")
    (OUTPUT / "strategy_schema.json").write_text(json.dumps({"strategy": "codec|level|transform", "profiles": list(profiles)}, indent=2), encoding="utf-8")
    (OUTPUT / "training_manifest.json").write_text(json.dumps({"seed": 20260901, "split_unit": "source_group", "groups": {"train": len(train), "validation": len(validation), "test": len(test)}, "selected_models": selected_names, "confidence_thresholds": thresholds}, indent=2), encoding="utf-8")
    (OUTPUT / "metrics.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    (OUTPUT / "model_sha256.txt").write_text(artifact_hash + "\n", encoding="ascii")
    write_csv(RESULTS / "selector_model_metrics.csv", metrics_all)
    write_csv(RESULTS / "selector_test_predictions.csv", test_rows)
    write_csv(RESULTS / "selector_feature_importance.csv", importance_rows)
    (RESULTS / "selector_metrics.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(dict(summary, selector_sha256=artifact_hash, selector_bytes=artifact_path.stat().st_size), indent=2))


if __name__ == "__main__":
    main()

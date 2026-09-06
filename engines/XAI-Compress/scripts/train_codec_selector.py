"""Train dependency-light codec selectors and evaluate strategy regret."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import statistics
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from xai_compress.hybrid.ml import (
    FeatureEncoder,
    GradientBoostedStumpsSelector,
    RandomForestSelector,
    SelectorArtifact,
)
from xai_compress.hybrid.profiles import label_measurements, load_profiles
from xai_compress.hybrid.selector import rule_candidates


NUMERIC_MEASUREMENTS = {
    "level", "compressed_bytes", "actual_bpb", "ratio", "compression_seconds",
    "decompression_seconds", "compression_MB_s", "decompression_MB_s", "peak_rss",
}


def read_dataset(path: Path, feature_names: list[str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(newline="", encoding="utf-8") as handle:
        for raw in csv.DictReader(handle):
            row: dict[str, Any] = dict(raw)
            for key in feature_names:
                if key not in {"extension", "mime_category", "magic_signature_category"}:
                    row[key] = float(raw[key])
            for key in NUMERIC_MEASUREMENTS:
                if key in raw and raw[key] not in ("", "None"):
                    row[key] = float(raw[key])
            row["sha_pass"] = raw.get("sha_pass", "").lower() == "true"
            rows.append(row)
    return rows


def grouped_rows(rows: list[dict]) -> dict[str, list[dict]]:
    result: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        if row.get("sha_pass"):
            result[row["sample_id"]].append(row)
    return result


def sample_records(rows: list[dict], feature_names: list[str], profiles: dict) -> dict[str, dict]:
    result: dict[str, dict] = {}
    for sample_id, measurements in grouped_rows(rows).items():
        first = measurements[0]
        feature_row = {key: first[key] for key in feature_names}
        profile_rankings = {
            profile: label_measurements(measurements, profile, profiles)
            for profile in profiles
        }
        result[sample_id] = {
            "sample_id": sample_id,
            "source_group": first["source_group"],
            "source_category": first["source_category"],
            "split": first["split"],
            "features": feature_row,
            "measurements": {row["strategy_id"]: row for row in measurements},
            "rankings": profile_rankings,
        }
    return result


def evaluate_predictions(
    records: list[dict],
    profile: str,
    predictor,
    model_name: str,
) -> tuple[dict, list[dict], list[dict]]:
    evaluations: list[dict] = []
    confusion: list[dict] = []
    inference_times = []
    for record in records:
        started = time.perf_counter()
        predicted = predictor(record["features"], 3)
        inference_times.append((time.perf_counter() - started) * 1000)
        available = record["measurements"]
        predicted_ids = [item[0] if isinstance(item, tuple) else item for item in predicted]
        predicted_ids = [value for value in predicted_ids if value in available]
        if not predicted_ids:
            fallback = [item.strategy_id for item in rule_candidates(record["features"], profile, 3)]
            predicted_ids = [value for value in fallback if value in available]
        if not predicted_ids:
            predicted_ids = sorted(available)[:1]
        selected_id = predicted_ids[0]
        ranking = record["rankings"][profile]
        score_by_id = {row["strategy_id"]: float(row["profile_score"]) for row in ranking}
        optimal = ranking[0]
        selected = available[selected_id]
        regret = score_by_id[selected_id] - float(optimal["profile_score"])
        size_regret = 100 * (float(selected["compressed_bytes"]) - float(optimal["compressed_bytes"])) / max(1, float(optimal["compressed_bytes"]))
        evaluations.append(
            {
                "model": model_name,
                "profile": profile,
                "sample_id": record["sample_id"],
                "source_category": record["source_category"],
                "split": record["split"],
                "optimal_strategy": optimal["strategy_id"],
                "selected_strategy": selected_id,
                "top1_correct": selected_id == optimal["strategy_id"],
                "top3_recall": optimal["strategy_id"] in predicted_ids[:3],
                "regret": regret,
                "size_regret_percent": size_regret,
                "selected_compressed_bytes": selected["compressed_bytes"],
                "optimal_compressed_bytes": optimal["compressed_bytes"],
            }
        )
        confusion.append(
            {
                "model": model_name,
                "profile": profile,
                "actual": optimal["strategy_id"],
                "predicted": selected_id,
                "count": 1,
            }
        )
    regrets = [row["regret"] for row in evaluations]
    sizes = [row["size_regret_percent"] for row in evaluations]
    metrics = {
        "model": model_name,
        "profile": profile,
        "samples": len(evaluations),
        "top_1_accuracy": statistics.mean(row["top1_correct"] for row in evaluations) if evaluations else 0.0,
        "top_3_recall": statistics.mean(row["top3_recall"] for row in evaluations) if evaluations else 0.0,
        "mean_regret": statistics.mean(regrets) if regrets else None,
        "median_regret": statistics.median(regrets) if regrets else None,
        "p95_regret": float(np.percentile(regrets, 95)) if regrets else None,
        "mean_size_regret_percent": statistics.mean(sizes) if sizes else None,
        "p95_size_regret_percent": float(np.percentile(sizes, 95)) if sizes else None,
        "mean_inference_ms": statistics.mean(inference_times) if inference_times else None,
    }
    return metrics, evaluations, confusion


def feature_importance(model, names: list[str]) -> list[dict]:
    counts: Counter[int] = Counter()

    def walk(node: dict) -> None:
        if "leaf" in node:
            return
        counts[int(node["feature"])] += 1
        walk(node["left"])
        walk(node["right"])

    if isinstance(model, RandomForestSelector):
        for tree in model.trees:
            walk(tree)
    else:
        for round_stumps in model.stumps:
            for stump in round_stumps:
                counts[int(stump["feature"])] += 1
    total = sum(counts.values()) or 1
    return [
        {"feature": names[index], "split_count": count, "importance": count / total}
        for index, count in counts.most_common()
    ]


def write_csv(path: Path, rows: list[dict]) -> None:
    fields = sorted({key for row in rows for key in row})
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, default=ROOT / "results" / "hybrid_ai" / "selector_dataset.csv")
    parser.add_argument("--output", type=Path, default=ROOT / "checkpoints" / "selector")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    results = ROOT / "results" / "hybrid_ai"
    schema = json.loads((results / "selector_feature_schema.json").read_text(encoding="utf-8"))
    feature_names = list(schema["features"])
    rows = read_dataset(args.dataset, feature_names)
    profiles = load_profiles()
    records = sample_records(rows, feature_names, profiles)
    train = [value for value in records.values() if value["split"] == "train"]
    validation = [value for value in records.values() if value["split"] == "validation"]
    test = [value for value in records.values() if value["split"] == "test"]
    if not train or not test:
        raise RuntimeError("selector split requires non-empty train and test groups")
    encoder = FeatureEncoder.fit([record["features"] for record in train + validation])
    selected_models: dict[str, Any] = {}
    all_metrics: list[dict] = []
    all_regret: list[dict] = []
    all_confusion: list[dict] = []
    importances: list[dict] = []
    selection_manifest: dict[str, str] = {}

    for profile in profiles:
        # Rule-based baseline, measured on the untouched test set.
        rule_predictor = lambda features, top_k, p=profile: [item.strategy_id for item in rule_candidates(features, p, top_k)]
        rule_metrics, rule_rows, rule_confusion = evaluate_predictions(test, profile, rule_predictor, "rule_based")
        all_metrics.append(rule_metrics)
        all_regret.extend(rule_rows)
        all_confusion.extend(rule_confusion)

        x_train = encoder.transform([record["features"] for record in train])
        y_train = [record["rankings"][profile][0]["strategy_id"] for record in train]
        families = {
            "random_forest": RandomForestSelector(n_estimators=41, max_depth=6).fit(x_train, y_train),
            "gradient_boosted_stumps": GradientBoostedStumpsSelector(rounds=30, learning_rate=0.15).fit(x_train, y_train),
        }
        selection_rows = validation or train
        family_validation: list[tuple[float, str, Any]] = []
        for family_name, model in families.items():
            predictor = lambda features, top_k, m=model: [
                (m.classes[index], float(probability))
                for index, probability in sorted(
                    enumerate(m.predict_proba(encoder.transform([features]))[0]),
                    key=lambda item: (-item[1], m.classes[item[0]]),
                )[:top_k]
            ]
            metrics, _, _ = evaluate_predictions(selection_rows, profile, predictor, family_name)
            family_validation.append((float(metrics["mean_regret"] or 0.0), family_name, model))
        _, selected_name, _ = min(family_validation, key=lambda item: (item[0], item[1]))
        # Refit the chosen family on train+validation. The test groups remain untouched.
        fit_records = train + validation
        x_fit = encoder.transform([record["features"] for record in fit_records])
        y_fit = [record["rankings"][profile][0]["strategy_id"] for record in fit_records]
        if selected_name == "random_forest":
            selected = RandomForestSelector(n_estimators=41, max_depth=6).fit(x_fit, y_fit)
        else:
            selected = GradientBoostedStumpsSelector(rounds=30, learning_rate=0.15).fit(x_fit, y_fit)
        selected_models[profile] = selected
        selection_manifest[profile] = selected_name
        predictor = lambda features, top_k, m=selected: [
            (m.classes[index], float(probability))
            for index, probability in sorted(
                enumerate(m.predict_proba(encoder.transform([features]))[0]),
                key=lambda item: (-item[1], m.classes[item[0]]),
            )[:top_k]
        ]
        metrics, regret_rows, confusion = evaluate_predictions(test, profile, predictor, selected_name)
        metrics["selected_for_profile"] = True
        all_metrics.append(metrics)
        all_regret.extend(regret_rows)
        all_confusion.extend(confusion)
        for row in feature_importance(selected, encoder.names):
            importances.append(dict(row, profile=profile, model=selected_name))

    selected_test = [row for row in all_metrics if row.get("selected_for_profile")]
    summary = {
        "training_samples": len(train),
        "validation_samples": len(validation),
        "test_samples": len(test),
        "split_unit": "source_group",
        "profiles": selection_manifest,
        "top_1_accuracy": statistics.mean(row["top_1_accuracy"] for row in selected_test),
        "top_3_recall": statistics.mean(row["top_3_recall"] for row in selected_test),
        "mean_regret": statistics.mean(row["mean_regret"] for row in selected_test),
        "median_regret": statistics.mean(row["median_regret"] for row in selected_test),
        "p95_regret": statistics.mean(row["p95_regret"] for row in selected_test),
        "mean_inference_ms": statistics.mean(row["mean_inference_ms"] for row in selected_test),
        "profile_metrics": all_metrics,
    }
    artifact = SelectorArtifact(encoder, selected_models, summary)
    artifact_path = args.output / "best.json"
    artifact.save(artifact_path)
    (args.output / "feature_schema.json").write_text(json.dumps(encoder.to_dict(), indent=2), encoding="utf-8")
    (args.output / "label_schema.json").write_text(
        json.dumps({"strategy_id": "codec|level|transform", "profiles": list(profiles), "target": "minimum measured normalized score"}, indent=2),
        encoding="utf-8",
    )
    (args.output / "metrics.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    manifest = {
        "format": "xai-codec-selector-v1",
        "artifact": "best.json",
        "artifact_sha256": hashlib.sha256(artifact_path.read_bytes()).hexdigest(),
        "model_families_benchmarked": ["rule_based", "random_forest", "gradient_boosted_stumps"],
        "selected_models": selection_manifest,
        "requires_sklearn": False,
        "deterministic_seed": 20260901,
    }
    (args.output / "model_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    write_csv(results / "selector_model_metrics.csv", all_metrics)
    write_csv(results / "regret_analysis.csv", all_regret)
    write_csv(results / "selector_confusion_matrix.csv", all_confusion)
    write_csv(results / "selector_feature_importance.csv", importances)
    (results / "selector_training_metrics.json").write_text(
        json.dumps({"models": [row for row in all_metrics if row["model"] != "rule_based"], "selected": selection_manifest}, indent=2),
        encoding="utf-8",
    )
    (results / "selector_test_metrics.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()

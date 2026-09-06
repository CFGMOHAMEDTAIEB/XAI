import copy
import json
from pathlib import Path

import pytest
import torch

from xai_compress.model_search import (
    ModelSearchOrchestrator,
    SearchConfig,
    candidate_fingerprint,
    classify_failure,
    deterministic_candidate_id,
    promotion_outcome,
)


def search_config(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    configs = root / "configs"
    configs.mkdir(parents=True)
    baseline = root / "checkpoints" / "kaggle" / "best.pt"
    baseline.parent.mkdir(parents=True)
    baseline.write_bytes(b"protected-gru")
    payload = {
        "schema_version": 1,
        "search_name": "test-search",
        "seed": 42,
        "protected_baseline": "checkpoints/kaggle/best.pt",
        "results_root": "results/model_search",
        "checkpoint_root": "checkpoints/model_search",
        "kaggle": {
            "current_diagnostic_kernel": "owner/kernel",
            "current_diagnostic_version": 1,
            "max_infrastructure_retries": 2,
        },
        "budget": {
            "max_candidates": 5,
            "max_gpu_hours": 10,
            "max_kaggle_submissions": 3,
            "max_failures": 3,
            "no_improvement_patience": 2,
        },
        "selection": {
            "minimum_actual_bpb_improvement_fraction": 0.005,
            "activation_hard_limit": 32752,
            "minimum_stability_epochs": 5,
        },
        "base_config": {
            "architecture": "causal-byte-transformer-v2",
            "lr": 0.0005,
            "context_length": 256,
        },
        "candidates": [
            {
                "key": "lr_0_0003", "parent": "base", "change": {"lr": 0.0003},
                "change_label": "LR 0.0003", "activation_rule": "always",
            },
            {
                "key": "lr_0_0002", "parent": "base", "change": {"lr": 0.0002},
                "change_label": "LR 0.0002", "activation_rule": "after failure",
            },
        ],
    }
    path = configs / "search.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def passing_summary() -> dict:
    return {
        "status": "PASS",
        "epochs": 5,
        "training_samples_per_epoch": 450000,
        "validation_samples_per_epoch": 50000,
        "finite_metrics": True,
        "finite_parameters": True,
        "finite_optimizer_state": True,
        "checkpoint_load": True,
        "deterministic_inference": True,
        "lossless_sha256": True,
        "max_activation": 1200.0,
        "layer_3_growth": "STABLE",
        "history": [
            {"epoch": epoch, "val_cross_entropy": 5.5 - epoch / 100,
             "val_bpb_estimate": 7.9 - epoch / 100, "vram_max_bytes": 1000,
             "samples_per_second": 20}
            for epoch in range(1, 6)
        ],
    }


def test_candidate_identity_is_deterministic_and_config_sensitive():
    config = {"architecture": "v2", "lr": 0.0003}
    assert candidate_fingerprint(config) == candidate_fingerprint(copy.deepcopy(config))
    assert deterministic_candidate_id("Candidate A", config).startswith("candidate-a-")
    assert candidate_fingerprint(config) != candidate_fingerprint({**config, "lr": 0.0002})


def test_existing_run_is_registered_once_and_duplicate_training_is_blocked(tmp_path):
    orchestrator = ModelSearchOrchestrator(SearchConfig.load(search_config(tmp_path)))
    state = orchestrator.initialize()
    candidate = orchestrator.register_candidate(state, "lr_0_0003")
    assert orchestrator.register_candidate(state, "lr_0_0003")["candidate_id"] == candidate["candidate_id"]
    assert state["budget"]["candidates_consumed"] == 1
    orchestrator.mark_running_external(state, candidate, "owner/kernel", 1)
    assert orchestrator.next_candidate_key(state) is None
    with pytest.raises(RuntimeError, match="another candidate|terminal"):
        second = orchestrator.register_candidate(state, "lr_0_0002")
        orchestrator.mark_running_external(state, second, "owner/duplicate", 1)


def test_numerical_failure_unlocks_only_approved_lower_lr(tmp_path):
    orchestrator = ModelSearchOrchestrator(SearchConfig.load(search_config(tmp_path)))
    state = orchestrator.initialize()
    candidate = orchestrator.register_candidate(state, "lr_0_0003")
    orchestrator.mark_running_external(state, candidate, "owner/kernel", 1)
    failure = orchestrator.record_failure(
        state, candidate, "MULTI_EPOCH_STABILITY", "non-finite gradient:output.weight",
        {"epoch": 4, "step": 24024, "first_non_finite_stage": "gradient:output.weight"},
    )
    assert failure["classification"] == "GRADIENT_INSTABILITY"
    assert orchestrator.next_candidate_key(state) == "lr_0_0002"
    assert (orchestrator.paths.results / "failures" / f"{candidate['candidate_id']}.json").is_file()


def test_stability_gate_requires_optimizer_evidence(tmp_path):
    orchestrator = ModelSearchOrchestrator(SearchConfig.load(search_config(tmp_path)))
    summary = passing_summary()
    del summary["finite_optimizer_state"]
    passed, reasons = orchestrator.validate_stability_summary(summary)
    assert not passed
    assert "finite optimizer-state gate failed" in reasons


def test_ingestion_reuses_existing_artifact_and_runs_local_gate(tmp_path, monkeypatch):
    orchestrator = ModelSearchOrchestrator(SearchConfig.load(search_config(tmp_path)))
    state = orchestrator.initialize()
    candidate = orchestrator.register_candidate(state, "lr_0_0003")
    orchestrator.mark_running_external(state, candidate, "owner/kernel", 1)
    source = tmp_path / "download" / "lr_0_0003"
    source.mkdir(parents=True)
    (source / "best.pt").write_bytes(b"measured-checkpoint")
    evidence = {
        "checkpoint_load": True, "finite_parameters": True, "finite_optimizer_state": True,
        "deterministic_inference": True, "lossless_sha256": True, "roundtrips": [],
        "checkpoint_size": 19, "checkpoint_sha256": "test", "checkpoint_epoch": 5,
        "parameter_tensor_count": 1, "optimizer_tensor_count": 1,
        "parameter_abs_max": 1.0, "optimizer_state_abs_max": 1.0,
    }
    monkeypatch.setattr(orchestrator, "_verify_checkpoint_locally", lambda _: evidence)
    assert orchestrator.ingest_stability_result(state, candidate, source, passing_summary())
    assert candidate["status"] == "STABILITY_VALIDATED"
    assert state["best_stable_candidate"] == candidate["candidate_id"]
    assert state["budget"]["kaggle_submissions_consumed"] == 1
    assert (Path(candidate["candidate_dir"]) / "local_checkpoint_validation.json").is_file()


def test_protected_baseline_change_is_detected(tmp_path):
    orchestrator = ModelSearchOrchestrator(SearchConfig.load(search_config(tmp_path)))
    orchestrator.initialize()
    orchestrator.paths.baseline.write_bytes(b"changed")
    with pytest.raises(RuntimeError, match="PROTECTED_GRU_CHANGED"):
        orchestrator.load_state()


def test_failure_classification_and_promotion_policy():
    assert classify_failure("CUDA out of memory") == "CUDA_OOM"
    assert classify_failure("non-finite optimizer state") == "OPTIMIZER_INSTABILITY"
    assert promotion_outcome(7.0, 8.0, 0.005, True, True) == "PROMOTE"
    assert promotion_outcome(None, 8.0, 0.005, True, True) == "INCONCLUSIVE"
    assert promotion_outcome(7.0, 8.0, 0.005, False, True) == "REJECT"


def test_nested_tensor_finite_scan():
    good = {"state": [{"exp_avg": torch.tensor([1.0, -2.0])}]}
    assert ModelSearchOrchestrator._finite_tensor_tree(good) == (True, 2.0, 1)
    bad = {"state": {0: {"exp_avg": torch.tensor([float("nan")])}}}
    finite, _, count = ModelSearchOrchestrator._finite_tensor_tree(bad)
    assert not finite and count == 1


def test_config_rejects_multiple_major_changes(tmp_path):
    path = search_config(tmp_path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["candidates"][0]["change"] = {"lr": 0.0003, "context_length": 512}
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="exactly one major field"):
        SearchConfig.load(path)


def test_state_resume_preserves_interrupted_external_run(tmp_path):
    config = SearchConfig.load(search_config(tmp_path))
    first = ModelSearchOrchestrator(config)
    state = first.initialize()
    candidate = first.register_candidate(state, "lr_0_0003")
    first.mark_running_external(state, candidate, "owner/kernel", 7)
    resumed = ModelSearchOrchestrator(config).initialize()
    assert resumed["running_candidate"] == candidate["candidate_id"]
    assert resumed["candidates"][candidate["candidate_id"]]["kaggle_version"] == 7
    assert resumed["budget"]["kaggle_submissions_consumed"] == 1


def test_checkpoint_namespaces_are_isolated(tmp_path):
    orchestrator = ModelSearchOrchestrator(SearchConfig.load(search_config(tmp_path)))
    state = orchestrator.initialize()
    first = orchestrator.register_candidate(state, "lr_0_0003")
    second = orchestrator.register_candidate(state, "lr_0_0002")
    assert first["checkpoint_dir"] != second["checkpoint_dir"]
    assert Path(first["checkpoint_dir"]).parent == orchestrator.paths.checkpoints
    assert Path(second["checkpoint_dir"]).parent == orchestrator.paths.checkpoints
    assert orchestrator.paths.baseline not in {
        Path(first["checkpoint_dir"]), Path(second["checkpoint_dir"]),
    }


def test_leaderboard_uses_na_for_unmeasured_values(tmp_path):
    orchestrator = ModelSearchOrchestrator(SearchConfig.load(search_config(tmp_path)))
    state = orchestrator.initialize()
    orchestrator.register_candidate(state, "lr_0_0003")
    rows = orchestrator.update_leaderboard(state)
    assert rows[0]["actual_bpb"] == "N/A"
    assert rows[0]["compression_MB_s"] == "N/A"
    persisted = json.loads(orchestrator.leaderboard_json.read_text(encoding="utf-8"))
    assert persisted == rows


def _write_benchmark(path: Path, candidate_bpb: float, baseline_bpb: float,
                     decision: str = "INCONCLUSIVE", sha256: bool = True):
    path.mkdir(parents=True)
    summaries = [
        {
            "method": "transformer_v2", "status": "PASS", "actual_bpb": candidate_bpb,
            "ratio": 8 / candidate_bpb, "compression_MB_s_median": 1.0,
            "decompression_MB_s_median": 2.0, "peak_RSS_MB_max": 100.0,
            "sha256_pass": sha256, "model_entropy_bpb": candidate_bpb - .2,
            "quantization_delta_bpb": .05, "entropy_coder_overhead_bpb": .1,
            "container_overhead_bpb": .05,
        },
        {
            "method": "old_gru", "status": "PASS", "actual_bpb": baseline_bpb,
            "sha256_pass": True,
        },
    ]
    (path / "promotion_decision.json").write_text(
        json.dumps({"decision": decision, "summaries": summaries}), encoding="utf-8"
    )


def test_actual_bpb_promotion_selects_candidate_only_after_measured_gate(tmp_path):
    orchestrator = ModelSearchOrchestrator(SearchConfig.load(search_config(tmp_path)))
    state = orchestrator.initialize()
    candidate = orchestrator.register_candidate(state, "lr_0_0003")
    candidate.update({
        "status": "STABILITY_VALIDATED",
        "checkpoint_manifest": {"sha256": "abc", "size": 10},
        "metrics": {"checkpoint_size": 10, "vram_bytes": 20},
    })
    benchmark = tmp_path / "benchmark"
    _write_benchmark(benchmark, 7.0, 8.0, "PROMOTE V2")
    assert orchestrator.ingest_benchmark(state, candidate, benchmark) == "PROMOTE"
    current = json.loads(orchestrator.current_best_path.read_text(encoding="utf-8"))
    assert current["candidate_id"] == candidate["candidate_id"]
    assert current["actual_bpb"] == 7.0
    assert state["status"] == "SUCCESS"
    pareto = json.loads((orchestrator.paths.results / "plots" / "pareto_summary.json").read_text())
    assert pareto["current_best_bpb"] == candidate["candidate_id"]
    assert (orchestrator.paths.results / "plots" / "pareto_bpb_vs_decompression.svg").is_file()


def test_sha256_is_mandatory_and_never_promotes(tmp_path):
    orchestrator = ModelSearchOrchestrator(SearchConfig.load(search_config(tmp_path)))
    state = orchestrator.initialize()
    candidate = orchestrator.register_candidate(state, "lr_0_0003")
    candidate.update({"status": "STABILITY_VALIDATED", "metrics": {}})
    benchmark = tmp_path / "benchmark"
    _write_benchmark(benchmark, 7.0, 8.0, "PROMOTE V2", sha256=False)
    assert orchestrator.ingest_benchmark(state, candidate, benchmark) == "REJECT"
    assert candidate["status"] == "LOSSLESS_CORRECTNESS_FAILED"
    current = json.loads(orchestrator.current_best_path.read_text(encoding="utf-8"))
    assert current["candidate_id"] == "protected_gru"


def test_inconclusive_candidate_does_not_replace_protected_current_best(tmp_path):
    orchestrator = ModelSearchOrchestrator(SearchConfig.load(search_config(tmp_path)))
    state = orchestrator.initialize()
    candidate = orchestrator.register_candidate(state, "lr_0_0003")
    candidate.update({
        "status": "STABILITY_VALIDATED",
        "checkpoint_manifest": {"sha256": "abc", "size": 10},
        "metrics": {"checkpoint_size": 10, "vram_bytes": 20},
    })
    benchmark = tmp_path / "benchmark"
    _write_benchmark(benchmark, 7.99, 8.0, "INCONCLUSIVE")
    assert orchestrator.ingest_benchmark(state, candidate, benchmark) == "INCONCLUSIVE"
    current = json.loads(orchestrator.current_best_path.read_text(encoding="utf-8"))
    assert current["candidate_id"] == "protected_gru"


def test_budget_and_no_improvement_stop_conditions(tmp_path):
    orchestrator = ModelSearchOrchestrator(SearchConfig.load(search_config(tmp_path)))
    state = orchestrator.initialize()
    state["budget"]["gpu_hours_consumed"] = state["budget"]["max_gpu_hours"]
    orchestrator._check_stop_conditions(state)
    assert state["status"] == "SEARCH_BUDGET_EXHAUSTED"

    state["status"] = "ACTIVE"
    state["stop_reason"] = None
    state["budget"]["gpu_hours_consumed"] = 0
    state["budget"]["eligible_without_improvement"] = state["budget"]["no_improvement_patience"]
    orchestrator._check_stop_conditions(state)
    assert state["status"] == "NO_SIGNIFICANT_IMPROVEMENT"


def test_infrastructure_retry_is_bounded(tmp_path):
    orchestrator = ModelSearchOrchestrator(SearchConfig.load(search_config(tmp_path)))
    state = orchestrator.initialize()
    candidate = orchestrator.register_candidate(state, "lr_0_0003")
    assert orchestrator.infrastructure_failure(state, candidate, ConnectionError("network"))
    assert orchestrator.infrastructure_failure(state, candidate, ConnectionError("network"))
    assert not orchestrator.infrastructure_failure(state, candidate, ConnectionError("network"))
    assert candidate["status"] == "INFRASTRUCTURE_FAILED"
    assert candidate["failure_classification"] == "INFRASTRUCTURE_ERROR"


def test_candidate_b_kernel_cannot_retrain_candidate_a():
    source = (Path(__file__).parents[1] / "scripts" / "kaggle" / "run_v2_lr_0002_diagnostic.py").read_text(
        encoding="utf-8"
    )
    assert "LEARNING_RATE = 0.0002" in source
    assert "candidate_a_retrained\": False" in source
    assert "for learning_rate in" not in source

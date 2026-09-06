import copy
import hashlib
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
    is_sha256,
    promotion_outcome,
    repair_protected_baseline_sha256,
)
from xai_compress.train import _collection_abs_max, aggregate_diagnostic_scalars
from xai_compress.checkpoint import save_checkpoint
from xai_compress.model import ModelConfig
from xai_compress.models.registry import build_model


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
        "protected_baseline_expected_sha256": "d2f07d3f09bf6662f8bdba6214efa8e83de36e78087eecbed6c26d8b3f61eba9",
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
    orchestrator.mark_running_external(state, candidate, "owner/kernel", 1)
    assert orchestrator.next_candidate_key(state) is None
    assert state["budget"]["kaggle_submissions_consumed"] == 1
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


def test_candidate_a_retry_kernel_is_single_candidate_and_single_retry():
    source = (Path(__file__).parents[1] / ".kaggle_kernel_model_search_lr_0003_retry" / "run.py").read_text(
        encoding="utf-8"
    )
    assert "LEARNING_RATE = 0.0003" in source
    assert '"candidate_a_retrained": True' in source
    assert '"candidate_a_retry_number": 1' in source
    assert "0.0002" not in source
    assert "for learning_rate in" not in source


def test_telemetry_aggregation_cpu_scalars_mixed_sources_and_missing_values():
    result = aggregate_diagnostic_scalars([torch.tensor(3.5), 2, 4.25, None])
    assert result == 4.25
    assert isinstance(result, float)
    assert aggregate_diagnostic_scalars([None, None]) == 0.0
    assert aggregate_diagnostic_scalars([]) == 0.0
    with pytest.raises(ValueError, match="scalar tensors only"):
        aggregate_diagnostic_scalars([torch.tensor([1.0, 2.0])])


def test_optimizer_telemetry_reduces_cpu_tensors_without_device_coupling():
    result = _collection_abs_max(
        [torch.tensor(2.0), torch.tensor([-3.5, 1.0]), None], torch.device("cpu")
    )
    assert result.device.type == "cpu"
    assert result.item() == 3.5


@pytest.mark.skipif(not torch.cuda.is_available(), reason="CUDA is unavailable")
def test_optimizer_telemetry_accepts_mixed_cpu_cuda_state():
    result = _collection_abs_max(
        [torch.tensor(2.0, device="cpu"), torch.tensor([-7.0, 1.0], device="cuda")],
        torch.device("cuda"),
    )
    assert result.device.type == "cuda"
    assert result.item() == 7.0


@pytest.mark.skipif(not torch.cuda.is_available(), reason="CUDA is unavailable")
def test_telemetry_aggregation_accepts_mixed_cpu_cuda_observations():
    cpu = torch.tensor(2.0, device="cpu")
    cuda = torch.tensor(7.0, device="cuda")
    with pytest.raises(RuntimeError, match="same device"):
        torch.stack([cpu, cuda])
    result = aggregate_diagnostic_scalars([cpu, cuda, 3.0])
    assert result == 7.0
    assert isinstance(result, float)


def test_candidate_a_telemetry_failure_is_superseded_not_erased(tmp_path):
    orchestrator = ModelSearchOrchestrator(SearchConfig.load(search_config(tmp_path)))
    state = orchestrator.initialize()
    candidate = orchestrator.register_candidate(state, "lr_0_0003")
    original = orchestrator.record_failure(
        state, candidate, "MULTI_EPOCH_STABILITY",
        "Expected all tensors to be on the same device, cuda:0 and cpu",
        {"epoch": 1, "step": 28125, "last_known_stage": "VALIDATING"},
    )
    superseding = orchestrator.supersede_candidate_a_telemetry_failure(state, candidate)
    assert original["classification"] == "CUDA_ERROR"
    assert candidate["failure"] == original
    assert candidate["status"] == "INFRASTRUCTURE_FAILED_RETRY_ELIGIBLE"
    assert candidate["scientific_status"] == "UNRESOLVED"
    assert superseding["reason"] == "POST_VALIDATION_TELEMETRY_DEVICE_MISMATCH"
    assert not superseding["numerical_instability_established"]
    assert orchestrator.infrastructure_retry_eligible(candidate)


def test_optimizer_telemetry_failure_is_classified_without_erasing_evidence(tmp_path):
    orchestrator = ModelSearchOrchestrator(SearchConfig.load(search_config(tmp_path)))
    state = orchestrator.initialize()
    candidate = orchestrator.register_candidate(state, "lr_0_0002")
    orchestrator.mark_running_external(state, candidate, "owner/kernel-b", 1)
    original = orchestrator.record_failure(
        state, candidate, "MULTI_EPOCH_STABILITY",
        "Expected all tensors to be on the same device, but got cuda:0 and cpu",
        {"epoch": 1, "step": 28125, "traceback": "optimizer_state_abs_max = _collection_abs_max(optimizer_tensors, device)"},
    )
    superseding = orchestrator.supersede_optimizer_telemetry_failure(state, candidate)
    assert candidate["failure"] == original
    assert candidate["failure_classification"] == "TELEMETRY_INFRASTRUCTURE_ERROR"
    assert candidate["scientific_status"] == "UNRESOLVED"
    assert candidate["decision"] == "INCONCLUSIVE"
    assert not candidate["retry_eligible"]
    assert superseding["reason"] == "POST_VALIDATION_OPTIMIZER_TELEMETRY_DEVICE_MISMATCH"
    assert not superseding["numerical_instability_established"]


def test_candidate_a_has_at_most_one_infrastructure_retry(tmp_path):
    orchestrator = ModelSearchOrchestrator(SearchConfig.load(search_config(tmp_path)))
    state = orchestrator.initialize()
    candidate = orchestrator.register_candidate(state, "lr_0_0003")
    orchestrator.record_failure(
        state, candidate, "MULTI_EPOCH_STABILITY",
        "Expected all tensors to be on the same device, cuda:0 and cpu",
    )
    orchestrator.supersede_candidate_a_telemetry_failure(state, candidate)
    orchestrator.authorize_infrastructure_retry(state, candidate)
    assert candidate["retry_count"] == 1
    assert state["budget"]["infrastructure_retries_consumed"] == 1
    with pytest.raises(RuntimeError, match="not eligible"):
        orchestrator.authorize_infrastructure_retry(state, candidate)


def test_numerical_failure_cannot_use_infrastructure_retry(tmp_path):
    orchestrator = ModelSearchOrchestrator(SearchConfig.load(search_config(tmp_path)))
    state = orchestrator.initialize()
    candidate = orchestrator.register_candidate(state, "lr_0_0003")
    assert not orchestrator.infrastructure_failure(state, candidate, "non-finite gradient:output.weight")
    assert candidate["failure_classification"] == "GRADIENT_INSTABILITY"
    assert not orchestrator.infrastructure_retry_eligible(candidate)


def test_baseline_hash_mismatch_blocks_promotion(tmp_path):
    path = search_config(tmp_path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["protected_baseline_expected_sha256"] = "0" * 64
    path.write_text(json.dumps(payload), encoding="utf-8")
    orchestrator = ModelSearchOrchestrator(SearchConfig.load(path))
    state = orchestrator.initialize()
    assert state["promotion_blocked"]
    assert state["promotion_block_reason"] == "PROTECTED_BASELINE_INTEGRITY_MISMATCH"
    candidate = orchestrator.register_candidate(state, "lr_0_0003")
    candidate.update({
        "status": "STABILITY_VALIDATED", "checkpoint_manifest": {"sha256": "abc", "size": 10},
        "metrics": {"checkpoint_size": 10, "vram_bytes": 20},
    })
    benchmark = tmp_path / "benchmark"
    _write_benchmark(benchmark, 7.0, 8.0, "PROMOTE V2")
    assert orchestrator.ingest_benchmark(state, candidate, benchmark) == "INCONCLUSIVE"
    assert state["promoted_candidate"] is None
    current = json.loads(orchestrator.current_best_path.read_text(encoding="utf-8"))
    assert current["candidate_id"] == "protected_gru"
    assert not current["validated"]


def test_expected_sha256_requires_exactly_64_hexadecimal_characters(tmp_path):
    assert is_sha256("a" * 64)
    assert is_sha256("A" * 64)
    assert not is_sha256("a" * 62)
    assert not is_sha256("g" * 64)
    path = search_config(tmp_path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["protected_baseline_expected_sha256"] = "a" * 62
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="exactly 64 hexadecimal"):
        SearchConfig.load(path)


def test_malformed_expected_hash_is_not_silently_reported_as_integrity_mismatch(tmp_path):
    path = search_config(tmp_path)
    config = SearchConfig.load(path)
    orchestrator = ModelSearchOrchestrator(config)
    config.payload["protected_baseline_expected_sha256"] = "a" * 62
    integrity = orchestrator.protected_baseline_integrity()
    assert not integrity["match"]
    assert not integrity["expected_sha256_valid_format"]
    assert integrity["verification_status"] == "EXPECTED_SHA256_MALFORMED"


def test_provenance_repair_preserves_history_and_checkpoint_bytes(tmp_path):
    path = search_config(tmp_path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    baseline = path.parents[1] / payload["protected_baseline"]
    measured = hashlib.sha256(baseline.read_bytes()).hexdigest()
    malformed = measured[:-2]
    payload["protected_baseline_expected_sha256"] = malformed
    path.write_text(json.dumps(payload), encoding="utf-8")
    provenance_path = path.parents[1] / "results" / "model_search" / "provenance.json"
    provenance_path.parent.mkdir(parents=True)
    provenance_path.write_text(json.dumps({
        "measured_sha256": measured,
        "provenance_status": "HISTORICAL_HASH_RECORD_TYPO_CONFIRMED",
        "evidence": [{
            "evidence_path": "archive/best.pt",
            "evidence_hash": measured,
            "metadata_match": True,
            "independent_historical_artifact": True,
        }],
    }), encoding="utf-8")
    bytes_before = baseline.read_bytes()
    result = repair_protected_baseline_sha256(path, provenance_path)
    repaired = json.loads(path.read_text(encoding="utf-8"))
    assert repaired["protected_baseline_expected_sha256"] == measured
    assert repaired["protected_baseline_expected_sha256_history"][-1]["value"] == malformed
    assert repaired["protected_baseline_expected_sha256_history"][-1]["value_length"] == 62
    assert baseline.read_bytes() == bytes_before
    assert result["checkpoint_sha256_before"] == result["checkpoint_sha256_after"] == measured
    assert not result["checkpoint_bytes_modified"]


def test_provenance_repair_requires_independent_matching_evidence(tmp_path):
    path = search_config(tmp_path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    baseline = path.parents[1] / payload["protected_baseline"]
    measured = hashlib.sha256(baseline.read_bytes()).hexdigest()
    payload["protected_baseline_expected_sha256"] = measured[:-2]
    path.write_text(json.dumps(payload), encoding="utf-8")
    provenance_path = path.parents[1] / "provenance.json"
    provenance_path.write_text(json.dumps({
        "measured_sha256": measured,
        "provenance_status": "HISTORICAL_HASH_RECORD_TYPO_CONFIRMED",
        "evidence": [{
            "evidence_hash": measured,
            "metadata_match": True,
            "independent_historical_artifact": False,
        }],
    }), encoding="utf-8")
    checkpoint_before = baseline.read_bytes()
    with pytest.raises(ValueError, match="independent metadata-matching"):
        repair_protected_baseline_sha256(path, provenance_path)
    assert baseline.read_bytes() == checkpoint_before
    assert json.loads(path.read_text(encoding="utf-8"))["protected_baseline_expected_sha256"] == measured[:-2]


def test_protected_gru_verification_writes_measured_checkpoint_metadata(tmp_path):
    path = search_config(tmp_path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    baseline = path.parents[1] / payload["protected_baseline"]
    model = build_model(ModelConfig(embedding_dim=8, hidden_dim=12, num_layers=1, context_length=16))
    save_checkpoint(baseline, model, epoch=3)
    payload["protected_baseline_expected_sha256"] = hashlib.sha256(baseline.read_bytes()).hexdigest()
    path.write_text(json.dumps(payload), encoding="utf-8")
    orchestrator = ModelSearchOrchestrator(SearchConfig.load(path))
    orchestrator.initialize()
    verification = orchestrator.write_protected_baseline_verification()
    assert verification["match"]
    assert verification["architecture"] == "causal-byte-gru-v1"
    assert verification["checkpoint_epoch"] == 3
    assert verification["size_bytes"] > 0
    persisted = json.loads((orchestrator.paths.results / "protected_gru_verification.json").read_text())
    assert persisted == verification

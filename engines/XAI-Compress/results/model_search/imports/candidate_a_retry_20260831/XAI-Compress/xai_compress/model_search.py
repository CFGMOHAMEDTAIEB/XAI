"""State and policy engine for controlled neural-lossless model search."""
from __future__ import annotations

import csv
import hashlib
import json
import math
import os
import re
import shutil
import tempfile
import traceback as traceback_module
from html import escape
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


TERMINAL_STATUSES = {
    "PREFLIGHT_FAILED", "SHORT_STABILITY_FAILED", "MULTI_EPOCH_STABILITY_FAILED",
    "LOSSLESS_CORRECTNESS_FAILED", "BENCHMARK_FAILED", "REJECTED", "VALIDATED",
    "INCONCLUSIVE", "KEEP_BASELINE", "PROMOTED", "INFRASTRUCTURE_FAILED_RETRY_ELIGIBLE",
}
NUMERICAL_FAILURES = {
    "NUMERICAL_INSTABILITY", "FORWARD_ACTIVATION_INSTABILITY", "AMP_GRADIENT_OVERFLOW",
    "GRADIENT_INSTABILITY", "OPTIMIZER_INSTABILITY",
}
MAJOR_FIELDS = {
    "architecture", "lr", "context_length", "embedding_dim", "num_layers",
    "n_heads", "ff_dim", "dropout", "residual_scale",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def is_sha256(value: Any) -> bool:
    """Return True only for a complete, lowercase-or-uppercase SHA-256 digest."""
    return isinstance(value, str) and re.fullmatch(r"[0-9a-fA-F]{64}", value) is not None


def candidate_fingerprint(config: dict) -> str:
    return hashlib.sha256(canonical_json(config).encode("utf-8")).hexdigest()


def deterministic_candidate_id(key: str, config: dict) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", key.lower()).strip("-") or "candidate"
    return f"{slug}-{candidate_fingerprint(config)[:10]}"


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, indent=2, allow_nan=False)
            handle.flush(); os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary): os.unlink(temporary)


def repair_protected_baseline_sha256(config_path: str | Path, provenance_path: str | Path) -> dict:
    """Repair only protection metadata after independently corroborated provenance.

    This deliberately operates on the raw JSON so a malformed legacy value can be
    repaired even though :class:`SearchConfig` correctly rejects it.  Checkpoint
    bytes are hashed before and after the metadata-only update and must not change.
    """
    config_path = Path(config_path).resolve()
    provenance_path = Path(provenance_path).resolve()
    config = json.loads(config_path.read_text(encoding="utf-8"))
    provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    measured = provenance.get("measured_sha256")
    old_value = config.get("protected_baseline_expected_sha256")
    if provenance.get("provenance_status") != "HISTORICAL_HASH_RECORD_TYPO_CONFIRMED":
        raise ValueError("provenance does not authorize baseline metadata repair")
    if not is_sha256(measured):
        raise ValueError("provenance measured_sha256 must be exactly 64 hexadecimal characters")
    corroborating = [
        item for item in provenance.get("evidence", [])
        if item.get("independent_historical_artifact") is True
        and item.get("metadata_match") is True
        and str(item.get("evidence_hash", "")).lower() == measured.lower()
    ]
    if not corroborating:
        raise ValueError("no independent metadata-matching historical artifact corroborates the digest")

    root = config_path.parents[1]
    checkpoint = (root / config["protected_baseline"]).resolve()
    before = sha256_file(checkpoint)
    if before.lower() != measured.lower():
        raise ValueError("protected checkpoint does not match the provenance digest")
    history = list(config.get("protected_baseline_expected_sha256_history", []))
    history.append({
        "value": old_value,
        "value_length": len(old_value) if isinstance(old_value, str) else None,
        "status": "MALFORMED_HISTORICAL_VALUE_PRESERVED",
        "superseded_at": utc_now(),
        "provenance_path": str(provenance_path),
    })
    config["protected_baseline_expected_sha256_history"] = history
    config["protected_baseline_expected_sha256"] = measured.lower()
    atomic_json(config_path, config)
    after = sha256_file(checkpoint)
    if after != before:
        raise RuntimeError("PROTECTED_GRU_CHANGED_DURING_METADATA_REPAIR")
    return {
        "old_expected_sha256": old_value,
        "expected_sha256": measured.lower(),
        "checkpoint_sha256_before": before,
        "checkpoint_sha256_after": after,
        "checkpoint_bytes_modified": False,
        "audit_history_preserved": True,
    }


def classify_failure(exception: BaseException | str, stage: str | None = None, details: dict | None = None) -> str:
    details = details or {}
    text = " ".join(filter(None, (str(exception), stage, str(details.get("first_non_finite_stage", ""))))).lower()
    if "out of memory" in text or "cuda oom" in text: return "CUDA_OOM"
    if isinstance(exception, ImportError) or "modulenotfounderror" in text or "importerror" in text: return "IMPORT_ERROR"
    if "source" in text and "hash" in text and ("mismatch" in text or "different" in text): return "INFRASTRUCTURE_ERROR"
    if isinstance(exception, (ConnectionError, TimeoutError)) or any(token in text for token in ("network", "connection", "timeout", "http", "infrastructure")):
        return "INFRASTRUCTURE_ERROR"
    if "determin" in text: return "DETERMINISM_ERROR"
    if "sha256" in text or "sha-256" in text or "lossless" in text and "fail" in text: return "LOSSLESS_CORRECTNESS_ERROR"
    if "checkpoint" in text or "fingerprint mismatch" in text: return "CHECKPOINT_ERROR"
    if "optimizer" in text and ("non-finite" in text or "nan" in text or "inf" in text): return "OPTIMIZER_INSTABILITY"
    if "gradient" in text and ("amp" in text or "scaler" in text or details.get("amp_only")):
        return "AMP_GRADIENT_OVERFLOW"
    if "gradient" in text and ("non-finite" in text or "nan" in text or "inf" in text): return "GRADIENT_INSTABILITY"
    if "activation" in text or "residual_ffn" in text or "ffn_output" in text: return "FORWARD_ACTIVATION_INSTABILITY"
    if any(token in text for token in ("non-finite", "nan", "infinity", "+inf", "-inf")): return "NUMERICAL_INSTABILITY"
    if "cuda" in text: return "CUDA_ERROR"
    if "benchmark" in text: return "BENCHMARK_ERROR"
    if isinstance(exception, (OSError, RuntimeError)) and any(token in text for token in ("environment", "disk", "permission")):
        return "ENVIRONMENT_ERROR"
    return "UNKNOWN_ERROR"


@dataclass(frozen=True)
class SearchPaths:
    root: Path
    results: Path
    checkpoints: Path
    baseline: Path


class SearchConfig:
    def __init__(self, source: Path, payload: dict):
        self.source = source.resolve(); self.root = self.source.parents[1]
        self.payload = payload
        self._validate()
        self.paths = SearchPaths(
            self.root,
            (self.root / payload["results_root"]).resolve(),
            (self.root / payload["checkpoint_root"]).resolve(),
            (self.root / payload["protected_baseline"]).resolve(),
        )

    @classmethod
    def load(cls, path: str | Path) -> "SearchConfig":
        source = Path(path)
        payload = json.loads(source.read_text(encoding="utf-8"))
        return cls(source, payload)

    def _validate(self) -> None:
        if self.payload.get("schema_version") != 1: raise ValueError("unsupported model-search schema")
        required = {"protected_baseline", "protected_baseline_expected_sha256", "results_root", "checkpoint_root", "budget", "selection", "base_config", "candidates"}
        missing = required - self.payload.keys()
        if missing: raise ValueError(f"missing model-search fields: {sorted(missing)}")
        if not is_sha256(self.payload["protected_baseline_expected_sha256"]):
            raise ValueError("protected_baseline_expected_sha256 must be exactly 64 hexadecimal characters")
        keys = [item.get("key") for item in self.payload["candidates"]]
        if any(not key or not isinstance(key, str) for key in keys) or len(keys) != len(set(keys)):
            raise ValueError("candidate keys must be unique non-empty strings")
        allowed_budget = ("max_candidates", "max_gpu_hours", "max_kaggle_submissions", "max_failures", "no_improvement_patience")
        if any(float(self.payload["budget"].get(name, 0)) <= 0 for name in allowed_budget):
            raise ValueError("all experiment budgets must be positive")
        for item in self.payload["candidates"]:
            change = item.get("change") or {}
            major = MAJOR_FIELDS.intersection(change)
            if len(major) != 1:
                raise ValueError(f"candidate {item['key']} must change exactly one major field; got {sorted(major)}")
            unknown = set(change) - set(self.payload["base_config"]) - {"residual_scale"}
            if unknown: raise ValueError(f"candidate {item['key']} has unknown fields: {sorted(unknown)}")

    @property
    def candidates(self) -> dict[str, dict]:
        return {item["key"]: item for item in self.payload["candidates"]}

    def resolve_candidate(self, key: str, best_stable_config: dict | None = None) -> dict:
        item = self.candidates[key]
        parent = item["parent"]
        if parent == "base": base = dict(self.payload["base_config"])
        elif parent == "@best_stable":
            if best_stable_config is None: raise ValueError(f"candidate {key} requires a best stable parent")
            base = dict(best_stable_config)
        else: base = self.resolve_candidate(parent, best_stable_config)
        base.update(item["change"])
        return base


class ModelSearchOrchestrator:
    def __init__(self, config: SearchConfig):
        self.config = config; self.paths = config.paths
        self.state_path = self.paths.results / "search_state.json"
        self.leaderboard_json = self.paths.results / "leaderboard.json"
        self.leaderboard_csv = self.paths.results / "leaderboard.csv"
        self.current_best_path = self.paths.checkpoints / "current_best.json"

    def _baseline_manifest(self) -> dict:
        path = self.paths.baseline
        if not path.is_file() or path.stat().st_size <= 0: raise FileNotFoundError(f"protected baseline unavailable: {path}")
        return {"path": str(path), "size": path.stat().st_size, "sha256": sha256_file(path)}

    def verify_protected_baseline(self, state: dict | None = None) -> dict:
        current = self._baseline_manifest()
        expected = (state or {}).get("protected_baseline")
        if expected and current != expected: raise RuntimeError("PROTECTED_GRU_CHANGED")
        checkpoint_root = self.paths.checkpoints
        if current["path"] == str(checkpoint_root) or checkpoint_root in self.paths.baseline.parents:
            raise RuntimeError("candidate checkpoint namespace overlaps protected baseline")
        return current

    def protected_baseline_integrity(self, current: dict | None = None) -> dict:
        current = current or self._baseline_manifest()
        expected = str(self.config.payload["protected_baseline_expected_sha256"]).lower()
        measured = str(current["sha256"]).lower()
        valid_format = is_sha256(expected)
        match = valid_format and measured == expected
        if not valid_format:
            verification_status = "EXPECTED_SHA256_MALFORMED"
        else:
            verification_status = "VERIFIED" if match else "PROTECTED_BASELINE_INTEGRITY_MISMATCH"
        return {
            "expected_sha256": expected,
            "measured_sha256": measured,
            "expected_sha256_valid_format": valid_format,
            "match": match,
            "verification_status": verification_status,
            "verified_at": utc_now(),
        }

    def write_protected_baseline_verification(self) -> dict:
        from .checkpoint import load_checkpoint

        manifest = self._baseline_manifest()
        integrity = self.protected_baseline_integrity(manifest)
        model, checkpoint = load_checkpoint(self.paths.baseline, "cpu")
        references = []
        needles = (manifest["sha256"].lower(), self.config.payload["protected_baseline"].replace("\\", "/").lower())
        for root in (self.paths.results, self.paths.checkpoints):
            if not root.exists():
                continue
            for path in root.rglob("*"):
                if not path.is_file() or path.suffix.lower() not in {".json", ".md", ".csv", ".txt"}:
                    continue
                try:
                    if path.stat().st_size > 10 << 20:
                        continue
                    text = path.read_text(encoding="utf-8", errors="replace").replace("\\", "/").lower()
                except OSError:
                    continue
                if any(needle in text for needle in needles):
                    references.append(str(path.resolve()))
        payload = {
            "path": str(self.paths.baseline),
            "measured_sha256": manifest["sha256"],
            "expected_sha256": integrity["expected_sha256"],
            "match": integrity["match"],
            "size_bytes": manifest["size"],
            "modification_timestamp_utc": datetime.fromtimestamp(
                self.paths.baseline.stat().st_mtime, timezone.utc
            ).isoformat(),
            "architecture": checkpoint.get("config", {}).get("architecture_id"),
            "config": checkpoint.get("config"),
            "checkpoint_format": checkpoint.get("format"),
            "checkpoint_epoch": checkpoint.get("epoch"),
            "checkpoint_fingerprint": checkpoint.get("fingerprint"),
            "parameter_count": sum(parameter.numel() for parameter in model.parameters()),
            "expected_sha256_valid_format": integrity["expected_sha256_valid_format"],
            "referencing_manifests": sorted(set(references)),
            "verification_status": integrity["verification_status"],
            "promotion_blocked": not integrity["match"],
            "verified_at": integrity["verified_at"],
        }
        atomic_json(self.paths.results / "protected_gru_verification.json", payload)
        return payload

    def _apply_integrity_interlock(self, state: dict, baseline: dict | None = None) -> bool:
        integrity = self.protected_baseline_integrity(baseline)
        state["protected_baseline_integrity"] = integrity
        state["promotion_blocked"] = not integrity["match"]
        state["promotion_block_reason"] = None if integrity["match"] else integrity["verification_status"]
        if state["promotion_blocked"]:
            state["promoted_candidate"] = None
        return state["promotion_blocked"]

    def initialize(self) -> dict:
        if self.state_path.is_file(): return self.load_state()
        self.paths.results.mkdir(parents=True, exist_ok=True)
        for directory in ("failures", "candidates", "plots", "reports", "imports"):
            (self.paths.results / directory).mkdir(exist_ok=True)
        self.paths.checkpoints.mkdir(parents=True, exist_ok=True)
        baseline = self.verify_protected_baseline()
        state = {
            "schema_version": 1, "search_name": self.config.payload["search_name"],
            "config_path": str(self.config.source), "created_at": utc_now(), "updated_at": utc_now(),
            "status": "ACTIVE", "protected_baseline": baseline,
            "pending_candidates": [item["key"] for item in self.config.payload["candidates"]],
            "running_candidate": None, "completed_candidates": [], "failed_candidates": [],
            "validated_candidates": [], "promoted_candidate": None, "best_stable_candidate": None,
            "candidates": {}, "seen_fingerprints": {},
            "budget": {**self.config.payload["budget"], "candidates_consumed": 0, "gpu_hours_consumed": 0.0,
                       "kaggle_submissions_consumed": 0, "failures_consumed": 0, "eligible_without_improvement": 0,
                       "infrastructure_retries_consumed": 0, "numerical_failures_consumed": 0},
            "infrastructure_retries": {}, "stop_reason": None,
        }
        self._apply_integrity_interlock(state, baseline)
        atomic_json(self.current_best_path, {"candidate_id": "protected_gru", **baseline,
            "validated": not state["promotion_blocked"], "baseline_integrity": state["protected_baseline_integrity"],
            "application_default_changed": False})
        self.save_state(state); self.update_leaderboard(state); return state

    def load_state(self) -> dict:
        state = json.loads(self.state_path.read_text(encoding="utf-8"))
        baseline = self.verify_protected_baseline(state)
        changed = False
        budget = state["budget"]
        for key in ("infrastructure_retries_consumed", "numerical_failures_consumed"):
            if key not in budget:
                budget[key] = 0; changed = True
        prior = (state.get("promotion_blocked"), state.get("promotion_block_reason"))
        self._apply_integrity_interlock(state, baseline)
        changed = changed or prior != (state.get("promotion_blocked"), state.get("promotion_block_reason"))
        if changed:
            state["updated_at"] = utc_now(); atomic_json(self.state_path, state)
            current = json.loads(self.current_best_path.read_text(encoding="utf-8")) if self.current_best_path.is_file() else {}
            if current.get("candidate_id") == "protected_gru":
                current.update({"validated": not state["promotion_blocked"],
                                "baseline_integrity": state["protected_baseline_integrity"]})
                atomic_json(self.current_best_path, current)
        return state

    def save_state(self, state: dict) -> None:
        self.verify_protected_baseline(state if state.get("protected_baseline") else None)
        state["updated_at"] = utc_now(); atomic_json(self.state_path, state)

    def _best_stable_config(self, state: dict) -> dict | None:
        candidate_id = state.get("best_stable_candidate")
        return state["candidates"][candidate_id]["resolved_config"] if candidate_id else None

    def register_candidate(self, state: dict, key: str) -> dict:
        resolved = self.config.resolve_candidate(key, self._best_stable_config(state))
        fingerprint = candidate_fingerprint(resolved); candidate_id = deterministic_candidate_id(key, resolved)
        existing = state["seen_fingerprints"].get(fingerprint)
        if existing:
            return state["candidates"][existing]
        if state["budget"]["candidates_consumed"] >= state["budget"]["max_candidates"]:
            self.stop(state, "SEARCH_BUDGET_EXHAUSTED"); raise RuntimeError("candidate budget exhausted")
        definition = self.config.candidates[key]
        checkpoint_dir = (self.paths.checkpoints / candidate_id).resolve()
        candidate_dir = (self.paths.results / "candidates" / candidate_id).resolve()
        if checkpoint_dir == self.paths.baseline or checkpoint_dir in self.paths.baseline.parents:
            raise RuntimeError("PROTECTED_GRU_OVERWRITE_ATTEMPT")
        record = {
            "candidate_id": candidate_id, "candidate_key": key, "fingerprint": fingerprint,
            "parent": definition["parent"], "change": definition["change"], "change_label": definition["change_label"],
            "activation_rule": definition["activation_rule"], "resolved_config": resolved,
            "status": "PENDING", "phase": 0, "created_at": utc_now(), "updated_at": utc_now(),
            "checkpoint_dir": str(checkpoint_dir), "candidate_dir": str(candidate_dir),
            "source_hashes": {}, "metrics": {}, "decision": "REJECT", "infrastructure_retries": 0,
        }
        checkpoint_dir.mkdir(parents=True, exist_ok=True); (checkpoint_dir / "periodic").mkdir(exist_ok=True)
        candidate_dir.mkdir(parents=True, exist_ok=True); atomic_json(candidate_dir / "config.json", record)
        state["candidates"][candidate_id] = record; state["seen_fingerprints"][fingerprint] = candidate_id
        state["budget"]["candidates_consumed"] += 1
        if key in state["pending_candidates"]: state["pending_candidates"].remove(key)
        self.save_state(state); return record

    def mark_running_external(self, state: dict, candidate: dict, kernel: str, version: int, count_submission=True) -> None:
        if (candidate.get("status") == "MULTI_EPOCH_RUNNING"
                and candidate.get("kaggle_kernel") == kernel
                and int(candidate.get("kaggle_version", -1)) == int(version)):
            return
        if candidate["status"] in TERMINAL_STATUSES: raise RuntimeError("cannot rerun a terminal candidate")
        if state["running_candidate"] not in (None, candidate["candidate_id"]): raise RuntimeError("another candidate is already running")
        if count_submission:
            if state["budget"]["kaggle_submissions_consumed"] >= state["budget"]["max_kaggle_submissions"]:
                self.stop(state, "SEARCH_BUDGET_EXHAUSTED"); raise RuntimeError("Kaggle submission budget exhausted")
            state["budget"]["kaggle_submissions_consumed"] += 1
        candidate.update({"status": "MULTI_EPOCH_RUNNING", "phase": 2, "kaggle_kernel": kernel,
                          "kaggle_version": version, "updated_at": utc_now()})
        state["running_candidate"] = candidate["candidate_id"]
        atomic_json(Path(candidate["candidate_dir"]) / "status.json", candidate); self.save_state(state)

    def record_failure(self, state: dict, candidate: dict, stage: str, exception: BaseException | str,
                       evidence: dict | None = None, trace: str | None = None) -> dict:
        evidence = dict(evidence or {}); classification = classify_failure(exception, stage, evidence)
        failure = {
            "candidate_id": candidate["candidate_id"], "candidate_key": candidate["candidate_key"],
            "parent_candidate": candidate["parent"], "timestamp": utc_now(), "stage": stage,
            "classification": classification, "exception": str(exception),
            "epoch": evidence.get("epoch"), "step": evidence.get("step"),
            "tensor_name": evidence.get("tensor_name") or evidence.get("first_non_finite_stage"),
            "dtype": evidence.get("dtype"), "shape": evidence.get("shape"),
            "min": evidence.get("min"), "max": evidence.get("max"), "mean": evidence.get("mean"), "std": evidence.get("std"),
            "activation_maxima": evidence.get("activation_maxima") or evidence.get("layer_trajectories"),
            "grad_scaler_scale": evidence.get("grad_scaler_scale"), "grad_norm": evidence.get("gradient_norm"),
            "learning_rate": candidate["resolved_config"].get("lr"), "source_hashes": candidate.get("source_hashes", {}),
            "traceback": trace or (traceback_module.format_exc() if isinstance(exception, BaseException) else None),
            "status": "MULTI_EPOCH_STABILITY_FAILED" if stage == "MULTI_EPOCH_STABILITY" else f"{stage}_FAILED",
            "evidence": evidence,
        }
        candidate.update({"status": failure["status"], "failure_classification": classification,
                          "failure": failure, "updated_at": utc_now(), "decision": "REJECT"})
        state["running_candidate"] = None
        if candidate["candidate_id"] not in state["failed_candidates"]: state["failed_candidates"].append(candidate["candidate_id"])
        if candidate["candidate_id"] not in state["completed_candidates"]: state["completed_candidates"].append(candidate["candidate_id"])
        state["budget"]["failures_consumed"] += 1
        if classification in NUMERICAL_FAILURES:
            state["budget"]["numerical_failures_consumed"] = state["budget"].get("numerical_failures_consumed", 0) + 1
        duration = evidence.get("duration_seconds")
        if isinstance(duration, (int, float)) and math.isfinite(duration) and duration >= 0:
            state["budget"]["gpu_hours_consumed"] += float(duration) / 3600.0
            candidate["gpu_hours_accounted"] = float(duration) / 3600.0
        failure_dir = self.paths.results / "failures"; atomic_json(failure_dir / f"{candidate['candidate_id']}.json", failure)
        atomic_json(Path(candidate["candidate_dir"]) / "failure.json", failure)
        atomic_json(Path(candidate["candidate_dir"]) / "status.json", candidate)
        if state["budget"]["failures_consumed"] >= state["budget"]["max_failures"]: self.stop(state, "SEARCH_BUDGET_EXHAUSTED")
        self.save_state(state); self.update_leaderboard(state); return failure

    def supersede_candidate_a_telemetry_failure(self, state: dict, candidate: dict) -> dict:
        """Correct Candidate A's scientific classification without erasing evidence."""
        original = candidate.get("failure")
        if not original:
            raise ValueError("Candidate A original failure evidence is missing")
        existing = candidate.get("superseding_classification")
        if existing:
            if not candidate.get("failure_class"):
                candidate["failure_class"] = existing["failure_class"]
                atomic_json(Path(candidate["candidate_dir"]) / "status.json", candidate)
                self.save_state(state)
            return existing
        if candidate.get("candidate_key") != "lr_0_0003":
            raise ValueError("telemetry supersession applies only to Candidate A")
        message = str(original.get("exception", "")).lower()
        if "same device" not in message or "cuda" not in message:
            raise ValueError("original failure is not the measured telemetry device mismatch")
        failure_id = hashlib.sha256(canonical_json(original).encode("utf-8")).hexdigest()
        superseding = {
            "classification_id": hashlib.sha256((failure_id + ":telemetry-supersession").encode()).hexdigest(),
            "candidate_id": candidate["candidate_id"],
            "timestamp": utc_now(),
            "status": "INFRASTRUCTURE_FAILED_RETRY_ELIGIBLE",
            "failure_class": "TELEMETRY_INFRASTRUCTURE_ERROR",
            "reason": "POST_VALIDATION_TELEMETRY_DEVICE_MISMATCH",
            "retry_eligible": True,
            "retry_count": 0,
            "max_retries": 1,
            "supersedes_failure_id": failure_id,
            "model_evidence_valid": False,
            "infrastructure_evidence_valid": True,
            "scientific_status": "UNRESOLVED",
            "numerical_instability_established": False,
            "original_failure_preserved_at": str(self.paths.results / "failures" / f"{candidate['candidate_id']}.json"),
        }
        candidate.update({
            "status": superseding["status"],
            "failure_classification": superseding["failure_class"],
            "failure_class": superseding["failure_class"],
            "scientific_status": superseding["scientific_status"],
            "retry_eligible": True,
            "retry_count": 0,
            "max_retries": 1,
            "model_evidence_valid": False,
            "infrastructure_evidence_valid": True,
            "superseding_classification": superseding,
            "decision": "INCONCLUSIVE",
            "updated_at": utc_now(),
        })
        if candidate["candidate_id"] not in state.setdefault("unresolved_candidates", []):
            state["unresolved_candidates"].append(candidate["candidate_id"])
        destination = self.paths.results / "failures" / f"{candidate['candidate_id']}.superseding.json"
        atomic_json(destination, superseding)
        atomic_json(Path(candidate["candidate_dir"]) / "superseding_classification.json", superseding)
        atomic_json(Path(candidate["candidate_dir"]) / "status.json", candidate)
        self.save_state(state); self.update_leaderboard(state)
        return superseding

    def supersede_optimizer_telemetry_failure(self, state: dict, candidate: dict) -> dict:
        """Classify mixed-device AdamW telemetry without changing raw failure evidence."""
        original = candidate.get("failure")
        if not original:
            raise ValueError("original failure evidence is missing")
        existing = candidate.get("optimizer_telemetry_superseding_classification")
        if existing:
            return existing
        message = str(original.get("exception", "")).lower()
        traceback = str(original.get("traceback") or original.get("evidence", {}).get("traceback", "")).lower()
        if not (
            "same device" in message
            and "cuda" in message
            and "_collection_abs_max" in traceback
            and "optimizer" in traceback
        ):
            raise ValueError("original failure is not the measured optimizer telemetry device mismatch")
        failure_id = hashlib.sha256(canonical_json(original).encode("utf-8")).hexdigest()
        superseding = {
            "classification_id": hashlib.sha256((failure_id + ":optimizer-telemetry-supersession").encode()).hexdigest(),
            "candidate_id": candidate["candidate_id"],
            "timestamp": utc_now(),
            "status": "INFRASTRUCTURE_FAILED",
            "failure_class": "TELEMETRY_INFRASTRUCTURE_ERROR",
            "reason": "POST_VALIDATION_OPTIMIZER_TELEMETRY_DEVICE_MISMATCH",
            "retry_eligible": False,
            "supersedes_failure_id": failure_id,
            "model_evidence_valid": False,
            "infrastructure_evidence_valid": True,
            "scientific_status": "UNRESOLVED",
            "numerical_instability_established": False,
            "original_failure_preserved_at": str(self.paths.results / "failures" / f"{candidate['candidate_id']}.json"),
        }
        candidate.update({
            "status": superseding["status"],
            "failure_classification": superseding["failure_class"],
            "failure_class": superseding["failure_class"],
            "scientific_status": superseding["scientific_status"],
            "retry_eligible": False,
            "model_evidence_valid": False,
            "infrastructure_evidence_valid": True,
            "optimizer_telemetry_superseding_classification": superseding,
            "decision": "INCONCLUSIVE",
            "updated_at": utc_now(),
        })
        if candidate["candidate_id"] not in state.setdefault("unresolved_candidates", []):
            state["unresolved_candidates"].append(candidate["candidate_id"])
        destination = self.paths.results / "failures" / f"{candidate['candidate_id']}.superseding.json"
        atomic_json(destination, superseding)
        atomic_json(Path(candidate["candidate_dir"]) / "optimizer_telemetry_superseding_classification.json", superseding)
        atomic_json(Path(candidate["candidate_dir"]) / "status.json", candidate)
        self.save_state(state); self.update_leaderboard(state)
        return superseding

    @staticmethod
    def infrastructure_retry_eligible(candidate: dict) -> bool:
        return bool(
            candidate.get("retry_eligible")
            and candidate.get("failure_classification") in {"TELEMETRY_INFRASTRUCTURE_ERROR", "INFRASTRUCTURE_ERROR", "CUDA_ERROR"}
            and int(candidate.get("retry_count", 0)) < int(candidate.get("max_retries", 0))
            and candidate.get("scientific_status") == "UNRESOLVED"
        )

    def authorize_infrastructure_retry(self, state: dict, candidate: dict) -> None:
        if state.get("running_candidate"):
            raise RuntimeError("cannot authorize a retry while another candidate is running")
        if not self.infrastructure_retry_eligible(candidate):
            raise RuntimeError("candidate is not eligible for an infrastructure retry")
        candidate["retry_count"] = int(candidate.get("retry_count", 0)) + 1
        candidate["retry_eligible"] = False
        candidate["status"] = "INFRASTRUCTURE_RETRY_PENDING"
        state["budget"]["infrastructure_retries_consumed"] = state["budget"].get("infrastructure_retries_consumed", 0) + 1
        self.save_state(state)

    def validate_stability_summary(self, summary: dict) -> tuple[bool, list[str]]:
        selection = self.config.payload["selection"]; reasons=[]
        if summary.get("status") != "PASS": reasons.append("diagnostic status is not PASS")
        if int(summary.get("epochs", 0)) < int(selection["minimum_stability_epochs"]): reasons.append("fewer than five complete epochs")
        if int(summary.get("training_samples_per_epoch", 0)) < 450000: reasons.append("training sample gate incomplete")
        if int(summary.get("validation_samples_per_epoch", 0)) < 50000: reasons.append("validation sample gate incomplete")
        if not summary.get("finite_metrics"): reasons.append("finite metrics gate failed")
        if not summary.get("finite_parameters"): reasons.append("finite parameter gate failed")
        if not summary.get("finite_optimizer_state"): reasons.append("finite optimizer-state gate failed")
        if not summary.get("checkpoint_load"): reasons.append("checkpoint load failed")
        if not summary.get("deterministic_inference"): reasons.append("deterministic inference failed")
        if not summary.get("lossless_sha256"): reasons.append("SHA-256 lossless gate failed")
        if float(summary.get("max_activation", math.inf)) >= float(selection["activation_hard_limit"]): reasons.append("activation safety limit exceeded")
        if summary.get("layer_3_growth") == "STRONGLY_ACCELERATING": reasons.append("strongly accelerating layer-3 trajectory")
        return not reasons, reasons

    @staticmethod
    def _finite_tensor_tree(value: Any) -> tuple[bool, float, int]:
        """Return finiteness, largest absolute value, and tensor count for nested state."""
        import torch

        finite = True
        absolute_max = 0.0
        tensor_count = 0
        pending = [value]
        while pending:
            current = pending.pop()
            if isinstance(current, dict):
                pending.extend(current.values())
            elif isinstance(current, (list, tuple)):
                pending.extend(current)
            elif torch.is_tensor(current):
                tensor_count += 1
                if not bool(torch.isfinite(current).all()):
                    finite = False
                if current.numel() and (current.is_floating_point() or current.is_complex()):
                    absolute_max = max(absolute_max, float(current.detach().abs().max().cpu()))
        return finite, absolute_max, tensor_count

    def _verify_checkpoint_locally(self, checkpoint: Path) -> dict:
        """Repeat the non-training acceptance gates on the downloaded artifact."""
        import random
        import torch

        from .checkpoint import load_checkpoint
        from .compression import compress_bytes, decompress_bytes

        model, checkpoint_object = load_checkpoint(checkpoint, "cpu")
        parameter_finite, parameter_abs_max, parameter_tensors = self._finite_tensor_tree(
            checkpoint_object.get("state_dict", {})
        )
        optimizer_present = "optimizer_state" in checkpoint_object
        optimizer_finite, optimizer_abs_max, optimizer_tensors = self._finite_tensor_tree(
            checkpoint_object.get("optimizer_state", {})
        )
        if not parameter_finite:
            raise FloatingPointError("NON_FINITE_CHECKPOINT_PARAMETER")
        if not optimizer_present or optimizer_tensors == 0:
            raise RuntimeError("CHECKPOINT_OPTIMIZER_STATE_MISSING")
        if not optimizer_finite:
            raise FloatingPointError("NON_FINITE_CHECKPOINT_OPTIMIZER_STATE")

        with torch.inference_mode():
            first, _ = model.step(256, None)
            second, _ = model.step(256, None)
        deterministic = torch.equal(first, second)
        if not deterministic:
            raise RuntimeError("DETERMINISTIC_INFERENCE_FAILED")

        generator = random.Random(int(self.config.payload["seed"]))
        corpus = {
            "empty": b"",
            "tiny": b"x",
            "text": b"XAI-Compress local candidate acceptance gate\n" * 16,
            "all_bytes": bytes(range(256)) * 2,
            "random": bytes(generator.randrange(256) for _ in range(1024)),
        }
        roundtrips = []
        for name, original in corpus.items():
            artifact = compress_bytes(original, "neural-lossless", checkpoint, device="cpu")
            reconstructed = decompress_bytes(artifact, checkpoint, device="cpu")
            original_hash = hashlib.sha256(original).hexdigest()
            reconstructed_hash = hashlib.sha256(reconstructed).hexdigest()
            roundtrips.append({
                "name": name,
                "bytes": len(original),
                "artifact_bytes": len(artifact),
                "original_sha256": original_hash,
                "reconstructed_sha256": reconstructed_hash,
                "pass": original_hash == reconstructed_hash,
            })
        lossless = all(item["pass"] for item in roundtrips)
        if not lossless:
            raise RuntimeError("SHA256_LOSSLESS_ROUNDTRIP_FAILED")
        return {
            "checkpoint_load": True,
            "checkpoint_epoch": checkpoint_object.get("epoch"),
            "checkpoint_size": checkpoint.stat().st_size,
            "checkpoint_sha256": sha256_file(checkpoint),
            "finite_parameters": parameter_finite,
            "parameter_tensor_count": parameter_tensors,
            "parameter_abs_max": parameter_abs_max,
            "finite_optimizer_state": optimizer_finite,
            "optimizer_tensor_count": optimizer_tensors,
            "optimizer_state_abs_max": optimizer_abs_max,
            "deterministic_inference": deterministic,
            "lossless_sha256": lossless,
            "roundtrips": roundtrips,
            "verified_at": utc_now(),
        }

    def _copy_candidate_artifacts(self, candidate: dict, source: Path) -> dict:
        checkpoint_dir=Path(candidate["checkpoint_dir"]);candidate_dir=Path(candidate["candidate_dir"])
        mappings = {
            "best.pt": checkpoint_dir/"best.pt", "best.latest.pt": checkpoint_dir/"best.latest.pt",
            "best.metrics.csv": candidate_dir/"training_metrics.csv", "best.history.json": candidate_dir/"history.json",
            "best.summary.json": candidate_dir/"checkpoint_summary.json",
            "multi_epoch_stability.csv": candidate_dir/"metrics.csv",
            "diagnostic_summary.json": candidate_dir/"summary.json",
            "training_status.json": candidate_dir/"training_status.json",
        }
        for name,destination in mappings.items():
            original=source/name
            if not original.is_file(): continue
            if destination.exists() and sha256_file(destination) != sha256_file(original):
                raise RuntimeError(f"candidate artifact collision: {destination}")
            destination.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(original,destination)
        checkpoint=checkpoint_dir/"best.pt"
        if not checkpoint.is_file() or checkpoint.stat().st_size <= 0: raise RuntimeError("validated candidate best.pt missing")
        manifest={"candidate_id":candidate["candidate_id"],"checkpoint":str(checkpoint),"size":checkpoint.stat().st_size,"sha256":sha256_file(checkpoint),"created_at":utc_now()}
        atomic_json(candidate_dir/"checkpoint_manifest.json",manifest);return manifest

    @staticmethod
    def _merge_training_status(source: Path, summary: dict) -> dict:
        status_path = source / "training_status.json"
        if not status_path.is_file():
            return summary
        training_status = json.loads(status_path.read_text(encoding="utf-8"))
        merged = dict(summary)
        merged["training_status"] = training_status
        for source_key, target_key in (
            ("epoch", "epoch"), ("step", "step"), ("train_loss", "loss"),
            ("validation_loss", "validation_loss"), ("BPB", "validation_bpb"),
            ("GPU", "gpu"), ("VRAM", "vram"), ("last_checkpoint", "last_checkpoint"),
        ):
            if training_status.get(source_key) is not None:
                merged.setdefault(target_key, training_status[source_key])
        merged.setdefault("last_known_stage", training_status.get("status"))
        return merged

    def _refresh_terminal_failure(self, state: dict, candidate: dict, source: Path, summary: dict) -> None:
        enriched = self._merge_training_status(source, summary)
        failure = candidate.get("failure") or {}
        failure["evidence"] = {**failure.get("evidence", {}), **enriched}
        for key in ("epoch", "step"):
            if failure.get(key) is None:
                failure[key] = enriched.get(key)
        candidate["failure"] = failure
        if not candidate.get("gpu_hours_accounted"):
            duration = enriched.get("duration_seconds")
            if isinstance(duration, (int, float)) and math.isfinite(duration) and duration >= 0:
                hours = float(duration) / 3600.0
                state["budget"]["gpu_hours_consumed"] += hours
                candidate["gpu_hours_accounted"] = hours
        atomic_json(self.paths.results/"failures"/f"{candidate['candidate_id']}.json",failure)
        atomic_json(Path(candidate["candidate_dir"])/"failure.json",failure)
        atomic_json(Path(candidate["candidate_dir"])/"status.json",candidate)
        self.save_state(state)

    def ingest_stability_result(self, state: dict, candidate: dict, source: str | Path, summary: dict | None = None) -> bool:
        source=Path(source);summary_path=source/"diagnostic_summary.json"
        summary=summary or json.loads(summary_path.read_text(encoding="utf-8"))
        if candidate.get("status") in {"STABILITY_VALIDATED", "VALIDATED", "PROMOTED"}:
            return True
        if candidate.get("status") in TERMINAL_STATUSES:
            self._refresh_terminal_failure(state, candidate, source, summary)
            return False
        summary = self._merge_training_status(source, summary)
        checkpoint = source / "best.pt"
        if summary.get("status") == "PASS":
            try:
                local_evidence = self._verify_checkpoint_locally(checkpoint)
            except Exception as exc:
                self.record_failure(
                    state, candidate, "LOSSLESS_CORRECTNESS", exc,
                    {"checkpoint": str(checkpoint), "kaggle_summary": summary},
                    traceback_module.format_exc(),
                )
                return False
            # The running Version 1 worker omitted an explicit optimizer boolean
            # from its final JSON.  This local scan supplies direct measured
            # evidence without changing or repeating the Kaggle experiment.
            summary = {**summary, **{
                key: local_evidence[key]
                for key in (
                    "checkpoint_load", "finite_parameters", "finite_optimizer_state",
                    "deterministic_inference", "lossless_sha256",
                )
            }}
            summary["local_checkpoint_validation"] = local_evidence
        passed,reasons=self.validate_stability_summary(summary)
        if not passed:
            self.record_failure(state,candidate,"MULTI_EPOCH_STABILITY",summary.get("exception") or "; ".join(reasons),summary)
            return False
        manifest=self._copy_candidate_artifacts(candidate,source)
        atomic_json(Path(candidate["candidate_dir"])/"local_checkpoint_validation.json",summary["local_checkpoint_validation"])
        manifests = sorted(source.parent.rglob("source-sha256.json"))
        if manifests:
            candidate["source_hashes"] = json.loads(manifests[0].read_text(encoding="utf-8"))
        history=summary.get("history") or []
        best_row=min(history,key=lambda row:float(row["val_cross_entropy"])) if history else {}
        candidate.update({"status":"STABILITY_VALIDATED","phase":3,"stability_summary":summary,
            "checkpoint_manifest":manifest,"metrics":{
                "best_validation_ce":best_row.get("val_cross_entropy"),"best_validation_bpb":best_row.get("val_bpb_estimate"),
                "best_epoch":best_row.get("epoch"),"max_activation":summary.get("max_activation"),
                "vram_bytes":max((float(row.get("vram_max_bytes",0)) for row in history),default=None),
                "training_samples_per_second":sum(float(row.get("samples_per_second",0)) for row in history)/len(history) if history else None,
                "checkpoint_size":manifest["size"],
                "duration_seconds":summary.get("duration_seconds"),
            },"decision":"INCONCLUSIVE","updated_at":utc_now()})
        state["running_candidate"]=None
        if candidate["candidate_id"] not in state["validated_candidates"]:state["validated_candidates"].append(candidate["candidate_id"])
        if candidate["candidate_id"] not in state["completed_candidates"]:state["completed_candidates"].append(candidate["candidate_id"])
        state["best_stable_candidate"]=candidate["candidate_id"]
        duration = summary.get("duration_seconds")
        if isinstance(duration, (int, float)) and math.isfinite(duration) and duration >= 0:
            state["budget"]["gpu_hours_consumed"] += float(duration) / 3600.0
            self._check_stop_conditions(state)
        atomic_json(Path(candidate["candidate_dir"])/"status.json",candidate);self.save_state(state);self.update_leaderboard(state);return True

    def ingest_benchmark(self, state: dict, candidate: dict, benchmark_dir: str | Path) -> str:
        benchmark_dir=Path(benchmark_dir);decision=json.loads((benchmark_dir/"promotion_decision.json").read_text(encoding="utf-8"))
        summaries=decision.get("summaries") or []
        candidate_summary=next((row for row in summaries if row.get("method")=="transformer_v2" and row.get("status")=="PASS"),None)
        baseline_summary=next((row for row in summaries if row.get("method")=="old_gru" and row.get("status")=="PASS"),None)
        if not candidate_summary or not candidate_summary.get("sha256_pass"):
            self.record_failure(state,candidate,"LOSSLESS_CORRECTNESS","candidate SHA-256 benchmark gate failed",{"summaries":summaries})
            return "REJECT"
        for filename,target in (("benchmark_raw.csv","benchmark.csv"),("benchmark_summary.csv","bpb_breakdown.csv")):
            source=benchmark_dir/filename
            if source.is_file():shutil.copy2(source,Path(candidate["candidate_dir"])/target)
        candidate["metrics"].update({
            "actual_bpb":candidate_summary.get("actual_bpb"),"ratio":candidate_summary.get("ratio"),
            "compression_MB_s":candidate_summary.get("compression_MB_s_median"),
            "decompression_MB_s":candidate_summary.get("decompression_MB_s_median"),
            "peak_RSS_MB":candidate_summary.get("peak_RSS_MB_max"),"sha256_pass":True,
            "model_entropy_bpb":candidate_summary.get("model_entropy_bpb"),
            "quantization_delta_bpb":candidate_summary.get("quantization_delta_bpb"),
            "coder_overhead_bpb":candidate_summary.get("entropy_coder_overhead_bpb"),
            "container_overhead_bpb":candidate_summary.get("container_overhead_bpb"),
            "baseline_actual_bpb":baseline_summary.get("actual_bpb") if baseline_summary else None,
        })
        candidate["phase"]=5;candidate["status"]="VALIDATED";candidate["decision"]=decision.get("decision","INCONCLUSIVE")
        if candidate["decision"]=="PROMOTE V2":candidate["decision"]="PROMOTE"
        elif candidate["decision"]=="KEEP OLD GRU":candidate["decision"]="KEEP_GRU"
        if state.get("promotion_blocked") and candidate["decision"] == "PROMOTE":
            candidate["benchmark_decision_before_integrity_interlock"] = "PROMOTE"
            candidate["decision"] = "INCONCLUSIVE"
            candidate["promotion_blocked_reason"] = state.get("promotion_block_reason")
        state["budget"]["eligible_without_improvement"] = 0 if candidate["decision"]=="PROMOTE" else state["budget"]["eligible_without_improvement"]+1
        self._select_current_best(state);self._check_stop_conditions(state)
        atomic_json(Path(candidate["candidate_dir"])/"status.json",candidate);self.save_state(state);self.update_leaderboard(state);self.write_report(state)
        return candidate["decision"]

    def _select_current_best(self,state:dict)->None:
        if state.get("promotion_blocked"):
            state["promoted_candidate"] = None
            return
        eligible=[item for item in state["candidates"].values() if item.get("status")=="VALIDATED" and item.get("decision")=="PROMOTE" and item.get("metrics",{}).get("sha256_pass") and item.get("metrics",{}).get("actual_bpb") is not None]
        if not eligible:
            return
        best=min(eligible,key=lambda item:float(item["metrics"]["actual_bpb"]))
        current={"candidate_id":best["candidate_id"],"path":str(Path(best["checkpoint_dir"])/"best.pt"),
                 "sha256":best["checkpoint_manifest"]["sha256"],"actual_bpb":best["metrics"]["actual_bpb"],
                 "validated":True,"application_default_changed":False,"updated_at":utc_now()}
        atomic_json(self.current_best_path,current);state["promoted_candidate"]=best["candidate_id"] if best.get("decision")=="PROMOTE" else None

    def _check_stop_conditions(self,state:dict)->None:
        budget=state["budget"]
        if budget["gpu_hours_consumed"]>=budget["max_gpu_hours"] or budget["candidates_consumed"]>=budget["max_candidates"] or budget["kaggle_submissions_consumed"]>=budget["max_kaggle_submissions"] or budget["failures_consumed"]>=budget["max_failures"]:
            self.stop(state,"SEARCH_BUDGET_EXHAUSTED")
        elif budget["eligible_without_improvement"]>=budget["no_improvement_patience"]:self.stop(state,"NO_SIGNIFICANT_IMPROVEMENT")
        elif state.get("promoted_candidate"):self.stop(state,"SUCCESS")

    def record_gpu_hours(self,state:dict,hours:float)->None:
        if hours<0 or not math.isfinite(hours):raise ValueError("GPU hours must be finite and non-negative")
        state["budget"]["gpu_hours_consumed"]+=hours;self._check_stop_conditions(state);self.save_state(state)

    def infrastructure_failure(self,state:dict,candidate:dict,exception:BaseException|str)->bool:
        classification = classify_failure(exception)
        if classification in NUMERICAL_FAILURES or classification in {"CUDA_OOM", "LOSSLESS_CORRECTNESS_ERROR", "DETERMINISM_ERROR", "CHECKPOINT_ERROR"}:
            self.record_failure(state,candidate,"MULTI_EPOCH_STABILITY",exception,{"retry_eligible":False})
            return False
        maximum=int(self.config.payload["kaggle"]["max_infrastructure_retries"]);count=int(candidate.get("infrastructure_retries",0))+1
        candidate["infrastructure_retries"]=count
        if count>maximum:self.record_failure(state,candidate,"INFRASTRUCTURE",exception,{"retry_count":count});return False
        candidate["status"]="INFRASTRUCTURE_RETRY_PENDING";self.save_state(state);return True

    def next_candidate_key(self,state:dict)->str|None:
        if state["status"]!="ACTIVE":return None
        records={item["candidate_key"]:item for item in state["candidates"].values()}
        first=records.get("lr_0_0003")
        if first is None:return "lr_0_0003"
        if first.get("status") == "STABILITY_VALIDATED":return None
        if first["status"] not in TERMINAL_STATUSES and first["status"]!="STABILITY_VALIDATED":return None
        if first.get("status") == "VALIDATED":
            return next((key for key in ("context_512","ffn_1024","layers_6") if key not in records),None)
        if first.get("failure_classification") in NUMERICAL_FAILURES | {"CUDA_ERROR"}:
            second=records.get("lr_0_0002")
            if second is None:return "lr_0_0002"
            if second.get("status") == "STABILITY_VALIDATED":return None
            if second["status"] not in TERMINAL_STATUSES and second["status"]!="STABILITY_VALIDATED":return None
            if second.get("status") == "VALIDATED":
                return next((key for key in ("context_512","ffn_1024","layers_6") if key not in records),None)
            if second.get("failure_classification") in {"FORWARD_ACTIVATION_INSTABILITY","GRADIENT_INSTABILITY","NUMERICAL_INSTABILITY"} and "residual_scale_depth" not in records:return "residual_scale_depth"
        return None

    def stop(self,state:dict,reason:str)->None:
        state["status"]=reason;state["stop_reason"]=reason;state["running_candidate"]=None

    def update_leaderboard(self,state:dict)->list[dict]:
        rows=[]
        for item in state["candidates"].values():
            metrics=item.get("metrics") or {}
            rows.append({
                "candidate_id":item["candidate_id"],"candidate_key":item["candidate_key"],"change":item["change_label"],
                "status":item["status"],"best_val_bpb":metrics.get("best_validation_bpb","N/A"),
                "actual_bpb":metrics.get("actual_bpb","N/A"),"ratio":metrics.get("ratio","N/A"),
                "sha256":metrics.get("sha256_pass","N/A"),"max_activation":metrics.get("max_activation","N/A"),
                "compression_MB_s":metrics.get("compression_MB_s","N/A"),"decompression_MB_s":metrics.get("decompression_MB_s","N/A"),
                "peak_RSS_MB":metrics.get("peak_RSS_MB","N/A"),"vram_bytes":metrics.get("vram_bytes","N/A"),
                "checkpoint_size":metrics.get("checkpoint_size","N/A"),"decision":item.get("decision","REJECT"),"pareto":"N/A",
            })
        eligible=[row for row in rows if all(isinstance(row[field],(int,float)) for field in ("actual_bpb","compression_MB_s","decompression_MB_s","peak_RSS_MB","vram_bytes","checkpoint_size"))]
        for row in eligible:
            dominated=False
            for other in eligible:
                if other is row:continue
                no_worse=(other["actual_bpb"]<=row["actual_bpb"] and other["compression_MB_s"]>=row["compression_MB_s"] and other["decompression_MB_s"]>=row["decompression_MB_s"] and other["peak_RSS_MB"]<=row["peak_RSS_MB"] and other["vram_bytes"]<=row["vram_bytes"] and other["checkpoint_size"]<=row["checkpoint_size"])
                strictly=(other["actual_bpb"]<row["actual_bpb"] or other["compression_MB_s"]>row["compression_MB_s"] or other["decompression_MB_s"]>row["decompression_MB_s"] or other["peak_RSS_MB"]<row["peak_RSS_MB"] or other["vram_bytes"]<row["vram_bytes"] or other["checkpoint_size"]<row["checkpoint_size"])
                if no_worse and strictly:dominated=True;break
            row["pareto"]="DOMINATED" if dominated else "PARETO"
        atomic_json(self.leaderboard_json,rows)
        fields=list(rows[0]) if rows else ["candidate_id","candidate_key","change","status","best_val_bpb","actual_bpb","ratio","sha256","max_activation","compression_MB_s","decompression_MB_s","peak_RSS_MB","vram_bytes","checkpoint_size","decision","pareto"]
        self.leaderboard_csv.parent.mkdir(parents=True,exist_ok=True)
        with self.leaderboard_csv.open("w",newline="",encoding="utf-8") as handle:
            writer=csv.DictWriter(handle,fieldnames=fields);writer.writeheader();writer.writerows(rows)
        self._write_pareto_outputs(rows)
        return rows

    def _write_pareto_outputs(self, rows: list[dict]) -> None:
        numeric = [
            row for row in rows
            if all(isinstance(row.get(field), (int, float)) for field in (
                "actual_bpb", "compression_MB_s", "decompression_MB_s",
                "peak_RSS_MB", "vram_bytes", "checkpoint_size",
            ))
        ]
        summary = {
            "measured_candidates": len(numeric),
            "pareto_candidates": [row["candidate_id"] for row in numeric if row["pareto"] == "PARETO"],
            "current_best_bpb": min(numeric, key=lambda row: row["actual_bpb"])["candidate_id"] if numeric else None,
            "best_compression_speed": max(numeric, key=lambda row: row["compression_MB_s"])["candidate_id"] if numeric else None,
            "best_decompression_speed": max(numeric, key=lambda row: row["decompression_MB_s"])["candidate_id"] if numeric else None,
            "best_peak_rss": min(numeric, key=lambda row: row["peak_RSS_MB"])["candidate_id"] if numeric else None,
            "best_vram": min(numeric, key=lambda row: row["vram_bytes"])["candidate_id"] if numeric else None,
            "smallest_checkpoint": min(numeric, key=lambda row: row["checkpoint_size"])["candidate_id"] if numeric else None,
        }
        plots = self.paths.results / "plots"
        plots.mkdir(parents=True, exist_ok=True)
        atomic_json(plots / "pareto_summary.json", summary)
        if not numeric:
            return
        self._write_scatter_svg(
            numeric, "actual_bpb", "decompression_MB_s",
            "Actual XAIC BPB vs decompression throughput",
            "Actual BPB (lower is better)", "Decompression MB/s (higher is better)",
            plots / "pareto_bpb_vs_decompression.svg",
        )
        self._write_scatter_svg(
            numeric, "actual_bpb", "peak_RSS_MB",
            "Actual XAIC BPB vs peak RSS",
            "Actual BPB (lower is better)", "Peak RSS MB (lower is better)",
            plots / "pareto_bpb_vs_memory.svg",
        )

    @staticmethod
    def _write_scatter_svg(rows: list[dict], x_field: str, y_field: str, title: str,
                           x_label: str, y_label: str, destination: Path) -> None:
        width, height, margin = 720, 460, 70
        xs = [float(row[x_field]) for row in rows]
        ys = [float(row[y_field]) for row in rows]

        def bounds(values: list[float]) -> tuple[float, float]:
            low, high = min(values), max(values)
            padding = max((high - low) * .08, abs(low) * .01, 1e-9)
            return low - padding, high + padding

        x_low, x_high = bounds(xs)
        y_low, y_high = bounds(ys)

        def px(value: float) -> float:
            return margin + (value - x_low) / (x_high - x_low) * (width - 2 * margin)

        def py(value: float) -> float:
            return height - margin - (value - y_low) / (y_high - y_low) * (height - 2 * margin)

        elements = [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
            '<rect width="100%" height="100%" fill="white"/>',
            f'<text x="{width/2}" y="28" text-anchor="middle" font-family="sans-serif" font-size="18">{escape(title)}</text>',
            f'<line x1="{margin}" y1="{height-margin}" x2="{width-margin}" y2="{height-margin}" stroke="#333"/>',
            f'<line x1="{margin}" y1="{margin}" x2="{margin}" y2="{height-margin}" stroke="#333"/>',
            f'<text x="{width/2}" y="{height-18}" text-anchor="middle" font-family="sans-serif" font-size="13">{escape(x_label)}</text>',
            f'<text x="18" y="{height/2}" text-anchor="middle" transform="rotate(-90 18 {height/2})" font-family="sans-serif" font-size="13">{escape(y_label)}</text>',
        ]
        for row in rows:
            x, y = px(float(row[x_field])), py(float(row[y_field]))
            color = "#087f5b" if row.get("pareto") == "PARETO" else "#868e96"
            elements.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="6" fill="{color}"/>')
            elements.append(f'<text x="{x+9:.2f}" y="{y-7:.2f}" font-family="sans-serif" font-size="11">{escape(str(row["candidate_id"]))}</text>')
        elements.append('</svg>')
        destination.write_text("\n".join(elements) + "\n", encoding="utf-8")

    def write_report(self,state:dict)->Path:
        rows=self.update_leaderboard(state);failed=[state["candidates"][candidate_id] for candidate_id in state["failed_candidates"]]
        lines=["# Final model search report","","# Search Summary","",f"Status: {state['status']}",f"Stop reason: {state.get('stop_reason') or 'N/A'}","","# Candidate Table","","| Candidate | Change | Status | Best Val BPB | Actual BPB | Ratio | SHA256 | Max Activation | Comp MB/s | Decomp MB/s | VRAM | Decision |","|---|---|---|---:|---:|---:|---|---:|---:|---:|---:|---|"]
        for row in rows:lines.append("| "+" | ".join(str(row[key]) for key in ("candidate_id","change","status","best_val_bpb","actual_bpb","ratio","sha256","max_activation","compression_MB_s","decompression_MB_s","vram_bytes","decision"))+" |")
        lines += ["","# Failed Candidates",""]
        lines += [f"- {item['candidate_id']}: {item.get('failure_classification','UNKNOWN_ERROR')} — {item.get('failure',{}).get('exception','N/A')}" for item in failed] or ["None recorded."]
        lines += ["","# Stability Analysis","","See each candidate's history and status artifacts; failed candidates are retained.","","# Compression Comparison","","Only measured `actual_bpb` values in the table are eligible for selection.","","# Classical Codec Comparison","","See candidate benchmark artifacts; unavailable codecs are N/A.","","# Pareto Analysis","",f"Pareto candidates: {', '.join(row['candidate_id'] for row in rows if row['pareto']=='PARETO') or 'N/A'}","","# Best Validated Candidate","",state.get("promoted_candidate") or state.get("best_stable_candidate") or "Protected GRU baseline","","# Remaining Limitations","","Unmeasured fields remain N/A. Validation BPB is not treated as artifact BPB.","","# Final Recommendation","",state.get("stop_reason") or "Search remains active; no automatic application-default replacement."]
        path=self.paths.results/"reports"/"final_model_search_report.md";path.parent.mkdir(parents=True,exist_ok=True);path.write_text("\n".join(lines)+"\n",encoding="utf-8");return path


def promotion_outcome(candidate_bpb: float | None, baseline_bpb: float | None, tolerance: float, sha256_pass: bool, stability_pass: bool) -> str:
    if not sha256_pass or not stability_pass:return "REJECT"
    if candidate_bpb is None or baseline_bpb is None:return "INCONCLUSIVE"
    improvement=(baseline_bpb-candidate_bpb)/baseline_bpb
    if improvement>=tolerance:return "PROMOTE"
    if improvement<=-tolerance:return "KEEP_BASELINE"
    return "INCONCLUSIVE"

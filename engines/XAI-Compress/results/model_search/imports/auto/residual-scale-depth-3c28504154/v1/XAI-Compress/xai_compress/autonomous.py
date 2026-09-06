"""Bounded, resumable controller for the declarative neural-lossless search."""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import torch

from .checkpoint import load_checkpoint, save_checkpoint
from .model import ModelConfig
from .model_search import ModelSearchOrchestrator, SearchConfig, atomic_json, canonical_json, sha256_file, utc_now
from .models.registry import build_model
from .telemetry import collection_abs_max, collection_finite_and_abs_max, collection_l2_norm


ACTIVE_KAGGLE = {"RUNNING", "QUEUED", "KernelWorkerStatus.RUNNING", "KernelWorkerStatus.QUEUED"}
STOP_STATES = {
    "SUCCESS", "SUCCESS_BEST_VALIDATED", "SEARCH_BUDGET_EXHAUSTED",
    "NO_SIGNIFICANT_IMPROVEMENT", "INFRASTRUCTURE_BLOCKED", "NO_VALID_CANDIDATE",
    "FIRST_VALIDATED_TRANSFORMER_READY",
}


class ControllerAlreadyRunning(RuntimeError):
    pass


class ControllerLock:
    def __init__(self, path: Path):
        self.path = path
        self.acquired = False

    @staticmethod
    def _alive(pid: int) -> bool:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        except OSError:
            return False
        return True

    def acquire(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists():
            try:
                existing = json.loads(self.path.read_text(encoding="utf-8"))
                if self._alive(int(existing["pid"])):
                    raise ControllerAlreadyRunning(f"controller PID {existing['pid']} already owns {self.path}")
            except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                pass
            stale = self.path.with_name(f"{self.path.name}.stale-{int(time.time())}")
            self.path.replace(stale)
        descriptor = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump({"pid": os.getpid(), "started_at": utc_now()}, handle)
            handle.flush(); os.fsync(handle.fileno())
        self.acquired = True

    def release(self) -> None:
        if self.acquired and self.path.exists():
            try:
                owner = json.loads(self.path.read_text(encoding="utf-8"))
                if int(owner.get("pid", -1)) == os.getpid():
                    self.path.unlink()
            finally:
                self.acquired = False

    def __enter__(self):
        self.acquire(); return self

    def __exit__(self, *_):
        self.release()


class EventLog:
    def __init__(self, path: Path):
        self.path = path

    def append(self, *, candidate: str | None, action: str, reason: str,
               previous_state: Any = None, new_state: Any = None,
               source_hash: Any = None, kernel: str | None = None,
               version: int | None = None, budget_before: Any = None,
               budget_after: Any = None, result: Any = None) -> dict:
        event = {
            "timestamp": utc_now(), "candidate": candidate, "action": action, "reason": reason,
            "previous_state": previous_state, "new_state": new_state, "source_hash": source_hash,
            "kernel": kernel, "version": version, "budget_before": budget_before,
            "budget_after": budget_after, "result": result,
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(canonical_json(event) + "\n")
            handle.flush(); os.fsync(handle.fileno())
        return event


class KaggleBackend:
    """Authenticated Kaggle CLI adapter. Tests supply a fake with this API."""
    def __init__(self, root: Path, config: SearchConfig):
        self.root = root
        self.config = config
        self.kaggle = root / ".venv" / "Scripts" / "kaggle.exe"
        self.python = root / ".venv" / "Scripts" / "python.exe"

    def _run(self, command: list[str], check: bool = True) -> subprocess.CompletedProcess:
        completed = subprocess.run(command, cwd=self.root, text=True, capture_output=True, check=False)
        if check and completed.returncode:
            raise RuntimeError((completed.stdout + "\n" + completed.stderr).strip())
        return completed

    def status(self, kernel: str) -> str:
        output = self._run([str(self.kaggle), "kernels", "status", kernel]).stdout.strip()
        match = re.search(r'"([^"]+)"', output)
        return match.group(1) if match else output

    def download(self, kernel: str, destination: Path) -> None:
        destination.mkdir(parents=True, exist_ok=True)
        self._run([str(self.kaggle), "kernels", "output", kernel, "-p", str(destination)])

    def deploy_source(self) -> dict:
        environment = os.environ.copy()
        environment.setdefault("KAGGLE_USERNAME", self.config.payload["kaggle"]["username"])
        environment.setdefault("KAGGLE_DATASET", self.config.payload["kaggle"].get("source_dataset", "xai-compress-source").split("/")[-1])
        script = self.root / "scripts" / "kaggle" / "update_kaggle.ps1"
        completed = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script),
             "-Message", "Autonomous model-search source snapshot"],
            cwd=self.root, env=environment, text=True, capture_output=True, check=False,
        )
        if completed.returncode:
            raise RuntimeError((completed.stdout + "\n" + completed.stderr).strip())
        manifest = json.loads((self.root / ".kaggle_build" / "source-sha256.json").read_text(encoding="utf-8"))
        return manifest

    def stage(self, candidate: dict, source_hashes: dict) -> tuple[Path, str]:
        slug_key = re.sub(r"[^a-z0-9]+", "-", candidate["candidate_key"].lower()).strip("-")
        slug = f"xai-compress-auto-{slug_key}-{candidate['fingerprint'][:10]}"
        stage = self.root / ".kaggle_autonomous" / candidate["candidate_id"]
        stage.mkdir(parents=True, exist_ok=True)
        payload = {"key": candidate["candidate_key"], "id": candidate["candidate_id"],
                   "config": candidate["resolved_config"], "source_hashes": source_hashes}
        template = (self.root / "scripts" / "kaggle" / "autonomous_kernel_template.py").read_text(encoding="utf-8")
        rendered = template.replace("__XAI_CANDIDATE_JSON__", canonical_json(payload))
        (stage / "run.py").write_text(rendered, encoding="utf-8")
        username = self.config.payload["kaggle"]["username"]
        metadata = {
            "id": f"{username}/{slug}", "title": slug.replace("-", " "), "code_file": "run.py",
            "language": "python", "kernel_type": "script", "is_private": True,
            "enable_gpu": True, "machine_shape": "NvidiaTeslaT4", "enable_internet": False,
            "dataset_sources": [self.config.payload["kaggle"]["source_dataset"], self.config.payload["dataset"]["kaggle_slug"]],
            "competition_sources": [], "kernel_sources": [],
        }
        atomic_json(stage / "kernel-metadata.json", metadata)
        return stage, metadata["id"]

    def submit(self, stage: Path) -> int:
        output = self._run([str(self.kaggle), "kernels", "push", "-p", str(stage)]).stdout
        match = re.search(r"Kernel version\s+(\d+)\s+successfully pushed", output)
        if not match:
            raise RuntimeError(f"cannot determine submitted kernel version: {output}")
        return int(match.group(1))


class AutonomousController:
    def __init__(self, config_path: str | Path, backend: Any | None = None, poll_seconds: int = 45):
        self.config = SearchConfig.load(config_path)
        self.orchestrator = ModelSearchOrchestrator(self.config)
        self.root = self.config.root
        self.backend = backend or KaggleBackend(self.root, self.config)
        self.poll_seconds = max(10, int(poll_seconds))
        self.controller_path = self.config.paths.results / "controller_state.json"
        self.lock = ControllerLock(self.config.paths.results / "controller.lock")
        self.events = EventLog(self.config.paths.results / "events.jsonl")

    def _persist_controller(self, phase: str, candidate: str | None = None, result: Any = None) -> None:
        atomic_json(self.controller_path, {
            "pid": os.getpid(), "phase": phase, "candidate": candidate,
            "updated_at": utc_now(), "result": result,
        })

    @staticmethod
    def _budget(state: dict) -> dict:
        return dict(state["budget"])

    def _preflight(self, candidate: dict) -> dict:
        config = candidate["resolved_config"]
        model_config = ModelConfig(
            embedding_dim=int(config["embedding_dim"]), hidden_dim=int(config["hidden_dim"]),
            num_layers=int(config["num_layers"]), context_length=int(config["context_length"]),
            dropout=float(config["dropout"]), architecture_id=config["architecture"],
            n_heads=int(config["n_heads"]), ff_dim=int(config["ff_dim"]),
            residual_scale=float(config.get("residual_scale", 1.0)),
        )
        model = build_model(model_config)
        optimizer = torch.optim.AdamW(model.parameters(), lr=float(config["lr"]))
        tokens = torch.randint(0, 257, (2, min(16, model_config.context_length)))
        logits, _ = model(tokens)
        loss = logits.float().square().mean(); loss.backward(); optimizer.step()
        finite_parameters, parameter_max = collection_finite_and_abs_max(model.parameters())
        finite_optimizer, optimizer_max = collection_finite_and_abs_max(optimizer.state_dict())
        gradient_norm = collection_l2_norm([p.grad for p in model.parameters() if p.grad is not None])
        checkpoint = Path(candidate["checkpoint_dir"]) / "preflight.pt"
        save_checkpoint(checkpoint, model, optimizer, epoch=0, metrics={"preflight": True})
        loaded, _ = load_checkpoint(checkpoint, "cpu")
        first, _ = loaded.step(256); second, _ = loaded.step(256)
        result = {
            "status": "PASS" if finite_parameters and finite_optimizer and torch.equal(first, second) else "FAIL",
            "finite_parameters": finite_parameters, "finite_optimizer_state": finite_optimizer,
            "parameter_abs_max": parameter_max, "optimizer_abs_max": optimizer_max,
            "gradient_norm": gradient_norm, "deterministic_inference": bool(torch.equal(first, second)),
            "checkpoint_sha256": sha256_file(checkpoint),
        }
        atomic_json(Path(candidate["candidate_dir"]) / "preflight.json", result)
        return result

    def _benchmark(self, state: dict, candidate: dict) -> str:
        output = Path(candidate["candidate_dir"]) / "promotion_benchmark"
        command = [
            str(self.backend.python), str(self.root / "scripts" / "benchmark_v2_promotion.py"),
            "--old-gru", str(self.orchestrator.paths.baseline),
            "--new-v2", str(Path(candidate["checkpoint_dir"]) / "best.pt"),
            "--output", str(output), "--minimum-improvement",
            str(self.config.payload["selection"]["minimum_actual_bpb_improvement_fraction"]),
        ]
        completed = subprocess.run(command, cwd=self.root, check=False)
        if completed.returncode:
            self.orchestrator.record_failure(state, candidate, "BENCHMARK", f"benchmark exit {completed.returncode}")
            return "BENCHMARK_FAILED"
        decision = self.orchestrator.ingest_benchmark(state, candidate, output)
        if state.get("first_validated_transformer"):
            state["status"] = "FIRST_VALIDATED_TRANSFORMER_READY"
            state["stop_reason"] = "FIRST_VALIDATED_TRANSFORMER_READY"
            self.orchestrator.save_state(state)
            return "FIRST_VALIDATED_TRANSFORMER_READY"
        return decision

    def _terminal_import(self, state: dict, candidate: dict, kaggle_status: str) -> str:
        kernel = candidate["kaggle_kernel"]; version = int(candidate["kaggle_version"])
        destination = self.config.paths.results / "imports" / "auto" / candidate["candidate_id"] / f"v{version}"
        download_marker = destination / ".download_complete.json"
        if not download_marker.exists():
            self.backend.download(kernel, destination)
            atomic_json(download_marker, {"kernel": kernel, "version": version, "downloaded_at": utc_now()})
            self.events.append(candidate=candidate["candidate_id"], action="DOWNLOAD", reason=kaggle_status,
                               kernel=kernel, version=version, result=str(destination))
        result_root = destination / "results" / "model_search"
        selection = result_root / "selection.json"
        if not selection.is_file():
            self.orchestrator.infrastructure_failure(state, candidate, "terminal output missing selection.json")
            self.events.append(candidate=candidate["candidate_id"], action="CLASSIFY", reason="OUTPUT_MISSING",
                               kernel=kernel, version=version, result="INFRASTRUCTURE_ERROR")
            return "INFRASTRUCTURE_ERROR"
        ingest_marker = destination / ".ingest_complete.json"
        if not ingest_marker.exists():
            payload = json.loads(selection.read_text(encoding="utf-8"))
            assessment = next((item for item in payload.get("assessments", [])
                               if item.get("candidate_key", candidate["candidate_key"]) == candidate["candidate_key"]), None)
            if assessment is None:
                raise RuntimeError("candidate assessment missing from selection.json")
            source = result_root / candidate["candidate_key"]
            passed = self.orchestrator.ingest_stability_result(state, candidate, source, assessment.get("summary"))
            atomic_json(ingest_marker, {"candidate": candidate["candidate_id"], "ingested_at": utc_now(), "passed": passed})
            self.events.append(candidate=candidate["candidate_id"], action="INGEST", reason=kaggle_status,
                               kernel=kernel, version=version, result={"passed": passed, "status": candidate["status"]})
        if candidate.get("status") == "STABILITY_VALIDATED":
            decision = self._benchmark(state, candidate)
            self.events.append(candidate=candidate["candidate_id"], action="BENCHMARK", reason="MANDATORY_GATES_PASS",
                               result=decision)
            return decision
        return candidate.get("failure_classification", candidate.get("status", "FAILED"))

    def _select_candidate(self, state: dict) -> dict | None:
        retry = next((item for item in state["candidates"].values()
                      if item.get("status") == "INFRASTRUCTURE_RETRY_PENDING"), None)
        if retry:
            return retry
        pending = next((item for item in state["candidates"].values()
                        if item.get("status") == "PENDING"), None)
        if pending:
            return pending
        key = self.orchestrator.next_candidate_key(state)
        return self.orchestrator.register_candidate(state, key) if key else None

    def run_once(self) -> str:
        state = self.orchestrator.initialize()
        self.orchestrator.reactivate_search_if_pending(state)
        if state["status"] in STOP_STATES:
            self._persist_controller("STOPPED", result=state["status"])
            return state["status"]
        running_id = state.get("running_candidate")
        if running_id:
            candidate = state["candidates"][running_id]
            status = self.backend.status(candidate["kaggle_kernel"])
            self._persist_controller("MONITOR", running_id, status)
            self.events.append(candidate=running_id, action="MONITOR", reason="POLL",
                               previous_state=candidate.get("status"), new_state=status,
                               kernel=candidate.get("kaggle_kernel"), version=candidate.get("kaggle_version"), result=status)
            if status in ACTIVE_KAGGLE:
                return "WAITING"
            return self._terminal_import(state, candidate, status)

        candidate = self._select_candidate(state)
        if candidate is None:
            reason = "SEARCH_BUDGET_EXHAUSTED" if self.orchestrator.search_budget_exhausted(state) else "NO_VALID_CANDIDATE"
            state["status"] = reason; state["stop_reason"] = reason
            self.orchestrator.save_state(state)
            self._persist_controller("STOPPED", result=reason)
            return reason
        before = self._budget(state)
        preflight = self._preflight(candidate)
        self.events.append(candidate=candidate["candidate_id"], action="PREFLIGHT", reason="BEFORE_SUBMISSION",
                           previous_state=candidate.get("status"), new_state="PREFLIGHT_PASS" if preflight["status"] == "PASS" else "PREFLIGHT_FAILED",
                           budget_before=before, budget_after=self._budget(state), result=preflight)
        if preflight["status"] != "PASS":
            self.orchestrator.record_failure(state, candidate, "PREFLIGHT", "local preflight failed", preflight)
            return "PREFLIGHT_FAILED"
        source_hashes = self.backend.deploy_source()
        stage, kernel = self.backend.stage(candidate, source_hashes)
        intent = {"kernel": kernel, "source_hashes": source_hashes, "stage": str(stage), "created_at": utc_now()}
        atomic_json(Path(candidate["candidate_dir"]) / "submission_intent.json", intent)
        version = self.backend.submit(stage)
        candidate["source_hashes"] = source_hashes
        candidate["kernel_code_sha256"] = sha256_file(stage / "run.py")
        self.orchestrator.mark_running_external(state, candidate, kernel, version, count_submission=True)
        self.events.append(candidate=candidate["candidate_id"], action="SUBMIT", reason="APPROVED_DECLARATIVE_CANDIDATE",
                           previous_state="PREFLIGHT_PASS", new_state="MULTI_EPOCH_RUNNING",
                           source_hash=source_hashes, kernel=kernel, version=version,
                           budget_before=before, budget_after=self._budget(state), result="SUBMITTED")
        self._persist_controller("MONITOR", candidate["candidate_id"], {"kernel": kernel, "version": version})
        return "SUBMITTED"

    def run(self, once: bool = False) -> str:
        with self.lock:
            self.events.append(candidate=None, action="CONTROLLER_START", reason="USER_AUTHORIZED_AUTO",
                               previous_state=None, new_state="RUNNING", result={"pid": os.getpid(), "once": once})
            while True:
                try:
                    result = self.run_once()
                except Exception as exc:
                    self._persist_controller("ERROR", result={"type": type(exc).__name__, "message": str(exc)})
                    self.events.append(candidate=None, action="CONTROLLER_ERROR", reason=type(exc).__name__, result=str(exc))
                    if once:
                        raise
                    time.sleep(self.poll_seconds)
                    continue
                if once or result in STOP_STATES:
                    return result
                time.sleep(self.poll_seconds)

"""CLI for the controlled XAI-Compress neural-lossless model search."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from xai_compress.model_search import ModelSearchOrchestrator,SearchConfig

DEFAULT_CONFIG=ROOT/"configs"/"model_search_v2.json"


def load(config_path:Path)->tuple[ModelSearchOrchestrator,dict]:
    orchestrator=ModelSearchOrchestrator(SearchConfig.load(config_path));state=orchestrator.initialize();return orchestrator,state


def compact_status(state:dict)->dict:
    return {key:state.get(key) for key in ("status","running_candidate","pending_candidates","completed_candidates","failed_candidates","unresolved_candidates","validated_candidates","promoted_candidate","best_stable_candidate","promotion_blocked","promotion_block_reason","protected_baseline_integrity","budget","stop_reason")}


def main()->None:
    parser=argparse.ArgumentParser();parser.add_argument("command",choices=("start","resume","status","leaderboard","benchmark-best","ingest-diagnostic","register-next","mark-external","verify-baseline","reclassify-candidate-a"));parser.add_argument("--config",type=Path,default=DEFAULT_CONFIG);parser.add_argument("--result",type=Path);parser.add_argument("--candidate");parser.add_argument("--kernel");parser.add_argument("--version",type=int);args=parser.parse_args()
    orchestrator,state=load(args.config)
    if args.command=="verify-baseline":
        print(json.dumps(orchestrator.write_protected_baseline_verification(),indent=2));return
    if args.command=="reclassify-candidate-a":
        candidate=next((item for item in state["candidates"].values() if item["candidate_key"]=="lr_0_0003"),None)
        if not candidate:raise SystemExit("Candidate A is not registered")
        print(json.dumps(orchestrator.supersede_candidate_a_telemetry_failure(state,candidate),indent=2));return
    if args.command=="start":
        candidate=orchestrator.register_candidate(state,"lr_0_0003")
        submitted_manifest=ROOT/".kaggle_build"/"source-sha256.json"
        if submitted_manifest.is_file() and not candidate.get("source_hashes"):
            candidate["source_hashes"]=json.loads(submitted_manifest.read_text(encoding="utf-8"))
            (Path(candidate["candidate_dir"])/"source-sha256.json").write_text(
                json.dumps(candidate["source_hashes"],indent=2)+"\n",encoding="utf-8"
            )
            orchestrator.save_state(state)
        if candidate["status"]=="PENDING":
            kaggle=orchestrator.config.payload["kaggle"]
            orchestrator.mark_running_external(state,candidate,kaggle["current_diagnostic_kernel"],int(kaggle["current_diagnostic_version"]),count_submission=True)
        print(json.dumps(compact_status(state),indent=2));return
    if args.command=="ingest-diagnostic":
        if not args.result:raise SystemExit("--result is required")
        selection=json.loads((args.result/"selection.json").read_text(encoding="utf-8"))
        assessments=selection.get("assessments") or []
        for assessment in assessments:
            lr=float(assessment["learning_rate"]);key="lr_0_0003" if abs(lr-.0003)<1e-12 else "lr_0_0002"
            candidate=orchestrator.register_candidate(state,key)
            source=args.result/f"lr_{str(lr).replace('.','_')}"
            orchestrator.ingest_stability_result(state,candidate,source,assessment.get("summary"))
        print(json.dumps(compact_status(state),indent=2));return
    if args.command=="resume":
        print(json.dumps({**compact_status(state),"next_candidate":orchestrator.next_candidate_key(state)},indent=2));return
    if args.command=="register-next":
        key=orchestrator.next_candidate_key(state)
        if not key:raise SystemExit("No candidate is currently eligible for registration")
        candidate=orchestrator.register_candidate(state,key)
        submitted_manifest=ROOT/".kaggle_build"/"source-sha256.json"
        if submitted_manifest.is_file():
            candidate["source_hashes"]=json.loads(submitted_manifest.read_text(encoding="utf-8"))
            (Path(candidate["candidate_dir"])/"source-sha256.json").write_text(
                json.dumps(candidate["source_hashes"],indent=2)+"\n",encoding="utf-8"
            )
            orchestrator.save_state(state)
        print(json.dumps(candidate,indent=2));return
    if args.command=="mark-external":
        if not args.candidate or not args.kernel or args.version is None:
            raise SystemExit("--candidate, --kernel, and --version are required")
        candidate=orchestrator.register_candidate(state,args.candidate)
        staged_wrappers={"lr_0_0002":ROOT/".kaggle_kernel_model_search_lr_0002"/"run.py"}
        wrapper=staged_wrappers.get(args.candidate)
        if wrapper and wrapper.is_file():
            import hashlib
            candidate["kernel_code_sha256"]=hashlib.sha256(wrapper.read_bytes()).hexdigest()
        orchestrator.mark_running_external(state,candidate,args.kernel,args.version,count_submission=True)
        orchestrator.save_state(state)
        print(json.dumps(compact_status(state),indent=2));return
    if args.command=="status":print(json.dumps(compact_status(state),indent=2));return
    if args.command=="leaderboard":print(json.dumps(orchestrator.update_leaderboard(state),indent=2));return
    candidate_id=state.get("best_stable_candidate")
    if not candidate_id:raise SystemExit("No stability-validated Transformer candidate is available to benchmark")
    candidate=state["candidates"][candidate_id];output=Path(candidate["candidate_dir"])/"promotion_benchmark"
    candidate_checkpoint=Path(candidate["checkpoint_dir"])/"best.pt"
    command=[sys.executable,str(ROOT/"scripts"/"benchmark_v2_promotion.py"),"--old-gru",str(orchestrator.paths.baseline),"--new-v2",str(candidate_checkpoint),"--output",str(output),"--minimum-improvement",str(orchestrator.config.payload["selection"]["minimum_actual_bpb_improvement_fraction"])]
    completed=subprocess.run(command,check=False)
    if completed.returncode:raise SystemExit(completed.returncode)
    orchestrator.ingest_benchmark(state,candidate,output)


if __name__=="__main__":main()

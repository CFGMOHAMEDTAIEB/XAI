"""Measured, paired promotion benchmark for the validated GRU and Transformer V2.

Neural rows use the complete probability -> deterministic quantization -> rANS
-> XAIC path.  Validation BPB is never substituted for artifact BPB.
"""
from __future__ import annotations

import argparse
import bz2
import csv
import gzip
import hashlib
import json
import lzma
import math
import random
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from xai_compress.checkpoint import load_checkpoint
from xai_compress.compression import compress_bytes, decompress_bytes
from xai_compress.entropy.quant import NEURAL_TOTAL, logits_to_cumulative
from xai_compress.format import unpack_container

def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def peak_rss_mb() -> float | None:
    try:
        import psutil
        info = psutil.Process().memory_info()
        return float(getattr(info, "peak_wset", info.rss)) / (1 << 20)
    except (ImportError, OSError):
        return None


def entropy_breakdown(data: bytes, checkpoint: Path) -> tuple[float, float]:
    model, _ = load_checkpoint(checkpoint, "cpu")
    model.eval(); hidden = None; previous = 256
    model_bits = 0.0; quantized_bits = 0.0
    with torch.inference_mode():
        for symbol in data:
            logits, hidden = model.step(previous, hidden)
            log_probs = torch.log_softmax(logits.detach().double(), dim=-1)
            model_bits -= float(log_probs[symbol].item()) / math.log(2)
            cumulative = logits_to_cumulative(logits)
            frequency = cumulative[symbol + 1] - cumulative[symbol]
            quantized_bits -= math.log2(frequency / NEURAL_TOTAL)
            previous = symbol
    denominator = max(1, len(data))
    return model_bits / denominator, quantized_bits / denominator


def encode_classical(method: str, data: bytes) -> bytes:
    if method == "gzip": return gzip.compress(data, compresslevel=9)
    if method == "bzip2": return bz2.compress(data, compresslevel=9)
    if method == "lzma": return lzma.compress(data, preset=6)
    if method == "brotli":
        import brotli
        return brotli.compress(data, quality=6)
    if method == "zstd":
        import zstandard as zstd
        return zstd.ZstdCompressor(level=3).compress(data)
    raise ValueError(method)


def decode_classical(method: str, artifact: bytes) -> bytes:
    if method == "gzip": return gzip.decompress(artifact)
    if method == "bzip2": return bz2.decompress(artifact)
    if method == "lzma": return lzma.decompress(artifact)
    if method == "brotli":
        import brotli
        return brotli.decompress(artifact)
    if method == "zstd":
        import zstandard as zstd
        return zstd.ZstdDecompressor().decompress(artifact)
    raise ValueError(method)


def worker(method: str, source: Path, checkpoint: Path | None) -> dict:
    data = source.read_bytes()
    if method in {"old_gru", "transformer_v2"}:
        if checkpoint is None: raise ValueError("neural method requires checkpoint")
        # Warm model loading and one tiny coding path outside timed regions.
        loaded_model, checkpoint_object = load_checkpoint(checkpoint, "cpu")
        checkpoint_metrics = checkpoint_object.get("metrics") or {}
        start = time.perf_counter()
        artifact = compress_bytes(data, "neural-lossless", checkpoint, device="cpu", coder="rans")
        compression_seconds = time.perf_counter() - start
        start = time.perf_counter()
        reconstructed = decompress_bytes(artifact, checkpoint, device="cpu")
        decompression_seconds = time.perf_counter() - start
        metadata, payload = unpack_container(artifact)
        model_bpb, quantized_bpb = entropy_breakdown(data, checkpoint)
        payload_bpb = 8 * len(payload) / max(1, len(data))
        result = {
            "method": method, "architecture": metadata["model_config"]["architecture_id"],
            "checkpoint_bytes": checkpoint.stat().st_size,
            "parameters": sum(parameter.numel() for parameter in loaded_model.parameters()),
            "validation_bpb": checkpoint_metrics.get("best_validation_bpb", checkpoint_metrics.get("val_bpb_estimate")),
            "model_entropy_bpb": model_bpb, "quantized_ideal_bpb": quantized_bpb,
            "quantization_delta_bpb": quantized_bpb - model_bpb,
            "entropy_coder_overhead_bpb": payload_bpb - quantized_bpb,
            "container_overhead_bpb": 8 * (len(artifact) - len(payload)) / max(1, len(data)),
        }
    elif method == "xai_static":
        start=time.perf_counter();artifact=compress_bytes(data,"static");compression_seconds=time.perf_counter()-start
        start=time.perf_counter();reconstructed=decompress_bytes(artifact);decompression_seconds=time.perf_counter()-start
        result={"method":method,"architecture":"adaptive-arithmetic"}
    else:
        start=time.perf_counter();artifact=encode_classical(method,data);compression_seconds=time.perf_counter()-start
        start=time.perf_counter();reconstructed=decode_classical(method,artifact);decompression_seconds=time.perf_counter()-start
        result={"method":method,"architecture":method}
    passed = digest(data) == digest(reconstructed)
    result.update({
        "file": source.name, "original_bytes": len(data), "compressed_bytes": len(artifact),
        "actual_bpb": 8 * len(artifact) / max(1, len(data)),
        "ratio": len(data) / max(1, len(artifact)),
        "compression_seconds": compression_seconds, "decompression_seconds": decompression_seconds,
        "compression_MB_s": len(data)/(1 << 20)/max(compression_seconds,1e-12),
        "decompression_MB_s": len(data)/(1 << 20)/max(decompression_seconds,1e-12),
        "peak_RSS_MB": peak_rss_mb(), "sha256_pass": passed,
        "original_sha256": digest(data), "reconstructed_sha256": digest(reconstructed),
    })
    if not passed: raise RuntimeError(f"SHA256 round trip failed for {method}: {source}")
    return result


def choose_corpus(root: Path, staging: Path, max_files: int, max_bytes: int) -> list[dict]:
    excluded={".git",".venv","checkpoints","results","target","__pycache__"}
    candidates=[]
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.stat().st_size == 0 or any(part in excluded for part in path.parts): continue
        candidates.append(path)
    if not candidates: raise ValueError(f"no benchmark files in {root}")
    staging.mkdir(parents=True,exist_ok=True); selected=[]; suffixes=set()
    for path in candidates:
        suffix=path.suffix.lower() or "<none>"
        if suffix in suffixes and len(candidates) >= max_files: continue
        data=path.read_bytes()[:max_bytes]
        target=staging/f"sample_{len(selected):02d}{path.suffix.lower()}"
        target.write_bytes(data);suffixes.add(suffix)
        selected.append({"sample":target,"source":path,"bytes":len(data),"sha256":digest(data),"training_overlap":"UNKNOWN"})
        if len(selected)>=max_files:break
    return selected


def bootstrap_ci(differences: list[float], seed=20260830, draws=10000) -> tuple[float,float]:
    if not differences:return math.nan,math.nan
    rng=random.Random(seed);n=len(differences);means=[]
    for _ in range(draws):means.append(sum(differences[rng.randrange(n)] for _ in range(n))/n)
    means.sort();return means[int(.025*draws)],means[min(draws-1,int(.975*draws))]


def main() -> None:
    parser=argparse.ArgumentParser()
    parser.add_argument("--old-gru",type=Path,required=True);parser.add_argument("--new-v2",type=Path,required=True)
    parser.add_argument("--corpus",type=Path,default=ROOT/"data"/"test")
    parser.add_argument("--output",type=Path,default=ROOT/"results"/"model_v2"/"promotion_benchmark")
    parser.add_argument("--max-files",type=int,default=6);parser.add_argument("--max-bytes",type=int,default=4096)
    parser.add_argument("--repetitions",type=int,default=3)
    parser.add_argument("--minimum-improvement",type=float,default=.005)
    parser.add_argument("--worker",action="store_true");parser.add_argument("--method");parser.add_argument("--file",type=Path);parser.add_argument("--checkpoint",type=Path)
    args=parser.parse_args()
    if args.worker:
        print(json.dumps(worker(args.method,args.file,args.checkpoint)));return
    for checkpoint in (args.old_gru,args.new_v2):load_checkpoint(checkpoint,"cpu")
    args.output.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(dir=args.output) as temporary:
        corpus=choose_corpus(args.corpus,Path(temporary),args.max_files,args.max_bytes)
        manifest=[{**{k:(str(v) if isinstance(v,Path) else v) for k,v in item.items() if k!="sample"},"sample":item["sample"].name} for item in corpus]
        (args.output/"corpus_manifest.json").write_text(json.dumps(manifest,indent=2),encoding="utf-8")
        methods=[("old_gru",args.old_gru),("transformer_v2",args.new_v2),("xai_static",None),("gzip",None),("brotli",None),("zstd",None),("bzip2",None),("lzma",None)]
        rows=[]
        for method,checkpoint in methods:
            for item in corpus:
                for repetition in range(1,args.repetitions+1):
                    command=[sys.executable,str(Path(__file__).resolve()),"--old-gru",str(args.old_gru),"--new-v2",str(args.new_v2),"--worker","--method",method,"--file",str(item["sample"])]
                    if checkpoint:command += ["--checkpoint",str(checkpoint)]
                    completed=subprocess.run(command,capture_output=True,text=True,check=False)
                    if completed.returncode:
                        rows.append({"method":method,"file":item["sample"].name,"repetition":repetition,"status":"N/A","error":completed.stderr.strip() or completed.stdout.strip()});break
                    row=json.loads(completed.stdout.splitlines()[-1]);row.update({"repetition":repetition,"status":"PASS"});rows.append(row)
    fields=sorted({key for row in rows for key in row})
    with (args.output/"benchmark_raw.csv").open("w",newline="",encoding="utf-8") as handle:
        writer=csv.DictWriter(handle,fieldnames=fields);writer.writeheader();writer.writerows(rows)
    summaries=[]
    for method in dict.fromkeys(row["method"] for row in rows):
        valid=[row for row in rows if row["method"]==method and row.get("status")=="PASS"]
        if not valid:
            summaries.append({"method":method,"status":"N/A"});continue
        first=[row for row in valid if row["repetition"]==1]
        original=sum(row["original_bytes"] for row in first);compressed=sum(row["compressed_bytes"] for row in first)
        summaries.append({
            "method":method,"status":"PASS","files":len(first),"original_bytes":original,"compressed_bytes":compressed,
            "actual_bpb":8*compressed/max(1,original),"ratio":original/max(1,compressed),
            "compression_MB_s_median":statistics.median(row["compression_MB_s"] for row in valid),
            "decompression_MB_s_median":statistics.median(row["decompression_MB_s"] for row in valid),
            "peak_RSS_MB_max":max((row["peak_RSS_MB"] for row in valid if row.get("peak_RSS_MB") is not None),default=None),
            "model_entropy_bpb":sum(row.get("model_entropy_bpb",0)*row["original_bytes"] for row in first)/max(1,original) if method in {"old_gru","transformer_v2"} else None,
            "parameters":first[0].get("parameters") if first else None,
            "checkpoint_bytes":first[0].get("checkpoint_bytes") if first else None,
            "validation_bpb":first[0].get("validation_bpb") if first else None,
            "quantization_delta_bpb":sum(row.get("quantization_delta_bpb",0)*row["original_bytes"] for row in first)/max(1,original) if method in {"old_gru","transformer_v2"} else None,
            "entropy_coder_overhead_bpb":sum(row.get("entropy_coder_overhead_bpb",0)*row["original_bytes"] for row in first)/max(1,original) if method in {"old_gru","transformer_v2"} else None,
            "container_overhead_bpb":sum(row.get("container_overhead_bpb",0)*row["original_bytes"] for row in first)/max(1,original) if method in {"old_gru","transformer_v2"} else None,
            "sha256_pass":all(row["sha256_pass"] for row in valid),
        })
    with (args.output/"benchmark_summary.csv").open("w",newline="",encoding="utf-8") as handle:
        fields=sorted({key for row in summaries for key in row});writer=csv.DictWriter(handle,fieldnames=fields);writer.writeheader();writer.writerows(summaries)
    old={row["file"]:row["actual_bpb"] for row in rows if row["method"]=="old_gru" and row.get("repetition")==1 and row.get("status")=="PASS"}
    new={row["file"]:row["actual_bpb"] for row in rows if row["method"]=="transformer_v2" and row.get("repetition")==1 and row.get("status")=="PASS"}
    paired=[new[name]-old[name] for name in sorted(set(old)&set(new))];low,high=bootstrap_ci(paired)
    old_summary=next((row for row in summaries if row["method"]=="old_gru" and row["status"]=="PASS"),None)
    new_summary=next((row for row in summaries if row["method"]=="transformer_v2" and row["status"]=="PASS"),None)
    decision="INCONCLUSIVE"
    if old_summary and new_summary:
        relative=(old_summary["actual_bpb"]-new_summary["actual_bpb"])/old_summary["actual_bpb"]
        if high < 0 and relative >= args.minimum_improvement:decision="PROMOTE V2"
        elif low > 0 and relative <= -args.minimum_improvement:decision="KEEP OLD GRU"
    report={"decision":decision,"paired_files":len(paired),"paired_mean_delta_bpb":statistics.mean(paired) if paired else None,"paired_bootstrap_95pct_ci":[low,high],"minimum_material_improvement":args.minimum_improvement,"summaries":summaries}
    (args.output/"promotion_decision.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
    print(json.dumps(report,indent=2))


if __name__=="__main__":main()

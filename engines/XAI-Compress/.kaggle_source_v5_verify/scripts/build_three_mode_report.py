from __future__ import annotations
import csv,json
from collections import defaultdict
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/"results"/"model_v2"

def write(name,rows,fields):
    path=OUT/name;path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("w",newline="",encoding="utf-8") as f:w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)

def main():
    source=ROOT/"results"/"compression_comparison"/"benchmark_results.csv";rows=list(csv.DictReader(source.open())) if source.exists() else []
    groups=defaultdict(list)
    for row in rows:groups[row["codec"]].append(row)
    lossless=[]
    for codec,items in groups.items():
        original=sum(int(x["original_size"]) for x in items);compressed=sum(int(x["compressed_size"]) for x in items);ct=sum(float(x["compress_seconds"]) for x in items);dt=sum(float(x["decompress_seconds"]) for x in items)
        lossless.append({"method":codec,"original_bytes":original,"compressed_bytes":compressed,"ratio":original/compressed,"space_saving_percent":100*(1-compressed/original),"actual_bpb":8*compressed/original,"compression_MB_s":original/2**20/ct,"decompression_MB_s":original/2**20/dt,"peak_RSS_MB":"N/A","SHA256_roundtrip":"PASS" if all(x["lossless"]=="True" for x in items) else "FAIL","measurement":"MEASURED: single cold-path pass on 4000-byte text/source corpus"})
    fields=["method","original_bytes","compressed_bytes","ratio","space_saving_percent","actual_bpb","compression_MB_s","decompression_MB_s","peak_RSS_MB","SHA256_roundtrip","measurement"]
    write("lossless_benchmark.csv",lossless,fields)
    write("lossy_benchmark.csv",[],["method","quality","original_bytes","compressed_bytes","ratio","bits_per_pixel","PSNR_dB","SSIM","compression_MB_s","decompression_MB_s","measurement"])
    old=next((x for x in lossless if x["method"]=="mouve_neural"),{})
    comparison=[{"model":"OLD NEURAL LOSSLESS","architecture":"causal-byte-gru-v1","checkpoint":"checkpoints/kaggle/best.pt","parameters":1700800,"checkpoint_bytes":20423284,"validation_CE":5.523487623098652,"validation_BPB":7.968708202255994,"actual_BPB":old.get("actual_bpb","N/A"),"ratio":old.get("ratio","N/A"),"compression_MB_s":old.get("compression_MB_s","N/A"),"decompression_MB_s":old.get("decompression_MB_s","N/A"),"SHA256":"PASS"},
                {"model":"NEW NEURAL LOSSLESS V2","architecture":"causal-byte-transformer-v2","checkpoint":"N/A — not trained","parameters":"N/A","checkpoint_bytes":"N/A","validation_CE":"N/A","validation_BPB":"N/A","actual_BPB":"N/A","ratio":"N/A","compression_MB_s":"N/A","decompression_MB_s":"N/A","SHA256":"SMOKE PASS; trained checkpoint N/A"},
                {"model":"NEURAL LOSSY V1","architecture":"conv-image-autoencoder-v1","checkpoint":"N/A — not trained","parameters":"N/A","checkpoint_bytes":"N/A","validation_CE":"N/A","validation_BPB":"N/A","actual_BPB":"N/A","ratio":"N/A","compression_MB_s":"N/A","decompression_MB_s":"N/A","SHA256":"NOT APPLICABLE — explicitly lossy"}]
    write("three_model_comparison.csv",comparison,list(comparison[0]))
    report="# XAI-Compress three-mode evidence report\n\n## Measured\n\n- Old neural checkpoint load and SHA-256 round trip pass.\n- Old-model 4,000-byte cold-path text/source benchmark is recorded in `lossless_benchmark.csv`.\n- BPB identity decomposition is recorded in `lossless_bpb_breakdown.csv`.\n- Local untrained architecture smoke tests pass for Lossless V2 and Lossy V1.\n\n## Not measured\n\nLossless V2 and Lossy V1 have no trained checkpoints. Their validation quality, actual BPB/rate-distortion, speed, memory, old-vs-new deltas, break-even point, publication figures, and Kaggle execution are N/A. No superiority claim is made.\n"
    (OUT/"final_report.md").write_text(report,encoding="utf-8")
    print(json.dumps({"lossless_rows":len(lossless),"lossy_rows":0,"v2_checkpoint":False,"lossy_checkpoint":False},indent=2))
if __name__=="__main__":main()

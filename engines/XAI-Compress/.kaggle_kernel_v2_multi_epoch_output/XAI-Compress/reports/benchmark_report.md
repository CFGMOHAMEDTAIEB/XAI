# Benchmark Report

This report is generated from raw measurements. Missing codecs or metrics are reported as unmeasured; no values are synthesized.

## Reproduction

```bash
xcompress benchmark --dataset <held-out-dataset> --output results/benchmark_results.csv
python scripts/generate_report.py
```

## Aggregate results

No valid benchmark rows were found. Run `xcompress benchmark` first.

## Experimental environment

```json
{
  "timestamp_utc": "2026-08-27T16:33:24.151194+00:00",
  "hostname": "DESKTOP-RC6V9R6",
  "os": "Windows-10-10.0.19045-SP0",
  "architecture": "AMD64",
  "cpu": "Intel64 Family 6 Model 142 Stepping 12, GenuineIntel",
  "logical_cpu_count": 8,
  "software": {
    "python": "3.14.7",
    "torch": "2.13.0+cpu",
    "numpy": "2.5.2",
    "zstandard": "0.25.0",
    "brotli": "1.2.0",
    "psutil": "7.2.2"
  },
  "ram_bytes": 25604222976,
  "accelerator": {
    "cuda_available": false,
    "device": "cpu",
    "gpu_count": 0,
    "gpu_name": null,
    "vram_bytes": null,
    "cuda_version": null,
    "cudnn_version": null,
    "torch_version": "2.13.0+cpu",
    "torch_cuda_compiled": false
  },
  "git_commit": "6905954831fdc2ca9a56581cea135ee63392f88b"
}
```

## Interpretation constraints

Ratios include container overhead. All comparisons must use identical input files. Training cost and model storage are separate from compressed payload size and must be disclosed. A result is admissible only when every decoded file is byte-identical.

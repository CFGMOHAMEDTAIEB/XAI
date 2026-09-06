# Experiment Report

This report is intentionally data-driven. Populate `results/experiments.csv` through the experiment runner, then execute `python scripts/generate_report.py`. Unrun experiments are not assigned results.

The canonical experiment schema records identity, UTC timestamp, status, model and dataset versions, parameter count, training configuration, loss, BPB, ratio, throughput, peak RAM/VRAM, serialized configuration, and notes.

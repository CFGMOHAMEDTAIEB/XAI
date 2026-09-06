# Kaggle deployment (Windows / VS Code)

This workflow publishes a clean, private source dataset and runs without GitHub or notebook Internet access.

## Authentication

Revoke any token ever pasted into chat. Authenticate with `.\.venv\Scripts\kaggle.exe auth login` (recommended). Alternatively, generate a fresh token in Kaggle **Settings → API** and store only the token text at `%USERPROFILE%\.kaggle\access_token`, or set `KAGGLE_API_TOKEN` only in the current terminal. Never put credentials in this repository.

Configure the non-secret identifiers:

```powershell
$env:KAGGLE_USERNAME = "your-kaggle-name"
$env:KAGGLE_DATASET = "xai-compress-source"
```

Install the CLI in the project environment if needed:

```powershell
.\.venv\Scripts\python.exe -m pip install kaggle
```

## Deploy

First upload or normal create/update detection:

```powershell
.\scripts\kaggle\deploy.ps1 -Message "Initial Kaggle deployment"
```

Explicit commands:

```powershell
.\scripts\kaggle\upload_kaggle.ps1
.\scripts\kaggle\update_kaggle.ps1 -Message "XAIC v3 streaming improvements"
```

The original source is never deleted. Only `.kaggle_build` is recreated, and local data, checkpoints, logs, environments, caches and generated compression files are excluded.

## Kaggle execution

Create a Kaggle notebook, enable a GPU, and attach both:

1. `<username>/xai-compress-source`
2. The desired public/private training dataset

Upload or open `notebooks/00_kaggle_setup.ipynb`, set `TRAIN_DATASET` to an attached dataset directory (or leave it `None` to list candidates), and execute from top to bottom. Source is copied from read-only `/kaggle/input` to `/kaggle/working/XAI-Compress`; installation uses `pip install -e . --no-deps`.

Set `RESUME_CHECKPOINT` to an attached previous `.pt` checkpoint to resume. Outputs are collected into `/kaggle/working/xai_compress_experiment.zip`. Save a notebook version or download that file before the session ends. A checkpoint can also be uploaded as a private Kaggle Dataset and attached to a later run.

The `RESEARCH` preset permits up to 60 epochs but uses validation early stopping (patience 8), `ReduceLROnPlateau`, a best checkpoint, an every-epoch latest checkpoint, and periodic checkpoints every five epochs. An attached valid `latest.pt`/`.pt` checkpoint is discovered automatically. Training history is written as both CSV and JSON, including loss, BPB, learning rate, throughput, elapsed time, ETA, GPU utilization when available, and VRAM counters.

At completion, `/kaggle/working/export` contains `best.pt`, `latest.pt`, `metrics.csv`, `history.json`, `summary.json`, `benchmark.csv`, and `figures/`. If notebook credentials and the Kaggle CLI are available, the runner publishes `KAGGLE_MODEL_DATASET` (default `mohameddtaieb/xai-compress-trained-model`). Otherwise it preserves all outputs and prints the manual command.

## Download the trained model locally

```powershell
.\scripts\kaggle\download_model.ps1
.\scripts\kaggle\download_model.ps1 -Output checkpoints\kaggle\research_v2
.\scripts\kaggle\sync_model.ps1
```

The downloader authenticates through the local CLI, stages and extracts the latest private model dataset, verifies a non-empty `best.pt` with the project checkpoint loader, prints model metadata, and backs up an existing destination before replacement.

## Optional Rust core

The native PyO3 module accelerates the measured probability-quantization boundary while PyTorch/CUDA remains responsible for training. Build it with `build_rust_windows.bat`; Python automatically falls back to the NumPy implementation when it is absent. Run the parity/performance report with:

```powershell
$env:PYTHONPATH = "."
.\.venv\Scripts\python.exe scripts\benchmark_rust_core.py
```

The report under `results/rust_core_benchmark.json` records measured latency, throughput-derived speedup, peak process RSS, and exact table parity. XAIC coding remains bit-compatible.

## Troubleshooting

- **Could not resolve host github.com:** expected with Internet off; this workflow does not use GitHub.
- **CUDA unavailable:** enable GPU in Notebook options and restart. Training intentionally stops on CPU.
- **Dataset not found:** attach it with **Add Input**, rerun discovery, and set `TRAIN_DATASET` to the displayed path.
- **Read-only `/kaggle/input`:** write only beneath `/kaggle/working`.
- **Missing dependency:** Kaggle must already provide `torch`, `numpy`, and `psutil`; offline mode does not download packages.
- **Checkpoint not found:** check `/kaggle/working/checkpoints` or attach the previous checkpoint dataset.
- **CUDA out of memory:** select `SMOKE`/`BALANCED` or lower the override batch size.
- **Session interrupted:** resume from `best.pt` or `best.latest.pt` after publishing it as a Kaggle output/dataset.

Deployment success, GPU execution and compression performance are separate facts. Local tests validate the tooling; only a completed Kaggle run verifies GPU training and produces real benchmark measurements.

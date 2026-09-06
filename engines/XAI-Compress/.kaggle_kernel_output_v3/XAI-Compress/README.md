# XAI-Compress Ready

A reproducible lossless compression project with two modes:

- **static**: adaptive arithmetic coding, no training required.
- **neural**: a causal GRU predicts probabilities for the next byte; arithmetic coding guarantees exact reconstruction.

The neural model never reconstructs approximately. It only predicts symbol probabilities. The arithmetic coder preserves every byte exactly.

## Requirements

Recommended: Python 3.11 or 3.12. Python 3.14 may work if a compatible PyTorch build is installed.

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# Linux/macOS
source .venv/bin/activate

python -m pip install --upgrade pip
pip install -r requirements.txt
pip install -e .
```

## Run tests

```bash
python -m pytest -q
```

## Static lossless compression

```bash
python -m xai_compress compress input.bin output.xaic --mode static
python -m xai_compress decompress output.xaic restored.bin
python -m xai_compress inspect output.xaic
```

Verify manually:

```bash
# Windows PowerShell
Get-FileHash input.bin -Algorithm SHA256
Get-FileHash restored.bin -Algorithm SHA256
```

## Train the Deep Learning model on your data

Put training files under a directory, for example:

```text
data/train/
  file1.bin
  logs/file2.log
  can/trace1.csv
```

Train:

```bash
python -m xai_compress train data/train checkpoints/gru_v1.pt --epochs 10 --context-length 128 --batch-size 64
```

Use the trained checkpoint:

```bash
python -m xai_compress compress input.bin output_neural.xaic --mode neural --checkpoint checkpoints/gru_v1.pt
python -m xai_compress decompress output_neural.xaic restored.bin --checkpoint checkpoints/gru_v1.pt
```

Neural mode intentionally refuses to run without a checkpoint. The checkpoint fingerprint is stored in the `.xaic` header and verified during decompression.

## Benchmark

```bash
python benchmark.py data/test --checkpoint checkpoints/gru_v1.pt --output benchmark_results.csv
```

If `zstandard` and `brotli` are installed, the benchmark includes them. It always includes gzip, bz2, and lzma from Python's standard library.

## Architecture

```text
previous byte / BOS token
        -> embedding
        -> causal GRU
        -> 256 logits
        -> deterministic integer frequencies
        -> arithmetic coder
        -> .xaic payload
```

Decoder uses only the `.xaic` artifact, the matching checkpoint in neural mode, and previously decoded bytes. Exactness is validated with SHA-256.

## Important limitations

- Neural compression is sequential and CPU-oriented in this first production baseline, so it is slower than classical codecs.
- A trained model may improve compression only on data similar to its training domain.
- Do not claim superiority over ZIP, Zstandard, or Brotli without held-out benchmark results.
- File compression now writes XAIC v3 chunks incrementally and file
  decompression reads and verifies one chunk at a time. Legacy XAIC v1/v2
  artifacts remain readable. Neural decoding is still autoregressive, and the
  Python probability-quantization/rANS boundary remains the main performance
  target for the next native-core pass.


## Large-dataset training (memory bounded)

Your local data is **not included** in the ZIP. Copy it to `data/train/`. The loader reads chunks lazily and caps the sample count and bytes per file.

```bat
python -m xai_compress train data\train checkpoints\gru_v3.pt ^
  --epochs 10 --context-length 256 --batch-size 32 ^
  --stride 256 --max-samples 200000 ^
  --max-bytes-per-file 16777216 ^
  --embedding-dim 128 --hidden-dim 256 --num-layers 2 --dropout 0.1
```

ZIP, 7z, gzip, xz, model checkpoints and XAIC artifacts are excluded from training by default.

## Optional Rust memory-safe core

Install Rust, then run:

```bat
build_rust_windows.bat
```

The training loader automatically uses the Rust `read_block` extension when available and falls back to Python buffered I/O otherwise.

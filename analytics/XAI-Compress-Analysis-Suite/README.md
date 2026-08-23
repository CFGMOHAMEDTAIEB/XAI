# XAI-Compress Benchmark, Interpretation and Visualization Suite

This add-on produces evidence-based benchmarks, charts, tables, and presentation-ready reports for XAI-Compress.

It never fabricates results. Every number comes from executed compression/decompression runs or saved training metrics.

## Copy into the main project

Copy this folder into the root of `XAI-Compress`, or unzip it there so this structure is available:

```text
XAI-Compress/
  xai_compress/
  checkpoints/
  data/
  XAI-Compress-Analysis-Suite/
```

Run all commands from the main `XAI-Compress` root.

## Install analysis dependencies

```bat
python -m pip install -r XAI-Compress-Analysis-Suite\requirements-analysis.txt
```

## Recommended data split

```text
data/
  train/       used only to train the model
  validation/  used for model selection
  test/        held-out files used only for the final benchmark
```

Never benchmark on a file used for training.

## 1. Inspect training

```bat
python XAI-Compress-Analysis-Suite\analyze_training.py ^
  --metrics checkpoints\gru_v3.metrics.csv ^
  --output-dir XAI-Compress-Analysis-Suite\outputs
```

Outputs:
- training and validation cross-entropy chart
- estimated validation bits-per-byte chart
- learning-rate chart
- best-epoch summary JSON

## 2. Run the full compression benchmark

Static only:

```bat
python XAI-Compress-Analysis-Suite\run_benchmark.py ^
  --data-dir data\test ^
  --output XAI-Compress-Analysis-Suite\outputs\tables\benchmark_results.csv
```

Static plus neural:

```bat
python XAI-Compress-Analysis-Suite\run_benchmark.py ^
  --data-dir data\test ^
  --checkpoint checkpoints\gru_v3.pt ^
  --output XAI-Compress-Analysis-Suite\outputs\tables\benchmark_results.csv
```

The benchmark compares:
- XAI-Compress static
- XAI-Compress neural when a checkpoint is supplied
- gzip
- bz2
- LZMA
- Zstandard when installed
- Brotli when installed

For every file and codec it records total compressed size, ratio, saving, bits per byte, times, throughput, memory delta, and lossless SHA-256 status.

## 3. Generate charts and summary tables

```bat
python XAI-Compress-Analysis-Suite\visualize_results.py ^
  --input XAI-Compress-Analysis-Suite\outputs\tables\benchmark_results.csv ^
  --output-dir XAI-Compress-Analysis-Suite\outputs
```

## 4. Build a presentation-ready report

```bat
python XAI-Compress-Analysis-Suite\generate_report.py ^
  --benchmark XAI-Compress-Analysis-Suite\outputs\tables\benchmark_results.csv ^
  --training-summary XAI-Compress-Analysis-Suite\outputs\tables\training_summary.json ^
  --output XAI-Compress-Analysis-Suite\outputs\reports\XAI_COMPRESS_REPORT.md
```

## 5. Run everything with one command

```bat
run_analysis_windows.bat data\test checkpoints\gru_v3.pt checkpoints\gru_v3.metrics.csv
```

For static-only analysis:

```bat
run_analysis_windows.bat data\test NONE checkpoints\gru_v3.metrics.csv
```

## Presentation material

Read:
- `docs/PRESENTATION_GUIDE.md`
- `docs/METRICS_EXPLAINED.md`
- generated `outputs/reports/XAI_COMPRESS_REPORT.md`

## Scientific rules

- Lossless means SHA-256 equality, not low MSE.
- Do not rank a codec if any tested reconstruction fails.
- Include the `.xaic` header and metadata in compressed size.
- Test files must be held out from training.
- Report median and standard deviation, not only the mean.
- A neural model is better only if held-out results improve a declared objective.

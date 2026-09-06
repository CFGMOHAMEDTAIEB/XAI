"""Create the reproducible notebook sequence without embedding measured claims."""
from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
NOTEBOOKS = ROOT / "notebooks"

SPECS = [
    ("01_project_introduction", "Project Introduction", "Define lossless neural compression, the research hypothesis, architecture, trade-offs, and limitations.", "from xai_compress.utils.device import detect_device\nprint('XAI-Compress: causal probabilities -> entropy coder -> exact bytes')\nprint('Device:', detect_device().as_dict())"),
    ("02_dataset_analysis", "Dataset Analysis", "Measure file counts, sizes, types, entropy, byte frequencies, duplicates, and file-level splits.", "from pathlib import Path\nfrom xai_compress.datasets.pipeline import dataset_report\nDATASET = Path('../data/train')\nreport = dataset_report(DATASET) if DATASET.exists() else {'status': 'dataset not installed'}\nreport"),
    ("03_data_preprocessing", "Data Preprocessing", "Audit validation, content-hash deduplication, filtering, chunking, byte representation, and lazy batching.", "from pathlib import Path\nfrom xai_compress.datasets.pipeline import discover_files, dedupe_paths\nroot = Path('../data/train')\nfiles = discover_files(root) if root.exists() else []\n{'discovered': len(files), 'unique': len(dedupe_paths(files)) if files else 0}"),
    ("04_entropy_analysis", "Information Theory and Entropy", "Compare marginal entropy, model cross entropy, and measured artifact BPB without conflating them.", "from xai_compress.analyzer import byte_entropy\nsamples = {'repetitive': b'A'*4096, 'uniform': bytes(range(256))*16}\n{k: byte_entropy(v) for k,v in samples.items()}"),
    ("05_baseline_model", "Baseline Model", "Characterize the causal GRU baseline: parameters, context, loss, BPB, speed, and memory.", "from xai_compress.model import CausalByteGRU, ModelConfig\nm = CausalByteGRU(ModelConfig())\n{'architecture': m.config.architecture_id, 'parameters': sum(p.numel() for p in m.parameters()), 'config': m.config.__dict__}"),
    ("06_model_architecture", "Improved Architecture", "Explain the byte Transformer, KV cache, deterministic probability quantization, rANS, and hybrid routing.", "from xai_compress.models.registry import build_model\nfrom xai_compress.models.transformer import preset_config\nfor name in ('tiny','small','balanced','ultra'):\n m=build_model(preset_config(name)); print(name, sum(p.numel() for p in m.parameters()))"),
    ("07_training_process", "Training Process", "Load real training metrics and visualize training/validation loss, BPB, throughput, LR, gradients, and VRAM.", "import csv\nfrom pathlib import Path\np=Path('../results/experiments.csv')\nrows=list(csv.DictReader(p.open(encoding='utf-8'))) if p.exists() else []\nprint(f'{len(rows)} recorded experiments; blank metrics are not measured')"),
    ("08_training_evolution", "Training and Model Evolution", "Show measured progression in BPB, ratio, throughput, parameters, loss, and memory across experiments.", "import pandas as pd\nfrom pathlib import Path\np=Path('../results/experiments.csv')\ndf=pd.read_csv(p) if p.exists() else pd.DataFrame()\ndf"),
    ("09_model_comparison", "Model Comparison", "Compare only completed experiments on parameter count, BPB, ratio, speed, and VRAM.", "import pandas as pd\ndf=pd.read_csv('../results/experiments.csv')\ncols=['experiment_id','model','parameters','bpb','compression_ratio','compression_mbs','decompression_mbs','peak_vram_bytes']\ndf[cols] if len(df) else 'No measured experiments yet'"),
    ("10_compression_comparison", "Classical Compressor Comparison", "Compare identical held-out files across available codecs; explicitly show missing 7-Zip or WinRAR measurements.", "import pandas as pd\nfrom pathlib import Path\np=Path('../results/benchmark_results.csv')\ndf=pd.read_csv(p) if p.exists() else pd.DataFrame()\nprint('Run xcompress benchmark to populate raw measurements') if df.empty else df.groupby('codec').agg({'original_size':'sum','compressed_size':'sum'})"),
    ("11_speed_benchmark", "Speed Benchmark", "Measure warm-up, startup latency, and CPU/GPU throughput across practical file sizes.", "SIZES=[1<<20,10<<20,100<<20,1<<30,10<<30]\nprint('Planned byte sizes:', SIZES)\nprint('Large cases run only when storage and time budgets permit.')"),
    ("12_memory_gpu_benchmark", "Hardware and Memory Benchmark", "Capture CPU, RAM, disk I/O, GPU utilization, VRAM, transfers, and throughput over time.", "from xai_compress.research import machine_manifest\nmachine_manifest()"),
    ("13_ablation_study", "Ablation Study", "Test architecture, context, hybrid selector, coder, checkpoint, mixed precision, and model scale one factor at a time.", "ABLATIONS=['full','gru_only','no_hybrid','arithmetic','rans','context_64','context_256','no_amp']\nprint('Required registered runs:', ABLATIONS)"),
    ("14_error_analysis", "Error Analysis", "Identify files and categories where XAI loses, including high-entropy and already-compressed inputs.", "import pandas as pd\nfrom pathlib import Path\np=Path('../results/benchmark_results.csv')\ndf=pd.read_csv(p) if p.exists() else pd.DataFrame()\nprint('No benchmark evidence yet') if df.empty else df.sort_values('bpb', ascending=False).head(20)"),
    ("15_final_results", "Final Results", "Produce the executive table directly from verified benchmark records and highlight per-metric winners.", "import json\nfrom pathlib import Path\np=Path('../results/benchmark_summary.json')\njson.loads(p.read_text()) if p.exists() else 'Run scripts/generate_report.py after benchmarking'"),
    ("16_complete_pipeline", "Complete End-to-End Pipeline", "Reproduce dataset audit, training, validation, compression, exact decompression, benchmarking, visualization, and reporting.", "print('1 audit dataset -> 2 train -> 3 validate -> 4 benchmark -> 5 generate report')\nprint('Correctness gate: restored_bytes == original_bytes for every admitted row')"),
]


def markdown(text: str):
    return {"cell_type": "markdown", "metadata": {}, "source": [line + "\n" for line in text.splitlines()]}


def code(text: str):
    return {"cell_type": "code", "execution_count": None, "metadata": {}, "outputs": [], "source": [line + "\n" for line in text.splitlines()]}


def make_notebook(title: str, purpose: str, source: str):
    intro = f"# {title}\n\n{purpose}\n\n**Evidence rule:** every numeric performance claim in this notebook must originate in a versioned raw result file. Missing data remains unmeasured."
    workflow = "## Reproduction\n\nRun from the repository environment. Record the Git commit, dataset manifest, checkpoint fingerprint, configuration, machine manifest, and software versions before interpreting results."
    interpretation = "## Interpretation\n\nSeparate artifact size, model storage, training cost, compression throughput, decompression throughput, peak memory, and hardware requirements. Reject any row that fails byte-for-byte verification."
    return {
        "cells": [markdown(intro), markdown(workflow), code(source), markdown(interpretation)],
        "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"}, "language_info": {"name": "python", "version": "3.10"}},
        "nbformat": 4,
        "nbformat_minor": 5,
    }


def main():
    NOTEBOOKS.mkdir(parents=True, exist_ok=True)
    for stem, title, purpose, source in SPECS:
        path = NOTEBOOKS / f"{stem}.ipynb"
        path.write_text(json.dumps(make_notebook(title, purpose, source), indent=1), encoding="utf-8")
        print(path.name)


if __name__ == "__main__":
    main()

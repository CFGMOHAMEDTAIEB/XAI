from __future__ import annotations
import argparse, json
from pathlib import Path
import pandas as pd


def money(value, digits=3):
    return 'N/A' if pd.isna(value) else f'{value:.{digits}f}'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--benchmark', required=True)
    parser.add_argument('--training-summary')
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    df = pd.read_csv(args.benchmark)
    df['is_lossless'] = df['lossless'].astype(str).str.lower().eq('true')
    valid = df[df['is_lossless'] & df['error'].fillna('').eq('')].copy()
    for col in ['bits_per_byte','space_saving_percent','compress_mib_per_second','decompress_mib_per_second','compression_ratio']:
        valid[col] = pd.to_numeric(valid[col], errors='coerce')
    summary = valid.groupby('codec').agg(
        files=('file','count'), mean_bpb=('bits_per_byte','mean'), median_bpb=('bits_per_byte','median'),
        std_bpb=('bits_per_byte','std'), mean_saving=('space_saving_percent','mean'),
        mean_ratio=('compression_ratio','mean'), compress_speed=('compress_mib_per_second','mean'),
        decompress_speed=('decompress_mib_per_second','mean')).reset_index().sort_values('mean_bpb')
    failures = df[~df['is_lossless'] | ~df['error'].fillna('').eq('')]
    training = None
    if args.training_summary and Path(args.training_summary).is_file():
        training = json.loads(Path(args.training_summary).read_text(encoding='utf-8'))
    lines = ['# XAI-Compress Experimental Report', '',
             '## Executive Summary', '',
             f'- Test files evaluated: **{df["file"].nunique()}**',
             f'- Codec executions: **{len(df)}**',
             f'- Failed or non-lossless executions: **{len(failures)}**',
             '- Ranking below includes only successful byte-identical reconstructions.', '']
    if not summary.empty:
        winner = summary.iloc[0]
        lines += [f'- Best mean compression efficiency: **{winner.codec}**, with **{money(winner.mean_bpb)} bits per byte**.', '']
    if training:
        lines += ['## Training Interpretation', '',
                  f'- Epochs completed: **{training["epochs_completed"]}**',
                  f'- Best epoch: **{training["best_epoch"]}**',
                  f'- Best validation cross-entropy: **{training["best_validation_cross_entropy"]:.4f} nats/byte**',
                  f'- Estimated validation BPB at best epoch: **{training["best_validation_bpb_estimate"]:.4f}**',
                  f'- Final generalization gap: **{training["generalization_gap_final"]:.4f}**', '']
    lines += ['## Lossless Codec Ranking', '',
              '| Rank | Codec | Mean BPB ↓ | Median BPB ↓ | Std BPB | Mean Saving % ↑ | Mean Ratio ↑ | Compress MiB/s ↑ | Decompress MiB/s ↑ |',
              '|---:|---|---:|---:|---:|---:|---:|---:|---:|']
    for rank, row in enumerate(summary.itertuples(index=False), 1):
        lines.append(f'| {rank} | {row.codec} | {money(row.mean_bpb)} | {money(row.median_bpb)} | {money(row.std_bpb)} | {money(row.mean_saving,2)} | {money(row.mean_ratio)} | {money(row.compress_speed)} | {money(row.decompress_speed)} |')
    lines += ['', '## What the Model Does', '',
              '1. Reads previous bytes as causal context.',
              '2. Uses an embedding and GRU to predict logits for all 256 possible next-byte values.',
              '3. Converts logits to deterministic integer frequency tables.',
              '4. Uses arithmetic coding to create a reversible compressed bitstream.',
              '5. Uses the same checkpoint and previously decoded bytes during decompression.',
              '6. Verifies exact reconstruction using SHA-256.', '',
              '## How to Interpret the Charts', '',
              '- **Lower BPB is better:** fewer encoded bits are needed per original byte.',
              '- **Higher space saving is better:** negative values indicate expansion.',
              '- **Higher throughput is better:** more MiB are processed each second.',
              '- **Training/validation loss:** both should decrease; a growing gap can indicate overfitting.',
              '- **Time versus BPB:** shows the trade-off between compression efficiency and computation cost.', '',
              '## Scientific Limitations', '',
              '- Results are valid only for the held-out files used by this execution.',
              '- Neural compression may be slower because decoding is sequential.',
              '- Already-compressed data may expand and should be handled by an adaptive selector.',
              '- Model checkpoint size is not included in each artifact because the same deployed model can decode many files.',
              '- Superiority over standard codecs must not be claimed unless held-out results demonstrate it.', '']
    if len(failures):
        lines += ['## Failed Executions', '']
        for row in failures.itertuples(index=False):
            lines.append(f'- `{row.file_name}` with `{row.codec}`: {row.error or "lossless check failed"}')
        lines.append('')
    lines += ['## Generated Evidence', '',
              '- `charts/training_loss.png`', '- `charts/validation_bpb.png`', '- `charts/mean_bpb.png`',
              '- `charts/mean_space_saving.png`', '- `charts/compression_throughput.png`',
              '- `charts/decompression_throughput.png`', '- `charts/time_vs_bpb.png`',
              '- `charts/category_bpb.png`', '- `tables/codec_summary.csv`', '- `tables/category_summary.csv`', '']
    output = Path(args.output); output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text('\n'.join(lines), encoding='utf-8')
    print({'report': str(output), 'valid_rows': len(valid), 'failed_rows': len(failures)})

if __name__ == '__main__':
    main()

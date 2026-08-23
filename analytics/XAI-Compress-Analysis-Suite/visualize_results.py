from __future__ import annotations
import argparse
from pathlib import Path
import pandas as pd
import matplotlib.pyplot as plt


def bar(frame, value, title, ylabel, output, ascending=True):
    ordered = frame.sort_values(value, ascending=ascending)
    plt.figure(figsize=(10, 5.5))
    plt.bar(ordered['codec'], ordered[value])
    plt.title(title); plt.xlabel('Codec'); plt.ylabel(ylabel); plt.xticks(rotation=25, ha='right'); plt.grid(axis='y', alpha=0.3)
    plt.tight_layout(); plt.savefig(output, dpi=180); plt.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', required=True)
    parser.add_argument('--output-dir', required=True)
    args = parser.parse_args()
    df = pd.read_csv(args.input)
    output = Path(args.output_dir); charts = output/'charts'; tables = output/'tables'
    charts.mkdir(parents=True, exist_ok=True); tables.mkdir(parents=True, exist_ok=True)
    valid = df[df['lossless'].astype(str).str.lower().eq('true') & df['error'].fillna('').eq('')].copy()
    if valid.empty:
        raise SystemExit('No valid lossless rows to visualize')
    numeric = ['compressed_size_total','compression_ratio','space_saving_percent','bits_per_byte','compress_seconds','decompress_seconds','compress_mib_per_second','decompress_mib_per_second']
    for col in numeric: valid[col] = pd.to_numeric(valid[col], errors='coerce')
    summary = valid.groupby('codec')[numeric].agg(['mean','median','std','min','max']).reset_index()
    summary.columns = ['codec' if a == 'codec' else f'{a}_{b}' for a,b in summary.columns]
    summary.to_csv(tables/'codec_summary.csv', index=False)
    category = valid.groupby(['category','codec'])[['bits_per_byte','space_saving_percent','compress_seconds','decompress_seconds']].mean().reset_index()
    category.to_csv(tables/'category_summary.csv', index=False)
    lossless_status = df.groupby('codec')['lossless'].apply(lambda s: s.astype(str).str.lower().eq('true').mean()*100).reset_index(name='lossless_success_percent')
    lossless_status.to_csv(tables/'lossless_status.csv', index=False)
    compact = valid.groupby('codec')[numeric].mean().reset_index()
    bar(compact, 'bits_per_byte', 'Mean Bits per Byte, Lower Is Better', 'Bits per Byte', charts/'mean_bpb.png', True)
    bar(compact, 'space_saving_percent', 'Mean Space Saving, Higher Is Better', 'Space Saving (%)', charts/'mean_space_saving.png', False)
    bar(compact, 'compress_mib_per_second', 'Compression Throughput, Higher Is Better', 'MiB/s', charts/'compression_throughput.png', False)
    bar(compact, 'decompress_mib_per_second', 'Decompression Throughput, Higher Is Better', 'MiB/s', charts/'decompression_throughput.png', False)
    plt.figure(figsize=(9, 6))
    for codec, group in valid.groupby('codec'):
        plt.scatter(group['compress_seconds'], group['bits_per_byte'], label=codec, alpha=0.75)
    plt.xlabel('Compression Time (seconds)'); plt.ylabel('Bits per Byte'); plt.title('Compression Time vs Compression Efficiency'); plt.legend(); plt.grid(True, alpha=0.3)
    plt.tight_layout(); plt.savefig(charts/'time_vs_bpb.png', dpi=180); plt.close()
    pivot = category.pivot(index='category', columns='codec', values='bits_per_byte')
    pivot.plot(kind='bar', figsize=(11, 6)); plt.ylabel('Mean Bits per Byte'); plt.title('Compression Efficiency by File Category'); plt.xticks(rotation=25, ha='right'); plt.grid(axis='y', alpha=0.3)
    plt.tight_layout(); plt.savefig(charts/'category_bpb.png', dpi=180); plt.close()
    print({'valid_rows': len(valid), 'charts': str(charts), 'tables': str(tables)})

if __name__ == '__main__':
    main()

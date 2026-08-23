from __future__ import annotations
import argparse, json
from pathlib import Path
import pandas as pd
import matplotlib.pyplot as plt


def save_line(df, columns, title, ylabel, output):
    plt.figure(figsize=(9, 5))
    for column in columns:
        if column in df.columns:
            plt.plot(df['epoch'], df[column], marker='o', label=column.replace('_', ' ').title())
    plt.xlabel('Epoch'); plt.ylabel(ylabel); plt.title(title); plt.legend(); plt.grid(True, alpha=0.3)
    plt.tight_layout(); plt.savefig(output, dpi=180); plt.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--metrics', required=True)
    parser.add_argument('--output-dir', required=True)
    args = parser.parse_args()
    df = pd.read_csv(args.metrics)
    required = {'epoch', 'train_cross_entropy', 'val_cross_entropy', 'val_bpb_estimate'}
    missing = required - set(df.columns)
    if missing:
        raise SystemExit(f'Missing training columns: {sorted(missing)}')
    output = Path(args.output_dir); charts = output/'charts'; tables = output/'tables'
    charts.mkdir(parents=True, exist_ok=True); tables.mkdir(parents=True, exist_ok=True)
    save_line(df, ['train_cross_entropy', 'val_cross_entropy'], 'Training and Validation Cross-Entropy', 'Cross-Entropy (nats/byte)', charts/'training_loss.png')
    save_line(df, ['val_bpb_estimate'], 'Estimated Validation Bits per Byte', 'Estimated BPB', charts/'validation_bpb.png')
    if 'learning_rate' in df.columns:
        save_line(df, ['learning_rate'], 'Learning-Rate Schedule', 'Learning Rate', charts/'learning_rate.png')
    best_index = df['val_cross_entropy'].idxmin(); best = df.loc[best_index].to_dict()
    summary = {
        'epochs_completed': int(df['epoch'].max()),
        'best_epoch': int(best['epoch']),
        'best_validation_cross_entropy': float(best['val_cross_entropy']),
        'best_validation_bpb_estimate': float(best['val_bpb_estimate']),
        'final_training_cross_entropy': float(df.iloc[-1]['train_cross_entropy']),
        'final_validation_cross_entropy': float(df.iloc[-1]['val_cross_entropy']),
        'generalization_gap_final': float(df.iloc[-1]['val_cross_entropy'] - df.iloc[-1]['train_cross_entropy']),
    }
    (tables/'training_summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    print(summary)

if __name__ == '__main__':
    main()

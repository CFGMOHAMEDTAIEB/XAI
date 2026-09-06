"""Print a compact summary from the latest Kaggle kernel log."""
from __future__ import annotations

import argparse
import json

from kaggle.api.kaggle_api_extended import KaggleApi


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("kernel")
    args = parser.parse_args()
    api = KaggleApi()
    api.authenticate()
    lines = api.kernels_logs(args.kernel).splitlines()
    interesting = [
        line for line in lines
        if line.startswith(("ACTIVATION THRESHOLD", "FIRST NON-FINITE EVENT", "FULL-EPOCH STABILITY GATE"))
    ]
    activations = [line for line in lines if line.startswith("ACTIVATION {")]
    if activations:
        payload = json.loads(activations[-1][len("ACTIVATION "):])
        print(json.dumps({key: payload.get(key) for key in (
            "step", "samples", "loss", "scale", "grad_norm", "activation_max"
        )}))
    for line in interesting[-10:]:
        print(line)


if __name__ == "__main__":
    main()

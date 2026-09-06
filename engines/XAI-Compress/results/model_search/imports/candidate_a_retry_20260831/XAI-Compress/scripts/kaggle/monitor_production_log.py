"""Stream only numerical gates and lifecycle events from production logs."""
from __future__ import annotations

import argparse
import ast
import json
import sys
import time

import requests
from kaggle.api.kaggle_api_extended import KaggleApi


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    parser = argparse.ArgumentParser()
    parser.add_argument("kernel")
    args = parser.parse_args()
    api = KaggleApi()
    api.authenticate()
    seen = 0
    while True:
        try:
            for index, event in enumerate(api.kernels_logs_stream(args.kernel)):
                if index < seen:
                    continue
                seen = index + 1
                for line in (event.get("data") or "").splitlines():
                    if line.startswith("{'epoch':"):
                        row = ast.literal_eval(line)
                        print("EPOCH", json.dumps(row), flush=True)
                    elif line.startswith((
                        "PRODUCTION SOURCE HASHES", "SMOKE TEST", "DETERMINISTIC INFERENCE",
                        "LOSSLESS SHA256", "NO VALID CHECKPOINT", "Valid attached recovery checkpoint",
                        "FIRST NON-FINITE STAGE", "Training, lossless validation",
                        "Published model dataset", "Kaggle credentials unavailable",
                        "Application model", "Export:", "Traceback", "RuntimeError",
                        "FloatingPointError", "NumericalDebugError",
                    )):
                        print(line, flush=True)
            return
        except (requests.exceptions.ChunkedEncodingError, requests.exceptions.ConnectionError):
            time.sleep(1)


if __name__ == "__main__":
    main()

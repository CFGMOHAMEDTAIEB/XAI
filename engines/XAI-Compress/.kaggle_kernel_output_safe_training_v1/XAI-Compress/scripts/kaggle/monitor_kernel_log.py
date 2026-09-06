"""Stream a compact subset of a Kaggle kernel's live log."""
from __future__ import annotations

import argparse
import json
import time

from kaggle.api.kaggle_api_extended import KaggleApi
import requests


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("kernel")
    args = parser.parse_args()
    api = KaggleApi()
    api.authenticate()
    last_reported = 0
    seen = 0
    while True:
        try:
            for index, event in enumerate(api.kernels_logs_stream(args.kernel)):
                if index < seen:
                    continue
                seen = index + 1
                for line in (event.get("data") or "").splitlines():
                    if line.startswith("RUN FULL-EPOCH FIX TEST"):
                        last_reported = 0
                        print(line, flush=True)
                    elif line.startswith("ACTIVATION {"):
                        payload = json.loads(line[len("ACTIVATION "):])
                        step = int(payload.get("step") or 0)
                        if step >= last_reported + 1000:
                            last_reported = step
                            print("PROGRESS", json.dumps({key: payload.get(key) for key in (
                                "step", "samples", "loss", "scale", "grad_norm", "activation_max"
                            )}), flush=True)
                    elif line.startswith(("SOURCE HASHES", "ACTIVATION THRESHOLD",
                                          "FIRST NON-FINITE EVENT", "FULL-EPOCH STABILITY GATE",
                                          "FIX ASSESSMENT", "VERSION 6 PRODUCTION")):
                        print(line, flush=True)
            return
        except (requests.exceptions.ChunkedEncodingError, requests.exceptions.ConnectionError):
            time.sleep(1)


if __name__ == "__main__":
    main()

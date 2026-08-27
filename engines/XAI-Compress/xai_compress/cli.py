from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from .benchmarks.suite import run_suite
from .checkpoint import load_checkpoint
from .compression import compress_file, decompress_file
from .format import unpack_container
from .utils.device import detect_device
from .utils.metrics import bits_per_byte, compression_ratio, throughput_mbs


def _print_stats(title: str, original: int, compressed: int, ctime: float, dtime: float | None = None) -> None:
    print(title)
    print(f"Input size       : {original / (1024 ** 2):.4f} MB")
    print(f"Compressed size  : {compressed / (1024 ** 2):.4f} MB")
    print(f"Ratio            : {compression_ratio(original, compressed):.3f}x")
    print(f"Bits/byte        : {bits_per_byte(compressed, original):.4f}")
    print(f"Compression      : {throughput_mbs(original, ctime):.2f} MB/s")
    if dtime is not None:
        print(f"Decompression    : {throughput_mbs(original, dtime):.2f} MB/s")


def main(argv=None):
    parser = argparse.ArgumentParser(prog="xcompress")
    sub = parser.add_subparsers(dest="command", required=True)

    compress = sub.add_parser("compress")
    compress.add_argument("input")
    compress.add_argument("output")
    compress.add_argument("--mode", choices=["static", "neural", "hybrid", "auto", "zlib"], default="static")
    compress.add_argument("--checkpoint")
    compress.add_argument("--model", help="unused unless training; for compress, use --checkpoint")
    compress.add_argument("--chunk-size", type=int, default=65536)
    compress.add_argument("--coder", choices=["arithmetic", "rans"], default="arithmetic")
    compress.add_argument("--device")
    compress.add_argument("--overwrite", action="store_true")

    decompress = sub.add_parser("decompress")
    decompress.add_argument("input")
    decompress.add_argument("output")
    decompress.add_argument("--checkpoint")
    decompress.add_argument("--device")
    decompress.add_argument("--overwrite", action="store_true")
    decompress.add_argument("--max-output-size", type=int, default=8 << 30)

    inspect = sub.add_parser("inspect")
    inspect.add_argument("input")

    train = sub.add_parser("train")
    train.add_argument("data_dir", nargs="?")
    train.add_argument("output", nargs="?")
    train.add_argument("--dataset")
    train.add_argument("--output-checkpoint")
    train.add_argument("--epochs", type=int, default=10)
    train.add_argument("--batch-size", type=int, default=64)
    train.add_argument("--lr", type=float, default=1e-3)
    train.add_argument("--context-length", type=int, default=128)
    train.add_argument("--stride", type=int, default=128)
    train.add_argument("--max-samples", type=int, default=200_000)
    train.add_argument("--max-bytes-per-file", type=int, default=16 * 1024 * 1024)
    train.add_argument("--num-workers", type=int, default=0)
    train.add_argument("--embedding-dim", type=int, default=64)
    train.add_argument("--hidden-dim", type=int, default=128)
    train.add_argument("--num-layers", type=int, default=1)
    train.add_argument("--dropout", type=float, default=0.0)
    train.add_argument("--include-archives", action="store_true")
    train.add_argument("--seed", type=int, default=42)
    train.add_argument("--device")
    train.add_argument("--amp", action=argparse.BooleanOptionalAction, default=True)
    train.add_argument("--grad-accum", type=int, default=1)
    train.add_argument("--resume")
    train.add_argument("--preset")
    train.add_argument("--architecture")
    train.add_argument("--n-heads", type=int, default=4)
    train.add_argument("--ff-dim", type=int, default=256)
    train.add_argument("--compile-model", action="store_true")
    train.add_argument("--multi-gpu", action="store_true")
    train.add_argument("--gradient-checkpointing", action="store_true")

    bench = sub.add_parser("benchmark")
    bench.add_argument("data_dir", nargs="?")
    bench.add_argument("--dataset")
    bench.add_argument("--checkpoint")
    bench.add_argument("--output", default="benchmark_results.csv")

    evaluate = sub.add_parser("evaluate")
    evaluate.add_argument("data_dir")
    evaluate.add_argument("--checkpoint")
    evaluate.add_argument("--mode", default="hybrid")

    device_cmd = sub.add_parser("device")

    args = parser.parse_args(argv)

    if args.command == "compress":
        t0 = time.perf_counter()
        info = compress_file(
            args.input,
            args.output,
            args.mode,
            args.checkpoint,
            args.overwrite,
            chunk_size=args.chunk_size,
            device=args.device,
            coder=args.coder,
        )
        ct = time.perf_counter() - t0
        _print_stats("Compression complete", info["original_size"], info["artifact_size"], ct)
        print(json.dumps(info, indent=2))
    elif args.command == "decompress":
        t0 = time.perf_counter()
        info = decompress_file(args.input, args.output, args.checkpoint, args.overwrite, args.max_output_size, args.device)
        dt = time.perf_counter() - t0
        src_size = Path(args.input).stat().st_size
        _print_stats("Decompression complete", info["restored_size"], src_size, 1.0, dt)
        print(json.dumps(info, indent=2))
    elif args.command == "inspect":
        path = Path(args.input)
        if path.suffix in {".pt", ".pth"}:
            model, obj = load_checkpoint(path, "cpu")
            print(
                json.dumps(
                    {
                        "type": "checkpoint",
                        "config": model.config.__dict__,
                        "epoch": obj.get("epoch"),
                        "fingerprint": obj.get("fingerprint"),
                        "parameter_count": sum(p.numel() for p in model.parameters()),
                        "metrics": obj.get("metrics"),
                    },
                    indent=2,
                    sort_keys=True,
                    default=str,
                )
            )
        else:
            with path.open("rb") as handle:
                prefix = handle.read(5)
                handle.seek(0)
                if len(prefix) == 5 and prefix[:4] == b"XAIC" and prefix[4] == 3:
                    from .streaming import read_header

                    md = read_header(handle)
                else:
                    md, _ = unpack_container(handle.read())
            print(json.dumps(md, indent=2, sort_keys=True))
    elif args.command == "train":
        from .train import train

        data_dir = args.dataset or args.data_dir
        output = args.output_checkpoint or args.output
        if not data_dir or not output:
            raise SystemExit("train requires data_dir/output or --dataset and --output-checkpoint")
        kwargs = vars(args)
        for key in ("command", "dataset", "output_checkpoint", "data_dir", "output"):
            kwargs.pop(key, None)
        train(data_dir, output, **kwargs)
    elif args.command == "benchmark":
        data_dir = args.dataset or args.data_dir
        if not data_dir:
            raise SystemExit("benchmark requires data_dir or --dataset")
        rows = run_suite(data_dir, args.checkpoint, args.output)
        print(f"wrote {args.output}: {len(rows)} rows")
    elif args.command == "evaluate":
        rows = run_suite(args.data_dir, args.checkpoint, None)
        lossless = all(r.lossless for r in rows)
        print(json.dumps({"files": len({r.file for r in rows}), "all_lossless": lossless}, indent=2))
    elif args.command == "device":
        print("\n".join(detect_device().report_lines()))

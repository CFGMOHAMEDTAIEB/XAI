import subprocess, sys, os, pathlib, hashlib, time, json, traceback

# Helper to run a command and capture output
def run_cmd(cmd, cwd=None):
    result = subprocess.run(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, shell=True)
    return result.stdout.strip(), result.stderr.strip(), result.returncode

def sha256_file(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            h.update(chunk)
    return h.hexdigest()

def main():
    python_exe = r"C:\\Python314\\python.exe"
    # 1. Show pip info
    pip_show_cmd = f"{python_exe} -m pip show xai-compress"
    out, err, rc = run_cmd(pip_show_cmd)
    print("PIP_SHOW_OUTPUT=\n" + out)
    # Show module file
    mod_file_cmd = f"{python_exe} -c \"import xai_compress, json; print(xai_compress.__file__)\""
    out, err, rc = run_cmd(mod_file_cmd)
    print("MODULE_FILE=\n" + out)

    # 2. Load selector
    from xai_compress.hybrid.selector import HybridSelector
    selector_path = r"C:\\Users\\ss\\Desktop\\XAI\\XAI\\engines\\XAI-Compress\\checkpoints\\selector_v2\\best.json"
    selector = HybridSelector(profile='balanced', mode='ai-benchmark', top_k=3,
                               microbench_bytes=65536, model_path=selector_path)
    try:
        artifact, error = selector._load_artifact()
        selector_loaded = artifact is not None
        error_msg = error if error else ""
        artifact_keys = list(artifact.__dict__.keys()) if artifact else []
    except Exception as e:
        selector_loaded = False
        error_msg = str(e)
        artifact_keys = []
    print(f"SELECTOR_LOADED={selector_loaded}")
    print(f"ERROR={error_msg}")
    print(f"ARTIFACT_KEYS={artifact_keys}")

    # 3. Real round-trip #1
    original_path = pathlib.Path(r"C:\\Users\\ss\\Desktop\\XAI\\XAI\\README.md")
    output_dir = pathlib.Path(r"C:\\Users\\ss\\Desktop\\XAI\\XAI\\scratch\\runtime-validation")
    output_dir.mkdir(parents=True, exist_ok=True)
    xaic_path = output_dir / (original_path.stem + ".xaic")
    restored_path = output_dir / (original_path.stem + "_restored" + original_path.suffix)

    original_bytes = original_path.stat().st_size
    sha_original = sha256_file(original_path)
    print(f"ORIGINAL_PATH={original_path}")
    print(f"ORIGINAL_BYTES={original_bytes}")
    print(f"SHA256_ORIGINAL={sha_original}")

    # Import compression functions
    from xai_compress.compression import compress_file, decompress_file
    # Compression
    try:
        start = time.perf_counter()
        info = compress_file(
            str(original_path),
            str(xaic_path),
            mode='hybrid-v2',
            profile='balanced',
            selector_model=selector_path,
            overwrite=True,
        )
        comp_seconds = time.perf_counter() - start
    except Exception as e:
        print("COMPRESSION_ERROR=" + traceback.format_exc())
        sys.exit(1)

    xaic_bytes = xaic_path.stat().st_size if xaic_path.exists() else 0
    print(f"XAIC_PATH={xaic_path}")
    print(f"XAIC_BYTES={xaic_bytes}")
    print(f"COMPRESSION_SECONDS={comp_seconds:.6f}")

    # Decompression
    try:
        start = time.perf_counter()
        de_info = decompress_file(
            str(xaic_path),
            str(restored_path),
            overwrite=True,
        )
        decomp_seconds = time.perf_counter() - start
    except Exception as e:
        print("DECOMPRESSION_ERROR=" + traceback.format_exc())
        sys.exit(1)

    restored_bytes = restored_path.stat().st_size if restored_path.exists() else 0
    sha_restored = sha256_file(restored_path) if restored_path.exists() else ""
    print(f"RESTORED_PATH={restored_path}")
    print(f"RESTORED_BYTES={restored_bytes}")
    print(f"DECOMPRESSION_SECONDS={decomp_seconds:.6f}")
    print(f"SHA256_RESTORED={sha_restored}")
    hash_equal = sha_original.lower() == sha_restored.lower()
    print(f"HASH_EQUAL={hash_equal}")

if __name__ == "__main__":
    main()

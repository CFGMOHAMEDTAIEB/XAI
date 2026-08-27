@echo off
where cargo >nul 2>nul || (echo Rust is missing. Install from https://rustup.rs && exit /b 1)
python -m pip install "maturin>=1.7,<2.0"
pushd rust-core
maturin develop --release
popd
python -c "import xai_compress_core; print('Rust core OK:', xai_compress_core)"

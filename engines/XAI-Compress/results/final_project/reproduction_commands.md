# Reproduction commands

```powershell
cd C:\Users\ss\Desktop\XAI\XAI\engines\XAI-Compress
.\.venv\Scripts\python.exe -m pytest -q
$env:PYO3_USE_ABI3_FORWARD_COMPATIBILITY='1'
cargo test --manifest-path rust-core\Cargo.toml
.\.venv\Scripts\python.exe scripts\finalize_project.py
.\.venv\Scripts\python.exe scripts\model_search_orchestrator.py status --config configs\model_search_v2.json
```

Kaggle safe-mode training is submitted only through the singleton autonomous controller. No credentials are stored in the repository.

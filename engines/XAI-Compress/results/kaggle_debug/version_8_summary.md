# Kaggle kernel version 8 smoke-gate summary

## ROOT CAUSE

Kaggle assigned `Tesla P100-PCIE-16GB` (`sm_60`). The installed PyTorch build supports only `sm_70`, `sm_75`, `sm_80`, `sm_86`, `sm_90`, `sm_100`, and `sm_120`. The first CUDA tensor operation failed with `cudaErrorNoKernelImageForDevice`. Classification: `CUDA_INCOMPATIBLE_RUNTIME` / `PROCESS_CRASH`; this was not OOM.

## LAST SUCCESSFUL STAGE

The version-7 fix worked: offline editable installation completed successfully. Optional Rust failed safely to the Python fallback. CUDA enumeration identified the assigned P100.

## FIX REQUIRED

Request `machine_shape: NvidiaTeslaT4` in Kaggle kernel metadata. Preserve the CUDA tensor smoke gate so an incompatible allocation cannot enter long training.

# Kaggle kernel version 9 smoke-gate summary

## RESULT

The requested `NvidiaTeslaT4` was assigned. Python 3.12.13, PyTorch 2.10.0+cu128, CUDA 12.8, and the first CUDA tensor operation succeeded. The run then failed before dataset construction with `RuntimeError: No attached training dataset was found` even though `/kaggle/input` usage was 17,921,462,459 bytes.

## CLASSIFICATION

`DATASET_NOT_FOUND` caused by the runner's top-level directory heuristic, not by a missing Kaggle attachment.

## FIX

Discover actual non-source files recursively, derive their mounted top-level dataset root, and print every input root with its file count before selection.

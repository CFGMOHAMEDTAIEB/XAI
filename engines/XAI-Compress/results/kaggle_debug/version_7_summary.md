# Kaggle kernel version 7 failure summary

## ROOT CAUSE

`pip install -e /kaggle/working/XAI-Compress --no-deps` retained PEP 517 build isolation. Pip attempted to install build dependencies in the Internet-disabled kernel and failed. Classification: `IMPORT_ERROR` (environment/package installation stage).

## FAILURE STAGE

Editable project installation, before importing XAI-Compress and before CUDA, Rust, dataset loading, checkpoint recovery, or training.

## LAST SUCCESSFUL STAGE

The source dataset was materialized at `/kaggle/working/XAI-Compress`; pip recognized it as a local editable project.

## FIX REQUIRED

Install editable source with both `--no-deps` and `--no-build-isolation`, using Kaggle's already-installed build tooling. Keep optional Cargo/Rust failure non-fatal.

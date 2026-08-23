@echo off
setlocal
if "%~1"=="" goto usage
set TEST_DATA=%~1
set CHECKPOINT=%~2
set METRICS=%~3
set SUITE=XAI-Compress-Analysis-Suite

python -m pip install -r "%SUITE%\requirements-analysis.txt"
if errorlevel 1 exit /b 1

if /I "%CHECKPOINT%"=="NONE" (
  python "%SUITE%\run_benchmark.py" --data-dir "%TEST_DATA%" --output "%SUITE%\outputs\tables\benchmark_results.csv"
) else (
  python "%SUITE%\run_benchmark.py" --data-dir "%TEST_DATA%" --checkpoint "%CHECKPOINT%" --output "%SUITE%\outputs\tables\benchmark_results.csv"
)
if errorlevel 1 exit /b 1

if not "%METRICS%"=="" (
  python "%SUITE%\analyze_training.py" --metrics "%METRICS%" --output-dir "%SUITE%\outputs"
)

python "%SUITE%\visualize_results.py" --input "%SUITE%\outputs\tables\benchmark_results.csv" --output-dir "%SUITE%\outputs"
if errorlevel 1 exit /b 1

python "%SUITE%\generate_report.py" --benchmark "%SUITE%\outputs\tables\benchmark_results.csv" --training-summary "%SUITE%\outputs\tables\training_summary.json" --output "%SUITE%\outputs\reports\XAI_COMPRESS_REPORT.md"
if errorlevel 1 exit /b 1

echo Analysis complete. Open %SUITE%\outputs\reports\XAI_COMPRESS_REPORT.md
exit /b 0

:usage
echo Usage: run_analysis_windows.bat TEST_DATA CHECKPOINT_OR_NONE METRICS_CSV
echo Example: run_analysis_windows.bat data\test checkpoints\gru_v3.pt checkpoints\gru_v3.metrics.csv
exit /b 2

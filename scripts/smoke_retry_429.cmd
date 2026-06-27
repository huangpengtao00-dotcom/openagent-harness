@echo off
setlocal
title OpenAgent Harness retry-429 smoke

cd /d "%~dp0.."

set "PYTHONPATH=%CD%\src"
set "TASK=.\benchmarks_realistic\retry-429-real\task.json"
set "RUNS=.\runs_smoke_retry_429"

echo.
echo Running local scripted retry-429 smoke...
echo Harness: %CD%
echo Task:    %TASK%
echo Runs:    %RUNS%
echo.

python -m openagent_harness.cli run "%TASK%" --runs "%RUNS%" --mode local --model scripted
if errorlevel 1 (
  echo.
  echo Smoke run failed. Check the error above.
  if /i not "%OPENAGENT_NO_PAUSE%"=="1" pause
  exit /b 1
)

echo.
echo Smoke run completed. Inspect the latest folder under:
echo %CD%\runs_smoke_retry_429
echo.
echo Expected artifacts:
echo - patch.diff
echo - test_result.json
echo - gate.json
echo - scorecard.json
echo - trace.jsonl
echo - report.html
echo - final_report.md
echo.
if /i not "%OPENAGENT_NO_PAUSE%"=="1" pause

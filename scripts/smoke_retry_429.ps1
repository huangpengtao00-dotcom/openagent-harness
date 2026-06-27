param(
    [string]$Runs = ".\runs_smoke_retry_429"
)

$ErrorActionPreference = "Stop"

$harnessRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
Set-Location -LiteralPath $harnessRoot

$env:PYTHONPATH = Join-Path $harnessRoot "src"
$task = ".\benchmarks_realistic\retry-429-real\task.json"

Write-Host ""
Write-Host "Running local scripted retry-429 smoke..."
Write-Host "Harness: $harnessRoot"
Write-Host "Task:    $task"
Write-Host "Runs:    $Runs"
Write-Host ""

python -m openagent_harness.cli run $task --runs $Runs --mode local --model scripted

Write-Host ""
Write-Host "Smoke run completed. Inspect the latest folder under:"
Write-Host (Join-Path $harnessRoot $Runs)
Write-Host ""
Write-Host "Expected artifacts:"
Write-Host "- patch.diff"
Write-Host "- test_result.json"
Write-Host "- gate.json"
Write-Host "- scorecard.json"
Write-Host "- trace.jsonl"
Write-Host "- report.html"
Write-Host "- final_report.md"

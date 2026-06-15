# OpenAgent Harness Architecture

OpenAgent Harness is a quality and evaluation layer for coding agents. It does not try to replace a full IDE assistant or hosted coding platform. It wraps an executor with task specs, tool policy, trace capture, quality gates, and failure analysis.

## Core Flow

1. Load a `TaskSpec`.
2. Copy the target repository into a run directory.
3. Execute either the local deterministic agent or the API-ready adapter.
4. Record every phase to `trace.jsonl` and `trace.sqlite`.
5. Generate `patch.diff`, `test_result.json`, and `final_report.md`.
6. Run `QualityGate` as the source of truth.
7. Classify failure type for interview-grade debugging.

## Eval Flow

The `eval` command discovers every `benchmarks/*/task.json`, runs each task through the same local harness, then writes `eval_summary.json`. This gives the project a real benchmark surface instead of a single cherry-picked demo.

Current local benchmark set:

- `T1-calc-div-zero`: return `None` for division by zero.
- `T2-pager-off-by-one`: fix 1-based pagination.
- `T3-cli-invalid-flag`: return exit code `2` for invalid CLI flags.
- `T4-mini-blog-slug-conflict`: return `409` on duplicate slug.
- `T5-csv-bom-cleanup`: remove UTF-8 BOM from CSV cells.

## Two Versions

### Version A: Local Demo

This version does not call any model API. It uses a deterministic `ScriptedAgent` so the project can be demonstrated on any laptop, in a classroom, or during an interview without API keys or spend risk.

### Version B: API-Ready

This version records API configuration through the `ApiAgent` adapter but intentionally does not make network calls. The real LiteLLM call site is left behind a clear budget/key decision because benchmark runs can become expensive quickly.

## Quality Gate Rules

- `NoPatch`: no meaningful patch was produced.
- `Unverified`: a patch exists, but tests were not run.
- `Regression`: tests ran and failed.
- `ScopeViolation`: patch changed files outside the allowlist.
- `ReportMissing`: execution did not produce a final report.
- `ApiNotConfigured`: API mode was selected, but real model calls are intentionally disabled.

## Why This Is Interview-Friendly

Most demo AI projects only show model output. This project shows the engineering layer that decides whether the output is trustworthy. That maps well to AI engineering roles because it covers reproducibility, evaluation, traces, budgets, and failure diagnosis.

# OpenAgent Harness

OpenAgent Harness is a **multi-model Coding Agent evaluation platform**. It runs the same engineering tasks across multiple model profiles, captures each patch/test/trace artifact, then produces a horizontal comparison by pass rate, score, cost, latency, patch size, and failure type.

Related backend:

- OpenAgent Platform Backend: https://github.com/huangpengtao00-dotcom/openagent-platform-backend

## What it does

Given a `task.json`, the harness can:

1. create an isolated workspace;
2. compact repository context with file ranking and AST symbol indexing;
3. run a JSON-action coding agent backed by DeepSeek/OpenAI-compatible models;
4. expose audited local tools: `read_file`, `edit_file`, `write_file`, `search_repo`, `inspect_symbols`, `run_command`;
5. enforce allowlist write scope and shell safety policy;
6. run acceptance checks with timeout and structured evidence;
7. generate `patch.diff`, `gate.json`, `scorecard.json`, `trace.jsonl`, `trace.sqlite`, `final_report.md`, and `report.html`;
8. run benchmark suites and produce `eval_report.html`;
9. run a `task x model profile` comparison matrix and produce `comparison_summary.json` plus `comparison_report.html`.

## Why this project is interview-grade

Most coding-agent demos stop at “LLM generated code.” This project focuses on the harder engineering questions:

- How do you keep an agent inside a safe file boundary?
- How do you prevent arbitrary shell execution?
- How do you compact repository context before calling a cheap model?
- How do you make edits reviewable instead of rewriting whole files?
- How do you verify that a patch actually passes tests?
- How do you classify failures and compare candidates?
- How do you produce evidence an interviewer can inspect?

## Multi-model comparison

The main evaluation path is now a model comparison matrix:

```bash
PYTHONPATH=src python -m openagent_harness.cli compare \
  --benchmarks benchmarks_engineering \
  --profiles examples/model_profiles.json \
  --runs runs_compare \
  --parallel 3
```

This runs every task against every profile and writes:

```text
runs_compare/comparison_summary.json
runs_compare/comparison_report.html
runs_compare/<profile>/<task>/<run_id>/patch.diff
runs_compare/<profile>/<task>/<run_id>/scorecard.json
runs_compare/<profile>/<task>/<run_id>/trace.jsonl
```

To run real NewAPI model profiles, put keys in environment variables and pass `--allow-llm-calls`:

```powershell
$env:OPENAGENT_GPT55_API_KEY = "<gpt-5.5 channel key>"
$env:OPENAGENT_GPT54_API_KEY = "<gpt-5.4 channel key>"
python -m openagent_harness.cli compare --benchmarks benchmarks_engineering --profiles examples/model_profiles.json --runs runs_compare_real --parallel 2 --allow-llm-calls
```

The profile file stores model names, endpoint URLs, and environment variable names. API keys stay outside the repository.

## Architecture

```text
TaskSpec -> Workspace -> ContextBuilder + CodeIndex -> JSON Action Agent
   -> LocalToolRegistry -> PermissionPolicy -> Acceptance Runner
   -> QualityGate -> Scorecard -> HTML Report / Trace / Diff
```

Important modules:

| File | Purpose |
|---|---|
| `src/openagent_harness/llm.py` | DeepSeek/OpenAI-compatible client, JSON response mode, token/cost estimate |
| `src/openagent_harness/agent_loop.py` | model -> action -> tool -> observation loop |
| `src/openagent_harness/tool_registry.py` | auditable tool registry |
| `src/openagent_harness/policy.py` | allowlist and shell safety policy |
| `src/openagent_harness/context.py` | repository context compaction |
| `src/openagent_harness/code_index.py` | Python AST symbol index and grep search |
| `src/openagent_harness/runner.py` | workspace, diff, acceptance, gate, report pipeline |
| `src/openagent_harness/compare.py` | multi-profile benchmark matrix and model comparison report |
| `src/openagent_harness/scoring.py` | 0-100 run scorecard |
| `src/openagent_harness/html_report.py` | readable run/eval reports |
| `src/openagent_harness/portfolio.py` | candidate selection surface |

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e .
```

Run a stable local smoke-test group:

```bash
python -m compileall -q src
PYTHONPATH=src python -m pytest tests/test_secure_deepseek_env.py tests/test_tool_registry_newlines.py tests/test_cli.py -q
```

Expected:

```text
11 passed
```

The full test suite includes subprocess-heavy benchmark tests. For the most stable cross-platform validation, run tests by file or use the benchmark commands below as the system-level acceptance check.

Run toy benchmark evaluation:

```bash
PYTHONPATH=src python -m openagent_harness.cli eval --benchmarks benchmarks --runs runs_eval_final
```

Expected:

```text
total=7
passed=7
failed=0
pass_rate=1.0
```

Run realistic interview benchmark evaluation:

```bash
PYTHONPATH=src python -m openagent_harness.cli eval --benchmarks benchmarks_realistic --runs runs_v1_realistic
```

Expected:

```text
total=3
passed=3
failed=0
pass_rate=1.0
```

The generated `eval_summary.json` is structured for quantitative comparison, not only pass/fail:

```json
{
  "total": 3,
  "passed": 3,
  "failed": 0,
  "pass_rate": 1.0,
  "avg_score": 96.5,
  "total_patch_lines": 182,
  "total_changed_files": 5,
  "tests_passed": 3,
  "failure_types": {
    "None": 3
  },
  "tokens": 0,
  "total_cost_usd": 0.0,
  "duration_seconds": 1.234
}
```

Each result row also includes `profile`, `score`, `patch_lines`, `changed_files`, `tests_passed`, `failure_type`, `tokens`, `estimated_cost_usd`, `duration_seconds`, and `run_dir`. The Platform Dashboard consumes the same shape and adds live API/retry comparison.

## CLI examples

Render compact context:

```bash
PYTHONPATH=src python -m openagent_harness.cli context benchmarks/calc-py/repo "fix zero division"
```

Inspect symbols:

```bash
PYTHONPATH=src python -m openagent_harness.cli index src/openagent_harness --query agent
```

Print tool schemas:

```bash
PYTHONPATH=src python -m openagent_harness.cli tools .
```

Run one benchmark offline:

```bash
PYTHONPATH=src python -m openagent_harness.cli run benchmarks/calc-py/task.json --runs runs_demo
```

Run one realistic benchmark offline:

```bash
PYTHONPATH=src python -m openagent_harness.cli run benchmarks_realistic/retry-429-real/task.json --runs runs_demo_v1
```

Run portfolio selection:

```bash
PYTHONPATH=src python -m openagent_harness.cli portfolio benchmarks/calc-py/task.json --runs runs_portfolio_demo
```

## DeepSeek / OpenAI-compatible model mode

Create a dry-run API configuration artifact without making a network call. This command forcibly disables task-level `budget.enable_llm_calls`, so it is safe even when the task file is prepared for real API mode:

```bash
PYTHONPATH=src python -m openagent_harness.cli api-check examples/deepseek_real_task.json --model deepseek-v4-flash
```

Expected output includes `network_call=false`.

Secure key setup:

```bash
cp .env.example .env
# Edit .env locally. Do not commit it.
PYTHONPATH=src python -m openagent_harness.cli deepseek-check --model deepseek-v4-flash
```

One-call connectivity smoke test:

```bash
PYTHONPATH=src python -m openagent_harness.cli deepseek-smoke --model deepseek-v4-flash
```

Real model call:

```bash
PYTHONPATH=src python -m openagent_harness.cli run examples/deepseek_real_task.json \
  --mode api \
  --model deepseek-v4-flash \
  --allow-llm-calls
```

API calls are disabled by default at the Harness CLI request layer. This prevents accidental spending during demos. Real keys are read only from environment variables or local `.env`, and `.env` is excluded by `.gitignore`. `api-check` loads the current working directory `.env` first, then the task-spec directory `.env` without overriding existing values; it never makes a network call. See `docs/secure_deepseek_key_setup.md`.


## Stable verification commands

For local project validation, keep unit tests and benchmark execution as separate commands. This avoids recursively nesting too many pytest subprocesses during CI-style checks while still validating both layers.

```bash
python -m compileall -q src
PYTHONPATH=src python -m pytest tests/test_secure_deepseek_env.py tests/test_tool_registry_newlines.py tests/test_cli.py -q
PYTHONPATH=src python -m openagent_harness.cli eval --benchmarks benchmarks --runs runs_eval_toy
PYTHONPATH=src python -m openagent_harness.cli eval --benchmarks benchmarks_realistic --runs runs_eval_realistic
```

For API onboarding without spending, run:

```bash
PYTHONPATH=src python -m openagent_harness.cli deepseek-check --model deepseek-v4-flash
PYTHONPATH=src python -m openagent_harness.cli api-check examples/deepseek_real_task.json --model deepseek-v4-flash
```

## JSON action protocol

The model must return one JSON object per turn:

```json
{"action":"search_repo","query":"zero denominator","limit":10}
```

```json
{"action":"inspect_symbols","query":"divide","limit":10}
```

```json
{
  "action":"edit_file",
  "path":"app.py",
  "old_text":"    return a / b\n",
  "new_text":"    if b == 0:\n        return None\n    return a / b\n",
  "expected_replacements":1
}
```

```json
{"action":"run_command","command":"python -m pytest -q"}
```

```json
{"action":"finish","summary":"Handled zero denominator and verified with pytest."}
```

## Benchmark tasks

The repo includes seven toy regression benchmark tasks:

| Task | Scenario |
|---|---|
| `calc-py` | zero division bug |
| `pager-py` | pagination off-by-one |
| `cli-tool` | invalid CLI flag handling |
| `mini-blog` | slug conflict behavior |
| `csv-cleaner` | UTF-8 BOM cleanup |
| `cache-ttl` | expired cache eviction |
| `retry-policy` | HTTP retry policy boundary |

The `benchmarks_realistic/` suite adds three GitHub-issue-style tasks for interview demos:

| Task | Scenario |
|---|---|
| `retry-429-real` | HTTP 429 retry behavior under retry budget |
| `config-loader-real` | nested config merge without mutating defaults |
| `fastapi-error-handler-real` | production error response should not leak internals |

The `benchmarks_engineering/` suite is intended for model comparison rather than simple smoke tests:

| Task | Scenario |
|---|---|
| `policy-auth-audit` | multi-file config merge, authorization priority, audit redaction |
| `retry-client-observability` | retry budget, 429/5xx handling, backoff, attempt events |
| `artifact-query-api` | artifact path safety, filtering, pagination, missing-file tolerance |

## Evidence generated per run

Each run directory contains:

```text
repo/                isolated patched repo
patch.diff           full repository diff
test_result.json     structured acceptance evidence
gate.json            binary quality gate
scorecard.json       comparative score
report.html          readable report
trace.jsonl          replayable timeline
trace.sqlite         queryable trace database
final_report.md      compact text summary
```

## Interview positioning

Use this one-liner:

> OpenAgent Harness is a multi-model coding-agent evaluation platform with OpenAI-compatible model profiles, concurrent task x model comparison, JSON-action tool loop, patch-level editing, permission policy, repository context compaction, acceptance verification, scorecards, trace replay, and HTML evidence reports.

See:

- `docs/final_architecture.md`
- `docs/interview_playbook_cn.md`
- `docs/interview_prep_from_zero_cn.md`
- `docs/interview_flashcards_cn.md`
- `docs/evidence_matrix.md`
- `docs/demo_commands.md`


## v1.0 interview delivery docs

- `docs/v1_interview_report.md`
- `docs/deepseek_real_run.md`
- `docs/system_design_cn.md`
- `docs/interview_qa_cn.md`

The project intentionally does not ship fabricated real DeepSeek artifacts. Real API evidence should be generated with your own key and saved under `runs_deepseek_real/`.

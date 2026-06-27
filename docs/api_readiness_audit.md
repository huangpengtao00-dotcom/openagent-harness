# OpenAgent Harness API Readiness Audit

## Route check

The project goal is **not** to keep adding agent buzzwords. The current route is:

1. Keep a local deterministic baseline for offline verification.
2. Add a safe DeepSeek/OpenAI-compatible API path.
3. Generate auditable evidence: context, tool calls, permission decisions, patch, tests, cost, scorecard, HTML report.
4. Use realistic but small benchmarks for interview demonstration.

The latest changes are necessary because they remove API onboarding blockers rather than expanding scope.

## Fixed blockers

### 1. `.env.example` was missing

Documentation asked users to copy `.env.example`, but the file was absent. This blocked safe local key setup. The template now exists and only contains empty placeholders.

### 2. `api-check` could accidentally execute API mode

Task specs can include `budget.enable_llm_calls=true`. `api-check` is supposed to be a dry-run configuration command, so it now forcibly disables that flag for the check command and prints `network_call=false`.

### 3. Runtime policy and post-run gate used different allowlist semantics

`PermissionPolicy` supported glob patterns such as `src/*.py`, while `QualityGate` previously used exact set membership. The two layers now share `is_path_allowed_by_patterns`, preventing a file from being allowed during editing but rejected after verification.

### 4. Stable API onboarding sequence

The recommended sequence is:

```bash
cp .env.example .env
PYTHONPATH=src python -m openagent_harness.cli deepseek-check --model deepseek-v4-flash
PYTHONPATH=src python -m openagent_harness.cli deepseek-smoke --model deepseek-v4-flash
PYTHONPATH=src python -m openagent_harness.cli run examples/deepseek_real_task.json --mode api --model deepseek-v4-flash --allow-llm-calls --runs runs_deepseek_real
```

Only the last two commands can make a network call; `deepseek-check` and `api-check` are dry-run checks.

## Non-goals

- No multi-agent orchestration yet.
- No large dependency introduction.
- No fake DeepSeek evidence.
- No hardcoding real keys into source, docs, tests, or packaged artifacts.

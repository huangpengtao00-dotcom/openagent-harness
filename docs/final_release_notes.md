# OpenAgent Harness v1 Final Release Notes

This release is the interview-ready API-closed-loop version. It keeps the project focused on a low-cost, auditable Coding Agent Harness rather than a broad all-in-one coding assistant.

## What is included

- Secure DeepSeek/OpenAI-compatible API loading via local `.env`.
- `deepseek-check` for non-spending configuration inspection.
- `api-check` for non-spending dry-run API readiness artifacts.
- `deepseek-smoke` for one minimal real API call.
- Guarded API agent run with JSON actions, tool registry, allowlist policy, patch-level edits, pytest acceptance, trace, scorecard, and HTML report.
- Windows-safe path handling for run artifacts.
- Robust usage parsing when a provider returns redacted or nonstandard usage fields.
- Newline-preserving `edit_file`, so a one-line fix does not create noisy full-file diffs on Windows.

## Validation commands

```bash
python -m compileall -q src
python -m pytest tests/test_secure_deepseek_env.py tests/test_tool_registry_newlines.py tests/test_cli.py -q
PYTHONPATH=src python -m openagent_harness.cli eval --benchmarks benchmarks_realistic --runs runs_eval_realistic_final
PYTHONPATH=src python -m openagent_harness.cli eval --benchmarks benchmarks --runs runs_eval_toy_final
```

## Real API evidence

A real DeepSeek run should produce:

- `report.html`
- `trace.jsonl`
- `patch.diff`
- `scorecard.json`
- `test_result.json`
- `gate.json`
- `api_agent_run.json`
- `context_summary.json`
- `task_spec.json`

Do not commit `.env` or any API key.

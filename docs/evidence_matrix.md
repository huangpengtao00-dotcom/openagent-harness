# OpenAgent Harness Evidence Matrix

This matrix keeps interview claims tied to code, tests, and artifacts. Use it to avoid overclaiming.

## Claim To Evidence

| Claim | Repository evidence | Verification / artifact | Boundary |
|---|---|---|---|
| Built a local Coding Agent execution and evaluation harness | `src/openagent_harness/runner.py`, `src/openagent_harness/cli.py` | `python -m pytest -q` -> `66 passed` | Local interview-grade harness, not commercial platform |
| Supports JSON action tool loop | `src/openagent_harness/agent_loop.py` | Tests and API mode code path | Real API run requires configured key and explicit allow |
| Exposes audited local tools | `src/openagent_harness/tool_registry.py` | `python -m openagent_harness.cli tools .` | Small local tool set, not arbitrary tool marketplace |
| Enforces allowlist write scope and shell safety | `src/openagent_harness/policy.py` | `tests/test_workspace_safety.py`, `tests/test_gate.py` | Not container-grade sandbox |
| Uses repository context compaction | `src/openagent_harness/context.py` | `python -m openagent_harness.cli context ...` | Deterministic heuristic context, not full semantic retrieval |
| Uses Python AST symbol index | `src/openagent_harness/code_index.py` | `python -m openagent_harness.cli index ...` | Python-only AST; tree-sitter would be next |
| Generates patch, test evidence, gate, scorecard, trace, HTML report | `runner.py`, `gate.py`, `scoring.py`, `html_report.py`, `trace.py` | Run directories contain `patch.diff`, `test_result.json`, `gate.json`, `scorecard.json`, `trace.jsonl`, `trace.sqlite`, `report.html` | Evidence is local artifact output |
| Classifies failure types | `src/openagent_harness/gate.py` | Gate can return `NoPatch`, `ScopeViolation`, `Regression`, `Unverified`, `ReportMissing` | Failure taxonomy is v1, not exhaustive |
| Scores runs for comparison | `src/openagent_harness/scoring.py` | `scorecard.json`; hygiene-blocked verified patches keep partial engineering score | Simple deterministic rubric, not a production risk engine |
| Runs benchmark evaluation | `src/openagent_harness/eval.py` | `runs_eval_codex_check/eval_summary.json` -> `7/7`; `runs_eval_realistic_codex_final_check/eval_summary.json` -> `3/3` | Scripted baseline evidence, zero token cost |
| Supports DeepSeek/OpenAI-compatible path | `src/openagent_harness/llm.py`, `model_adapter.py`, `cli.py` | `api-check` prints `network_call=false`; real calls require `--allow-llm-calls` | Do not claim fabricated real DeepSeek artifacts |
| Explores a multi-file backend policy task with DeepSeek | `custom_tasks/dpsk-complex-policy-pipeline-20260623/task.json`, `docs/boundary_exploration_20260623.md` | DeepSeek run produced `7 passed`, 3 changed files, 118 patch lines, 48,828 tokens, and exposed an artifact-hygiene false positive | One complex exploratory task, not SWE-bench-level coverage |

## Safe Interview Summary

> OpenAgent Harness is a local-first Coding Agent execution and evaluation framework. It standardizes task input, builds compact repo context, lets an agent use JSON actions against audited local tools, enforces file and shell safety policy, runs acceptance checks, and emits diff/test/gate/scorecard/trace/report artifacts for review.

## Do Not Say

- Do not say it is a production commercial Agent platform.
- Do not say it fully implements SWE-bench.
- Do not say every benchmark is a real open-source issue.
- Do not say real DeepSeek evidence exists unless you generated it with your own key and saved the artifact.
- Do not say it is container-sandboxed; current safety is path, command, workspace, and gate based.

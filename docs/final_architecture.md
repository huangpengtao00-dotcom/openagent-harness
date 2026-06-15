# OpenAgent Harness — Final Interview Architecture

## Positioning

OpenAgent Harness is a local-first coding-agent evaluation platform. It is not a simple chatbot wrapper. The system evaluates whether an LLM-powered coding agent can safely understand a repository, choose tools, edit code, run acceptance checks, and produce auditable evidence.

The project is designed for AI engineering interviews because it covers three layers at once:

1. LLM application engineering: OpenAI-compatible / DeepSeek client, JSON action protocol, context compaction, token/cost budget.
2. Agent system engineering: tool registry, permission policy, patch-level edits, iterative observe-act loop, workspace isolation.
3. Evaluation engineering: benchmark tasks, quality gate, trace replay, scorecard, HTML report, failure classification.

## Architecture

```text
TaskSpec(task.json)
   |
   v
WorkspaceManager  ---> isolated repo copy
   |
   v
ContextBuilder ----> repository map + AST symbol map + selected source snippets
   |
   v
JsonActionCodingAgent
   |      ^
   |      |
   v      |
LocalToolRegistry ---- read_file / edit_file / search_repo / inspect_symbols / run_command
   |
   v
PermissionPolicy ---- allowlist write scope + shell command safety
   |
   v
Acceptance Runner ---- pytest/custom checks + timeout + structured result
   |
   v
QualityGate ---- diff exists + tests ran + tests passed + scope ok + report exists
   |
   v
Scorecard + report.html + trace.jsonl + trace.sqlite + patch.diff
```

## Why this is stronger than the earlier version

Earlier versions proved that the harness could run tests and detect basic patch scope. The final architecture proves a full coding-agent loop:

- The agent can inspect a repo, not just receive a fixed file.
- The agent can use a registry of tools, not hardcoded if/else actions.
- The agent can make local patch edits through `edit_file`, not only replace whole files.
- The harness can inspect Python symbols through AST indexing.
- Runs produce both machine-readable and human-readable evidence.
- Benchmarks include seven task types instead of a single toy arithmetic case.

## DeepSeek / cheap LLM integration

`OpenAICompatibleClient` keeps the API layer minimal and inspectable. It supports DeepSeek-style OpenAI-compatible chat completions through:

- `OPENAGENT_API_KEY` or `DEEPSEEK_API_KEY`
- `OPENAGENT_BASE_URL` or `DEEPSEEK_BASE_URL`
- JSON response mode
- optional `thinking` / `reasoning_effort` fields
- deterministic fallback token and cost estimation

API calls are disabled by default. A real model run requires explicit budget approval:

```bash
python -m openagent_harness.cli run examples/deepseek_task.json \
  --mode api \
  --model deepseek-v4-flash \
  --allow-llm-calls
```

## Tool action protocol

The LLM must output exactly one JSON object per turn. Examples:

```json
{"action":"search_repo","query":"divide zero denominator","limit":10}
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

## Evaluation evidence

Each run directory contains:

- `repo/`: isolated patched repository
- `patch.diff`: full diff across the repository snapshot
- `test_result.json`: structured command, stdout, stderr, timeout, duration
- `gate.json`: final pass/fail decision
- `scorecard.json`: 0-100 engineering score
- `report.html`: readable evidence report
- `trace.jsonl`: replayable step timeline
- `trace.sqlite`: queryable trace database
- `final_report.md`: compact text report

## Interview talking points

### 1. Why not just call an LLM once?

Single-shot generation cannot observe runtime failures. Coding-agent systems need an observe-act loop: inspect files, patch, run tests, read failures, patch again. This project implements that loop with an auditable JSON protocol.

### 2. Why tool registry?

Hardcoded actions do not scale. A registry separates agent policy from tool implementation. Adding semantic search, lint, type check, MCP tools, or database inspection becomes a tool extension rather than an agent-loop rewrite.

### 3. Why allowlist policy?

Coding agents can over-edit or touch unrelated files. The allowlist makes the task boundary explicit and gives the quality gate a concrete criterion for scope control.

### 4. Why patch-level edit?

Whole-file writes destroy local formatting and create noisy diffs. `edit_file` enforces exact anchors and fails on ambiguous matches, which reduces hallucinated rewrites and makes review easier.

### 5. Why scorecard if gate already exists?

The gate is binary. The scorecard is comparative. It lets a portfolio runner select among multiple candidates by combining pass/fail, scope, patch size, changed-file count, and timeout penalties.

## Remaining extensions

The project is now strong enough for an interview demo. If extended further, the highest-value additions are:

- real multi-candidate LLM sampling with temperature/top-p variation;
- git worktree strategy for large repositories;
- tree-sitter index for multi-language codebases;
- mutation testing to catch overfitting to tests;
- web UI for trace timeline and patch review;
- MCP-compatible external tool adapters.

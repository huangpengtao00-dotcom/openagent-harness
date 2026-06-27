# OpenAI/Fighting Provider Audit - 2026-06-20

## Rollback Snapshot

- Snapshot: `C:\Users\hpt\Documents\实习项目\Interview-Project-Bundle-20260617-233344\02_OpenAgent_Harness_backup_before_openai_20260620-162914`
- Excluded from the snapshot: `.env`, virtual environments, cache folders, and run artifacts.

## Findings

1. `OPENAI_API_KEY` was recognized, but the old key-selection order preferred `DEEPSEEK_API_KEY` whenever a local `.env` contained one. That made OpenAI/Fighting requests use the wrong bearer token.
2. OpenAI/Fighting uses the Responses wire API, while the original harness only emitted Chat Completions payloads.
3. Provider errors could include partially masked key fragments. The sanitizer now redacts masked `sk-...` strings as well as full keys.
4. The OpenAI/Fighting hard-task run returned one malformed multi-JSON response at step 1. The agent recovered, but the JSON parser now accepts the first complete JSON object and ignores trailing text.

## Code Changes

- `src/openagent_harness/llm.py`
  - Added provider-aware API key resolution.
  - Added OpenAI default base URL inference for `gpt-*` models.
  - Added `wire_api=responses`, `reasoning_effort`, and `store=false` support.
  - Added Responses API usage parsing for `input_tokens` / `output_tokens`.
- `src/openagent_harness/cli.py`
  - Added `--wire-api`, `--reasoning-effort`, and `--disable-response-storage`.
  - Restored explicit `--allow-llm-calls` gate for real smoke calls.
  - Converted smoke API errors into concise CLI errors.
- `src/openagent_harness/env.py`
  - Hardened redaction for provider-masked API key fragments.
- `src/openagent_harness/agent_loop.py`
  - Hardened JSON action parsing for trailing text or multiple JSON objects.
- `.env.example`
  - Documented optional OpenAI base URL, wire API, and response-storage opt-out settings.

## Live Runs

### OpenAI/Fighting Smoke

- Command profile: `gpt-5.5`, `wire_api=responses`, `reasoning_effort=high`, `store=false`, base URL `http://43.106.115.130:8080/v1`
- Artifact: `runs_openai_fighting_smoke_newkey_afterfix/deepseek_smoke.json`
- Result: pass
- Usage: 5,167 tokens

### OpenAI/Fighting Hard Task

- Task: `custom_tasks/stair-25-hard-token-bucket/task.json`
- Artifact: `runs_openai_fighting_compare_20260620/stair-25-hard-token-bucket-2ae21048`
- Result: pass
- Score: 100
- Tests: `python -m pytest -q` passed
- Patch: 16 lines, 1 changed file
- Usage: 32,159 tokens
- Note: estimated cost is `0.0` because the local price table only covers DeepSeek models.

### DeepSeek Hard Task

- Task: `custom_tasks/stair-25-hard-token-bucket/task.json`
- Artifact: `runs_deepseek_compare_20260620/stair-25-hard-token-bucket-c5a04c4a`
- Result: pass
- Score: 100
- Tests: `python -m pytest -q` passed
- Patch: 14 lines, 1 changed file
- Usage: 4,005 tokens
- Estimated cost: 0.00073668 USD

## DeepSeek Baseline Evidence

- Evidence: `..\01_OpenAgent_Platform_Backend\evidence\real_deepseek_staircase_20260619-204138`
- Final useful result: 30 valid task scenarios passed after the nested-parameters harness fix and one corrected CSV fixture.
- Total recorded DeepSeek runs: 38
- Total tokens: 181,186
- Estimated spend: 0.03034262 USD, approximately 0.219984 CNY at 7.25 USD/CNY.

## Reproduction Commands

```powershell
$env:PYTHONPATH='src'
$env:OPENAI_API_KEY='<local-key>'
python -m openagent_harness.cli deepseek-smoke --model gpt-5.5 --base-url http://43.106.115.130:8080/v1 --wire-api responses --reasoning-effort high --disable-response-storage --allow-llm-calls --runs runs_openai_fighting_smoke
python -m openagent_harness.cli run custom_tasks\stair-25-hard-token-bucket\task.json --mode api --model gpt-5.5 --base-url http://43.106.115.130:8080/v1 --wire-api responses --reasoning-effort high --disable-response-storage --allow-llm-calls --runs runs_openai_fighting_compare
python -m openagent_harness.cli run custom_tasks\stair-25-hard-token-bucket\task.json --mode api --model deepseek-v4-flash --allow-llm-calls --runs runs_deepseek_compare
python -m pytest -q
```


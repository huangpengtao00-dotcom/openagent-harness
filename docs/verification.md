# Verification Guide

Use separate commands for unit tests, local benchmark evaluation, and API checks. This keeps the project demonstrable and avoids confusing a local test-runner issue with LLM/API behavior.

## 1. Compile

```bash
python -m compileall -q src
```

## 2. Unit tests

```bash
python -m compileall -q src
PYTHONPATH=src python -m pytest tests/test_secure_deepseek_env.py tests/test_tool_registry_newlines.py tests/test_cli.py -q
```

Expected result after the API-readiness fixes:

```text
36 passed
```

## 3. Toy benchmark suite

```bash
PYTHONPATH=src python -m openagent_harness.cli eval --benchmarks benchmarks --runs runs_eval_toy
```

Expected:

```text
total=7
passed=7
failed=0
pass_rate=1.0
```

## 4. Realistic benchmark suite

```bash
PYTHONPATH=src python -m openagent_harness.cli eval --benchmarks benchmarks_realistic --runs runs_eval_realistic
```

Expected:

```text
total=3
passed=3
failed=0
pass_rate=1.0
```

## 5. API dry checks

These commands do not call the network:

```bash
PYTHONPATH=src python -m openagent_harness.cli deepseek-check --model deepseek-v4-flash
PYTHONPATH=src python -m openagent_harness.cli api-check examples/deepseek_real_task.json --model deepseek-v4-flash
```

`api-check` should print `network_call=false`. With a configured key it prints `status=ok`; without a key it prints `status=missing_key`. Neither path makes a network call.

## 6. Real API calls

Only these commands can spend tokens:

```bash
PYTHONPATH=src python -m openagent_harness.cli deepseek-smoke --model deepseek-v4-flash
PYTHONPATH=src python -m openagent_harness.cli run examples/deepseek_real_task.json --mode api --model deepseek-v4-flash --allow-llm-calls --runs runs_deepseek_real
```

Do not run them until `.env` contains a valid local `DEEPSEEK_API_KEY`.

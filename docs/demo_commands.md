# Demo Commands

## 1. Run all tests

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -vv -s
```

Expected result:

```text
27 passed
```

## 2. Run all benchmarks

```bash
PYTHONPATH=src python -m openagent_harness.cli eval --benchmarks benchmarks --runs runs_eval_final
```

Expected result:

```text
total=7
passed=7
failed=0
pass_rate=1.0
```

## 3. Inspect tool registry

```bash
PYTHONPATH=src python -m openagent_harness.cli tools .
```

## 4. Inspect code symbols

```bash
PYTHONPATH=src python -m openagent_harness.cli index src/openagent_harness --query agent
```

## 5. Run one task offline

```bash
PYTHONPATH=src python -m openagent_harness.cli run benchmarks/calc-py/task.json --runs runs_demo
```

## 6. Create DeepSeek API-mode placeholder

```bash
PYTHONPATH=src python -m openagent_harness.cli api-check examples/deepseek_task.json --model deepseek-v4-flash
```

## 7. Real DeepSeek run

```bash
export DEEPSEEK_API_KEY=your_key
PYTHONPATH=src python -m openagent_harness.cli run examples/deepseek_task.json \
  --mode api \
  --model deepseek-v4-flash \
  --allow-llm-calls
```

API calls are disabled by default. Use the real run only when you intentionally want to spend tokens.

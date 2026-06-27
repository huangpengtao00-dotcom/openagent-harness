# Demo Commands

## 1. Run all tests

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -vv -s
```

Expected result:

```text
all selected tests pass
```

## 2. Run the stable interview smoke on Windows

CMD:

```cmd
scripts\smoke_retry_429.cmd
```

PowerShell:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\smoke_retry_429.ps1
```

Expected result includes:

```text
status=pass
artifacts=...
```

## 3. Run all benchmarks

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

## 4. Inspect tool registry

```bash
PYTHONPATH=src python -m openagent_harness.cli tools .
```

## 5. Inspect code symbols

```bash
PYTHONPATH=src python -m openagent_harness.cli index src/openagent_harness --query agent
```

## 6. Run one task offline

```bash
PYTHONPATH=src python -m openagent_harness.cli run benchmarks/calc-py/task.json --runs runs_demo
```

## 7. Create DeepSeek API-mode placeholder

```bash
PYTHONPATH=src python -m openagent_harness.cli api-check examples/deepseek_real_task.json --model deepseek-v4-flash
```

## 8. Real DeepSeek run

```bash
export DEEPSEEK_API_KEY=your_key
PYTHONPATH=src python -m openagent_harness.cli run examples/deepseek_real_task.json \
  --mode api \
  --model deepseek-v4-flash \
  --allow-llm-calls
```

API calls are disabled by default. Use the real run only when you intentionally want to spend tokens and can save the evidence.

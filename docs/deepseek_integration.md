# DeepSeek / OpenAI-Compatible LLM Integration

This project now supports a guarded API path instead of only a placeholder.

## Why this matters

The previous version had a benchmark harness but no real model loop. The upgraded version adds:

1. OpenAI-compatible chat client using the Python standard library.
2. DeepSeek defaults: `deepseek-v4-flash` and `https://api.deepseek.com`.
3. JSON-action coding loop: model proposes one action per turn.
4. Local tool execution: read file, write allowlisted file, run safe command.
5. Permission policy: blocks path escape, out-of-scope writes, and risky shell commands.
6. Deterministic context compaction before each agent run.
7. Usage and approximate cost accounting.
8. Dry-run API configuration checks that never call the network.

## Safe dry run

```powershell
python -m openagent_harness.cli api-check benchmarks/calc-py/task.json --model deepseek-v4-flash
python -m openagent_harness.cli deepseek-check --model deepseek-v4-flash
```

## Render prompt context

```powershell
python -m openagent_harness.cli context benchmarks/calc-py/repo "fix zero division" --max-chars 20000
```

## Real LLM run

Use this only after setting an API key and accepting spend risk.

```powershell
$env:DEEPSEEK_API_KEY="sk-..."
python -m openagent_harness.cli run examples/deepseek_task.json --mode api --model deepseek-v4-flash --allow-llm-calls
```

`budget.enable_llm_calls` is intentionally false in the example. This prevents accidental API spend when a task file is copied into a demo.

## Design choices

- The model does not directly mutate the file system. It emits JSON actions.
- The harness executes those actions through local tools.
- The policy layer checks every write and every shell command.
- The quality gate remains separate from the agent. A confident model answer does not pass unless the artifacts pass.

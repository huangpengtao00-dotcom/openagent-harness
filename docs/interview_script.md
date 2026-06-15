# Interview Script

## 30-Second Pitch

OpenAgent Harness is a local-first evaluation harness for coding agents. Existing coding assistants can execute tasks, but I wanted a layer that asks: did the agent really finish, what evidence proves it, and why did it fail? The project runs a task against a repo, captures trace artifacts, generates a patch, runs tests, applies a quality gate, and classifies failures such as unverified patches or scope violations.

## 2-Minute Explanation

The core abstraction is `TaskSpec`: repo, goal, allowlist, acceptance checks, and budget. The runner copies the repo into an isolated run folder, executes either a deterministic local agent or an API-ready adapter, records JSONL and SQLite traces, writes a patch and test result, then lets `QualityGate` decide pass or fail.

The key engineering decision is that the final answer is not trusted. Only artifacts are trusted. If a patch exists but tests did not run, the system marks it `Unverified`. If tests fail, it is `Regression`. If the patch touches files outside the allowlist, it is `ScopeViolation`.

The current benchmark has 5 local tasks and can be run with one command: `python -m openagent_harness.cli eval --benchmarks benchmarks`. The baseline result is 5 passed, 0 failed, pass rate 1.0.

## Why Not Just Use A Hosted Assistant?

A coding assistant can be the executor. This project is the harness around the executor. It controls the task contract, budget, allowed files, traces, tests, and failure report. That makes model behavior comparable and reproducible.

## What I Would Improve Next

I would expand benchmarks from 5 to 10 tasks, add real LiteLLM calls behind budget controls, then add Docker for cleaner reproducibility. I would still keep the local scripted mode because interviews and demos should not depend on an API key.

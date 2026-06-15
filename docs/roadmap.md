# Project Roadmap

## P0: Interview-Ready Baseline

- Local no-API runner works.
- Five benchmark tasks pass.
- `eval` runs all benchmark task specs and writes `eval_summary.json`.
- Trace artifacts are written to JSONL and SQLite.
- Quality gate detects patch, tests, report, and scope.
- API mode records configuration without making paid calls.

## P1: Stronger Internship Portfolio

- Add 5 more benchmark tasks:
  - delete task cleans tag relationship
  - config value read from `DATABASE_URL`
  - auth required for edit/delete
  - CSV parser handles quoted commas
  - monorepo command delegates to package tests
- Add summary metrics beyond pass rate: average runtime and failure type counts.

## P2: API Mode

- Add LiteLLM call behind explicit `max_cost_usd`.
- Add retry and timeout controls.
- Record prompt tokens, completion tokens, and estimated cost in trace events.
- Keep local mode as the default.

## P3: Reproducibility

- Add Docker runner for benchmark repos.
- Freeze benchmark snapshots.
- Add a static HTML report only after the CLI flow is stable.

## Do Not Add Before First Interviews

- Multi-agent orchestration.
- RAG or vector database.
- Browser automation.
- Kubernetes or enterprise permission systems.

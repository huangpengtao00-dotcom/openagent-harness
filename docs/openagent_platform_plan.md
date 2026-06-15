# OpenAgent Platform Implementation Plan

> Status: planning document. Do not implement until the user approves this plan.

## Goal

Build **OpenAgent Platform**, a Go backend that manages AI Agent evaluation tasks and calls the existing Python **OpenAgent Harness** as the execution engine.

The final portfolio story should become:

```text
OpenAgent Harness = local agent evaluation engine
OpenAgent Platform = Go backend for task management, async execution, status tracking, trace/gate query, and high-concurrency controls
```

## Preflight Findings

- Existing Python Harness works.
- Verified command:

```powershell
python -m openagent_harness.cli eval --benchmarks benchmarks --runs C:\tmp\openagent_plan_check
```

- Observed result:

```text
total=5
passed=5
failed=0
pass_rate=1.0
```

- Current machine does **not** have `go` available in PATH.
- Current machine does **not** have `docker` available in PATH.

Implication:

- V1 must be designed to work after installing Go only.
- V2 can use Redis / MySQL / Docker after environment setup.
- No paid LLM API calls are part of this project.

## Recommended Architecture

```text
Client / Postman / curl
        |
        v
Go Gin API
        |
        +--> Task Service
        +--> Run Service
        +--> Gate / Trace Query Service
        +--> Idempotency / Rate Limit Service
        |
        v
Worker Pool / Queue
        |
        v
Harness Adapter
        |
        v
python -m openagent_harness.cli eval --benchmarks benchmarks --runs <artifact_dir>
        |
        v
eval_summary.json / gate.json / trace.jsonl
        |
        v
SQLite/MySQL + optional Redis cache
```

## Version Split

### V1: Local Runnable Version

Purpose: short-term learning and demo.

Tech stack:

```text
Go + Gin + GORM + SQLite + goroutine worker pool + Zap-style logging
```

V1 must include:

- `POST /api/tasks`
- `GET /api/tasks`
- `GET /api/tasks/:id`
- `POST /api/tasks/:id/runs`
- `GET /api/runs/:id`
- `GET /api/runs/:id/logs`
- `GET /api/runs/:id/gate`
- `POST /api/runs/:id/cancel`
- `GET /api/eval/summary`
- Local worker pool with max concurrency, for example 2 or 3.
- `context.WithTimeout` around Python Harness execution.
- Idempotency key for repeated run creation.
- Persistent records in SQLite.
- Tests for state transitions and service behavior.

V1 does not include:

- Frontend UI.
- Real user login.
- Paid model APIs.
- Redis.
- Docker.
- Distributed workers.

### V2: Backend Depth Version

Purpose: resume depth and backend interview talking points.

Tech stack:

```text
Go + Gin + GORM + MySQL + Redis + Asynq + Docker Compose + structured logs
```

V2 adds:

- MySQL instead of SQLite.
- Redis run-status cache.
- Redis-based rate limit.
- Asynq queue for async jobs.
- Retry policy and dead-letter queue.
- Docker Compose for API + MySQL + Redis.
- Small load test script.
- README benchmark screenshot / command output.

V2 does not include:

- Multi-tenant enterprise permissions.
- Kubernetes.
- Real model billing.
- Browser automation.
- Full observability stack such as Prometheus/Grafana unless everything else is stable.

## Data Model

### tasks

```text
id
name
repo_path
benchmark_path
mode
budget_json
created_at
updated_at
```

### runs

```text
id
task_id
status
idempotency_key
started_at
finished_at
pass_rate
failure_type
artifact_dir
error_message
created_at
updated_at
```

### gate_results

```text
id
run_id
has_diff
tests_ran
tests_passed
scope_ok
status
failure_type
raw_json
created_at
```

### trace_logs

```text
id
run_id
step
phase
message
tool_name
exit_code
raw_json
created_at
```

## Run State Machine

```text
PENDING -> RUNNING -> SUCCESS
                   -> FAILED
                   -> TIMEOUT
                   -> CANCELED
```

Rules:

- A run starts as `PENDING`.
- Worker changes it to `RUNNING`.
- Harness success with pass rate and parsed results becomes `SUCCESS`.
- Harness command failure or parsed gate failure becomes `FAILED`.
- Context timeout becomes `TIMEOUT`.
- User cancel request marks cancel intent; if the process can be stopped, final state becomes `CANCELED`.
- Terminal states cannot move back to non-terminal states.

## API Contract

### Create task

```http
POST /api/tasks
Content-Type: application/json

{
  "name": "local five benchmark eval",
  "repo_path": "C:/Users/hpt/Desktop/待处理/实习项目/OpenAgent-Harness",
  "benchmark_path": "benchmarks",
  "mode": "local",
  "budget": {
    "timeout_seconds": 60,
    "max_concurrency": 2
  }
}
```

### Start run

```http
POST /api/tasks/:id/runs
Idempotency-Key: demo-run-001
```

### Run response

```json
{
  "id": 1,
  "task_id": 1,
  "status": "PENDING",
  "artifact_dir": "runs/platform/run-1"
}
```

### Query run

```http
GET /api/runs/:id
```

### Query logs

```http
GET /api/runs/:id/logs
```

### Query gate

```http
GET /api/runs/:id/gate
```

## Project Structure

Create a new sibling project under the internship workspace:

```text
C:\Users\hpt\Desktop\待处理\实习项目\OpenAgent-Platform\
  cmd\server\main.go
  internal\api\router.go
  internal\api\handlers\
    task_handler.go
    run_handler.go
  internal\config\config.go
  internal\db\db.go
  internal\models\
    task.go
    run.go
    gate_result.go
    trace_log.go
  internal\service\
    task_service.go
    run_service.go
    idempotency_service.go
  internal\worker\
    pool.go
    job.go
  internal\harness\
    adapter.go
    parser.go
  internal\state\state.go
  internal\errors\errors.go
  tests\
  docs\
    tutorial_harness.md
    tutorial_platform.md
    interview_qa.md
  README.md
```

## Implementation Plan

### Phase 0: Environment

- Install Go 1.22+ or latest stable Go.
- Confirm:

```powershell
go version
python -m openagent_harness.cli eval --benchmarks benchmarks
```

- Do not install Docker until V2.

### Phase 1: V1 API and Storage

- Initialize Go module.
- Add Gin, GORM, SQLite driver.
- Create `Task`, `Run`, `GateResult`, `TraceLog` models.
- Add migration on startup.
- Implement task create/list/detail endpoints.
- Write tests for task service.

### Phase 2: V1 Worker and Harness Adapter

- Implement worker pool.
- Implement Harness adapter around:

```powershell
python -m openagent_harness.cli eval --benchmarks benchmarks --runs <artifact_dir>
```

- Parse `eval_summary.json`.
- Read representative `gate.json` and `trace.jsonl` artifacts.
- Update run state.
- Write tests for parser and state machine.

### Phase 3: V1 Controls

- Add idempotency key.
- Add timeout.
- Add cancel endpoint.
- Add run logs and gate query endpoints.
- Add README commands.
- Add tutorial docs.

### Phase 4: V2 Redis / Queue / MySQL

- Add Docker Compose.
- Add MySQL config.
- Add Redis cache.
- Add Asynq queue.
- Add rate limit middleware.
- Add retry policy and dead-letter recording.
- Add load test script.

## Tutorial Plan

### Tutorial A: OpenAgent Harness

Goal: understand the Python evaluation engine.

Lessons:

1. What problem Harness solves: False Success.
2. How `TaskSpec` describes a coding-agent task.
3. How `runner.py` copies repo, applies agent, runs tests, writes artifacts.
4. How `gate.py` decides pass/fail.
5. How `trace.py` records events.
6. How `eval.py` runs all benchmarks.
7. How to explain 5 benchmark tasks in interviews.

Practice:

```powershell
python -m pytest tests -q
python -m openagent_harness.cli eval --benchmarks benchmarks
```

Expected:

```text
14 passed
total=5
passed=5
failed=0
pass_rate=1.0
```

### Tutorial B: Go Backend V1

Goal: understand backend basics through the platform.

Lessons:

1. Go module and project layout.
2. Gin routing and handlers.
3. GORM models and SQLite persistence.
4. Service layer and state machine.
5. Worker pool and goroutine basics.
6. Calling Python from Go with timeout.
7. Parsing JSON artifacts.
8. Writing tests and README.

### Tutorial C: Go Backend V2

Goal: add backend interview depth.

Lessons:

1. MySQL schema and migrations.
2. Redis cache for run status.
3. Redis rate limiting.
4. Asynq queue and retries.
5. Idempotency and duplicate-submit protection.
6. Timeout, cancellation, and process cleanup.
7. Docker Compose local environment.
8. Resume explanation and Q&A.

## Multi-Layer Audit Gates

### Gate 1: Scope Audit

Pass criteria:

- V1 and V2 are separated.
- No frontend.
- No paid LLM APIs.
- No Docker dependency in V1.
- No unverified resume claims.

### Gate 2: Test Audit

Pass criteria:

- State machine tests pass.
- Parser tests pass.
- Task/run service tests pass.
- Harness adapter can be tested with a fake command runner.

### Gate 3: Integration Audit

Pass criteria:

- Starting a run through Go produces Harness artifacts.
- Go parses `eval_summary.json`.
- API returns run status and pass rate.

### Gate 4: Concurrency Audit

Pass criteria:

- Worker pool enforces max concurrency.
- Duplicate `Idempotency-Key` does not create duplicate active runs.
- Timeout produces `TIMEOUT`, not a stuck `RUNNING` state.

### Gate 5: Data Audit

Pass criteria:

- DB records match artifact files.
- Failed runs keep error message and artifact path.
- Trace query returns ordered events.

### Gate 6: Resume Audit

Pass criteria:

- Resume only claims completed features.
- V1 resume text does not mention Redis / Asynq / Docker until V2 is implemented.
- Metrics are reproducible from commands in README.

## Acceptance Criteria

### V1 is complete when:

- `go test ./...` passes.
- API starts locally.
- Can create a task.
- Can start a run.
- Run calls Python Harness.
- Run reaches `SUCCESS` with `pass_rate=1.0`.
- Can query logs and gate result.
- Tutorial docs exist.

### V2 is complete when:

- `docker compose up` starts API + MySQL + Redis.
- Asynq worker executes jobs.
- Redis rate limit works.
- Retry policy is demonstrated.
- README includes verified commands and outputs.

## Risks and Fallbacks

| Risk | Impact | Fallback |
|---|---|---|
| Go not installed | Cannot start implementation | Install Go first |
| Docker not installed | V2 blocked | Complete V1 first |
| Redis/MySQL setup slow | Environment drag | Keep SQLite/goroutine V1 as stable baseline |
| Python Harness path with Chinese characters | Command issues | Use absolute paths and quote paths carefully |
| Project becomes too large | Learning slows down | Freeze V1 scope before V2 |
| Resume overclaims | Interview risk | Resume audit after every milestone |

## Approval Needed Before Implementation

Recommended next action:

1. Install Go.
2. Implement V1 first.
3. Write Harness tutorial and Platform V1 tutorial.
4. Verify V1 end-to-end.
5. Only then start V2 Redis/MySQL/Asynq.

Implementation should not begin until this plan is approved.

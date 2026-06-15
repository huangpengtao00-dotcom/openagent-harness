# OpenAgent Harness Optimization Report

## What was improved

1. Full-repository diff snapshot
   - The runner now snapshots the whole working repo, not only files listed in `allowlist`.
   - `patch.diff` now records any changed text file and binary-file fingerprint changes.
   - This fixes the previous false-success risk where an agent could modify a file outside the allowlist without the gate seeing it.

2. Real acceptance-command execution
   - The runner now reads `acceptance` from `task.json`.
   - The shorthand `"pytest"` expands to `python -m pytest -q`.
   - Custom commands such as `python check_custom.py` are supported.
   - Acceptance commands stop at the first failure and write structured evidence into `test_result.json`.

3. Timeout-safe subprocess tool
   - `run_command` now supports `timeout_seconds`.
   - Timed-out commands return exit code `124` with `timed_out=true`, instead of hanging indefinitely.
   - The default acceptance timeout is 30 seconds and can be overridden with `budget.acceptance_timeout_seconds`.

4. Stronger test evidence
   - `test_result.json` now includes `commands`, per-command `exit_code`, `stdout`, `stderr`, `timed_out`, and `duration_seconds`.
   - The trace event now records all acceptance commands and their exit codes.

5. Regression tests added
   - Added a test proving `patch.diff` includes out-of-scope file modifications.
   - Added a test proving custom acceptance commands are actually used.

## Verification

```text
python -m pytest -q
16 passed
```

```text
PYTHONPATH=src python -m openagent_harness.cli eval --benchmarks benchmarks --runs runs_eval_new
total=5
passed=5
failed=0
pass_rate=1.0
```

## Interview value

The strongest improvement is not adding surface features. It closes a real evaluation loophole: previously, the harness could claim scope control while only diffing allowlisted files. Now the gate can detect changed files outside the allowlist, making the project more defensible as an agent-evaluation harness.

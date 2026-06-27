from __future__ import annotations

import difflib
import hashlib
import json
import shutil
import shlex
import uuid
from pathlib import Path

from .artifact_hygiene import write_artifact_hygiene, write_evidence_summary
from .context import ContextBuilder
from .env import sanitize_mapping
from .gate import QualityGate
from .html_report import write_run_html_report
from .ignore_rules import should_ignore_repo_path
from .llm import ProviderTransientError
from .model_adapter import ApiAgent, ScriptedAgent
from .schema import GateResult, RunMode, RunResult, TaskSpec, TraceEvent
from .tools import ToolResult, run_command
from .trace import JsonlTraceStore, SqliteTraceStore
from .workspace import WorkspaceManager


_DEFAULT_ACCEPTANCE_TIMEOUT_SECONDS = 30.0


class HarnessRunner:
    def __init__(
        self,
        mode: RunMode = "local",
        model: str = "scripted",
        *,
        base_url: str | None = None,
        api_key: str | None = None,
        allow_llm_calls: bool = False,
        wire_api: str | None = None,
        reasoning_effort: str | None = None,
        disable_response_storage: bool | None = None,
        failure_context: str | None = None,
    ) -> None:
        self.mode = mode
        self.model = model
        self.base_url = base_url
        self.api_key = api_key
        self.allow_llm_calls = allow_llm_calls
        self.wire_api = wire_api
        self.reasoning_effort = reasoning_effort
        self.disable_response_storage = disable_response_storage
        self.failure_context = failure_context

    def run_task(self, spec: TaskSpec, runs_root: Path) -> RunResult:
        run_id = f"{spec.id}-{uuid.uuid4().hex[:8]}"
        run_dir = runs_root / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        trace = JsonlTraceStore(run_dir / "trace.jsonl")
        sqlite_trace = SqliteTraceStore(run_dir / "trace.sqlite")

        self._append(trace, sqlite_trace, TraceEvent(run_id, spec.id, "spec", 1, spec.goal))

        if self.mode == "api" and not self._llm_calls_allowed(spec):
            return self._record_api_placeholder(spec, run_id, run_dir, trace, sqlite_trace)

        repo_dir = run_dir / "repo"
        workspace = WorkspaceManager().create(Path(spec.repo), repo_dir)
        self._write_task_artifacts(run_dir, repo_dir, spec)
        self._write_failure_context_artifact(run_dir)
        before = self._snapshot(repo_dir)
        self._append(
            trace,
            sqlite_trace,
            TraceEvent(
                run_id,
                spec.id,
                "act",
                2,
                "created isolated workspace and captured full baseline",
                observation={"workspace_strategy": workspace.strategy, "source_repo": str(workspace.source)},
            ),
        )

        if self.mode == "api":
            try:
                changed = self._apply_api_agent(spec, repo_dir, run_dir, trace, sqlite_trace, run_id)
            except ProviderTransientError as exc:
                return self._record_api_failure(spec, run_id, run_dir, repo_dir, before, trace, sqlite_trace, exc, "ProviderTransient")
            except RuntimeError as exc:
                return self._record_api_failure(spec, run_id, run_dir, repo_dir, before, trace, sqlite_trace, exc, "ApiRuntimeError")
        else:
            changed = self._apply_scripted_agent(spec, repo_dir, trace, sqlite_trace, run_id)

        after = self._snapshot(repo_dir)
        self._write_patch(run_dir / "patch.diff", before, after)
        test_results = self._run_acceptance(spec, repo_dir)
        self._cleanup_runtime_caches(repo_dir)
        tests_passed = self._write_test_results(run_dir, test_results)
        self._append(
            trace,
            sqlite_trace,
            TraceEvent(
                run_id,
                spec.id,
                "verify",
                4,
                "ran acceptance checks",
                tool={"name": "acceptance", "args": [" ".join(result.command) for result in test_results]},
                observation={
                    "tests_ran": len(test_results) > 0,
                    "tests_passed": tests_passed,
                    "exit_codes": [result.exit_code for result in test_results],
                    "changed": [self._relative_path(repo_dir, path) for path in changed if path.exists()],
                },
            ),
        )

        self._write_report(run_dir / "final_report.md", spec, tests_passed)
        write_artifact_hygiene(run_dir)
        gate = QualityGate().check_run(run_dir, spec)
        (run_dir / "gate.json").write_text(json.dumps(gate.to_dict(), indent=2), encoding="utf-8")
        scorecard = write_run_html_report(run_dir, gate)
        write_evidence_summary(run_dir)
        self._append(
            trace,
            sqlite_trace,
            TraceEvent(
                run_id,
                spec.id,
                "report",
                5,
                "generated scorecard and HTML report",
                observation={"score": scorecard.score, "html_report": "report.html"},
            ),
        )
        return RunResult(run_id, run_dir, gate)

    def _write_task_artifacts(self, run_dir: Path, repo_dir: Path, spec: TaskSpec) -> None:
        builder = ContextBuilder(repo_dir)
        index = builder.build_index(spec.goal)
        selected = builder.candidate_files(spec.goal, limit=int(spec.budget.get("context_summary_files", 12)))
        payload = {
            "task": {
                "id": spec.id,
                "repo": spec.repo,
                "goal": spec.goal,
                "allowlist": spec.allowlist,
                "acceptance": spec.acceptance or ["pytest"],
                "budget": spec.budget,
            },
            "context": {
                "total_files": len(index.files),
                "total_bytes": index.total_bytes,
                "selected_files": [file.__dict__ for file in selected],
                "skipped_files": index.skipped[:50],
            },
        }
        (run_dir / "task_spec.json").write_text(json.dumps(payload["task"], ensure_ascii=False, indent=2), encoding="utf-8")
        (run_dir / "context_summary.json").write_text(
            json.dumps(payload["context"], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _write_failure_context_artifact(self, run_dir: Path) -> None:
        if self.failure_context:
            (run_dir / "failure_context_input.txt").write_text(self.failure_context, encoding="utf-8")

    def _record_api_failure(
        self,
        spec: TaskSpec,
        run_id: str,
        run_dir: Path,
        repo_dir: Path,
        before: dict[str, str],
        trace: JsonlTraceStore,
        sqlite_trace: SqliteTraceStore,
        exc: Exception,
        failure_type: str,
    ) -> RunResult:
        message = str(exc)
        self._write_patch(run_dir / "patch.diff", before, self._snapshot(repo_dir))
        self._write_json_artifact(
            run_dir / "api_agent_run.json",
            {
                "finished": False,
                "summary": message,
                "steps": [],
                "changed_paths": [],
                "total_usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "estimated_cost_usd": 0.0},
                "failure_type": failure_type,
            },
        )
        self._write_json_artifact(
            run_dir / "test_result.json",
            {
                "tests_ran": False,
                "tests_passed": False,
                "command": "",
                "commands": [],
                "results": [],
                "stdout": "",
                "stderr": message,
            },
        )
        self._write_report(run_dir / "final_report.md", spec, False)
        write_artifact_hygiene(run_dir)
        gate = GateResult(False, False, False, True, True, "fail", failure_type)
        (run_dir / "gate.json").write_text(json.dumps(gate.to_dict(), indent=2), encoding="utf-8")
        scorecard = write_run_html_report(run_dir, gate)
        write_evidence_summary(run_dir)
        self._append(
            trace,
            sqlite_trace,
            TraceEvent(
                run_id,
                spec.id,
                "fail",
                3,
                "api provider failed before a verified patch was produced",
                observation={"failure_type": failure_type, "error": message, "score": scorecard.score},
            ),
        )
        return RunResult(run_id, run_dir, gate)

    def _apply_scripted_agent(
        self,
        spec: TaskSpec,
        repo_dir: Path,
        trace: JsonlTraceStore,
        sqlite_trace: SqliteTraceStore,
        run_id: str,
    ) -> list[Path]:
        changed = ScriptedAgent().apply(repo_dir, spec.goal)
        self._append(
            trace,
            sqlite_trace,
            TraceEvent(
                run_id,
                spec.id,
                "act",
                3,
                "scripted agent applied local patch",
                observation={"changed": [self._relative_path(repo_dir, path) for path in changed]},
            ),
        )
        return changed

    def _apply_api_agent(
        self,
        spec: TaskSpec,
        repo_dir: Path,
        run_dir: Path,
        trace: JsonlTraceStore,
        sqlite_trace: SqliteTraceStore,
        run_id: str,
    ) -> list[Path]:
        agent = ApiAgent(
            self.model,
            base_url=self.base_url,
            api_key=self.api_key,
            timeout_seconds=float(spec.budget.get("llm_timeout_seconds", 60.0)),
            max_tokens=int(spec.budget.get("llm_max_tokens", 2048)),
            thinking=spec.budget.get("thinking") if isinstance(spec.budget.get("thinking"), str) else None,
            reasoning_effort=self.reasoning_effort
            or (spec.budget.get("reasoning_effort") if isinstance(spec.budget.get("reasoning_effort"), str) else None),
            wire_api=self.wire_api,
            disable_response_storage=self.disable_response_storage,
        )
        if not agent.is_configured():
            raise RuntimeError("API mode was allowed but no API key is configured.")
        outcome = agent.apply(repo_dir, spec, failure_context=self.failure_context)
        self._write_json_artifact(run_dir / "api_agent_run.json", outcome.to_dict())
        self._append(
            trace,
            sqlite_trace,
            TraceEvent(
                run_id,
                spec.id,
                "act",
                3,
                "api agent loop executed",
                observation={
                    "finished": outcome.finished,
                    "steps": len(outcome.steps),
                    "summary": outcome.summary,
                    "usage": outcome.total_usage.to_dict(),
                    "changed": [self._relative_path(repo_dir, path) for path in outcome.changed_paths if path.exists()],
                },
            ),
        )
        return outcome.changed_paths

    def _llm_calls_allowed(self, spec: TaskSpec) -> bool:
        return self.allow_llm_calls or bool(spec.budget.get("enable_llm_calls"))

    def _record_api_placeholder(
        self,
        spec: TaskSpec,
        run_id: str,
        run_dir: Path,
        trace: JsonlTraceStore,
        sqlite_trace: SqliteTraceStore,
    ) -> RunResult:
        config = ApiAgent(
            self.model,
            base_url=self.base_url,
            api_key=self.api_key,
            wire_api=self.wire_api,
            reasoning_effort=self.reasoning_effort,
            disable_response_storage=self.disable_response_storage,
        ).configuration_note()
        self._write_json_artifact(run_dir / "api_mode.json", config)
        (run_dir / "patch.diff").write_text("", encoding="utf-8")
        write_artifact_hygiene(run_dir)
        gate = GateResult(False, False, False, True, False, "fail", "ApiNotConfigured")
        (run_dir / "gate.json").write_text(json.dumps(gate.to_dict(), indent=2), encoding="utf-8")
        write_evidence_summary(run_dir)
        self._append(
            trace,
            sqlite_trace,
            TraceEvent(run_id, spec.id, "act", 2, "api mode recorded but not executed", observation=config),
        )
        return RunResult(run_id, run_dir, gate)

    def _snapshot(self, repo_dir: Path) -> dict[str, str]:
        snapshot: dict[str, str] = {}
        for path in sorted(repo_dir.rglob("*")):
            if not path.is_file() or self._should_ignore(path, repo_dir):
                continue
            raw = path.read_bytes()
            try:
                content = raw.decode("utf-8")
            except UnicodeDecodeError:
                digest = hashlib.sha256(raw).hexdigest()
                content = f"<binary sha256={digest} size={len(raw)}>\n"
            snapshot[self._relative_path(repo_dir, path)] = content
        return snapshot

    def _write_patch(self, patch_path: Path, before: dict[str, str], after: dict[str, str]) -> None:
        chunks: list[str] = []
        for normalized in sorted(before.keys() | after.keys()):
            old = before.get(normalized, "")
            new = after.get(normalized, "")
            if old == new:
                continue
            chunks.append(f"diff --git a/{normalized} b/{normalized}\n")
            chunks.extend(
                difflib.unified_diff(
                    old.splitlines(keepends=True),
                    new.splitlines(keepends=True),
                    fromfile=f"a/{normalized}" if normalized in before else "/dev/null",
                    tofile=f"b/{normalized}" if normalized in after else "/dev/null",
                )
            )
        patch_path.write_text("".join(chunks), encoding="utf-8")

    def _run_acceptance(self, spec: TaskSpec, repo_dir: Path) -> list[ToolResult]:
        timeout_seconds = float(spec.budget.get("acceptance_timeout_seconds", _DEFAULT_ACCEPTANCE_TIMEOUT_SECONDS))
        results: list[ToolResult] = []
        for command in self._acceptance_commands(spec):
            env = self._acceptance_env(spec, command)
            result = run_command(command, repo_dir, timeout_seconds=timeout_seconds, env=env)
            results.append(result)
            if result.exit_code != 0:
                break
        return results

    def _write_test_results(self, run_dir: Path, test_results: list[ToolResult]) -> bool:
        tests_ran = len(test_results) > 0
        tests_passed = tests_ran and all(result.exit_code == 0 for result in test_results)
        self._write_json_artifact(
            run_dir / "test_result.json",
            {
                "tests_ran": tests_ran,
                "tests_passed": tests_passed,
                "command": " && ".join(" ".join(result.command) for result in test_results),
                "commands": [" ".join(result.command) for result in test_results],
                "results": [
                    {
                        "command": " ".join(result.command),
                        "exit_code": result.exit_code,
                        "stdout": result.stdout,
                        "stderr": result.stderr,
                        "timed_out": result.timed_out,
                        "duration_seconds": result.duration_seconds,
                    }
                    for result in test_results
                ],
                "stdout": "\n".join(result.stdout for result in test_results),
                "stderr": "\n".join(result.stderr for result in test_results),
            },
        )
        return tests_passed

    def _acceptance_commands(self, spec: TaskSpec) -> list[list[str]]:
        raw_commands = spec.acceptance or ["pytest"]
        commands: list[list[str]] = []
        for raw in raw_commands:
            command = raw.strip()
            if not command:
                continue
            if command == "pytest":
                commands.append(["python", "-m", "pytest", "-q"])
            else:
                commands.append(shlex.split(command))
        return commands

    def _acceptance_env(self, spec: TaskSpec, command: list[str]) -> dict[str, str]:
        disables_pytest_plugins = bool(spec.budget.get("disable_pytest_plugin_autoload", True))
        if disables_pytest_plugins and any(part == "pytest" or part.endswith("pytest") for part in command):
            return {"PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1"}
        return {}

    def _write_report(self, report_path: Path, spec: TaskSpec, tests_passed: bool) -> None:
        report_path.write_text(
            "# Final Report\n\n"
            f"- Task: {spec.id}\n"
            f"- Goal: {spec.goal}\n"
            f"- Mode: {self.mode}\n"
            f"- Model: {self.model}\n"
            f"- Acceptance: {', '.join(spec.acceptance or ['pytest'])}\n"
            f"- Tests passed: {tests_passed}\n"
            "- Gate source of truth: gate.json\n",
            encoding="utf-8",
        )

    def _cleanup_runtime_caches(self, repo_dir: Path) -> None:
        for name in ("__pycache__", ".pytest_cache"):
            for path in repo_dir.rglob(name):
                if path.is_dir():
                    shutil.rmtree(path, ignore_errors=True)

    def _append(self, jsonl: JsonlTraceStore, sqlite: SqliteTraceStore, event: TraceEvent) -> None:
        jsonl.append(event)
        sqlite.append(event)

    def _write_json_artifact(self, path: Path, payload: dict[str, object]) -> None:
        path.write_text(json.dumps(sanitize_mapping(payload), ensure_ascii=False, indent=2), encoding="utf-8")

    def _relative_path(self, repo_dir: Path, path: Path) -> str:
        """Return a stable repo-relative path across Windows/Unix and absolute/relative inputs."""
        repo_root = repo_dir.resolve()
        candidate = path.resolve()
        try:
            return candidate.relative_to(repo_root).as_posix()
        except ValueError:
            # Some tools may return a relative path while run_dir/repo_dir is also relative.
            # Fall back to lexical relative_to before failing with a useful value.
            try:
                return path.relative_to(repo_dir).as_posix()
            except ValueError:
                return candidate.as_posix()

    def _should_ignore(self, path: Path, repo_dir: Path) -> bool:
        return should_ignore_repo_path(path.resolve(), repo_dir.resolve())

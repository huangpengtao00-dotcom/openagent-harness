from __future__ import annotations

import difflib
import hashlib
import json
import shlex
import uuid
from pathlib import Path

from .context import ContextBuilder
from .gate import QualityGate
from .html_report import write_run_html_report
from .model_adapter import ApiAgent, ScriptedAgent
from .schema import GateResult, RunMode, RunResult, TaskSpec, TraceEvent
from .tools import ToolResult, run_command
from .trace import JsonlTraceStore, SqliteTraceStore
from .workspace import WorkspaceManager


_IGNORED_DIRS = {".git", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"}
_IGNORED_SUFFIXES = {".pyc", ".pyo", ".sqlite", ".db"}
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
    ) -> None:
        self.mode = mode
        self.model = model
        self.base_url = base_url
        self.api_key = api_key
        self.allow_llm_calls = allow_llm_calls

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
            changed = self._apply_api_agent(spec, repo_dir, run_dir, trace, sqlite_trace, run_id)
        else:
            changed = self._apply_scripted_agent(spec, repo_dir, trace, sqlite_trace, run_id)

        after = self._snapshot(repo_dir)
        self._write_patch(run_dir / "patch.diff", before, after)
        test_results = self._run_acceptance(spec, repo_dir)
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
        gate = QualityGate().check_run(run_dir, spec)
        (run_dir / "gate.json").write_text(json.dumps(gate.to_dict(), indent=2), encoding="utf-8")
        scorecard = write_run_html_report(run_dir, gate)
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
            reasoning_effort=spec.budget.get("reasoning_effort") if isinstance(spec.budget.get("reasoning_effort"), str) else None,
        )
        if not agent.is_configured():
            raise RuntimeError("API mode was allowed but no API key is configured.")
        outcome = agent.apply(repo_dir, spec)
        (run_dir / "api_agent_run.json").write_text(json.dumps(outcome.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
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
        config = ApiAgent(self.model, base_url=self.base_url, api_key=self.api_key).configuration_note()
        (run_dir / "api_mode.json").write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
        (run_dir / "patch.diff").write_text("", encoding="utf-8")
        gate = GateResult(False, False, False, True, False, "fail", "ApiNotConfigured")
        (run_dir / "gate.json").write_text(json.dumps(gate.to_dict(), indent=2), encoding="utf-8")
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
        (run_dir / "test_result.json").write_text(
            json.dumps(
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
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
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

    def _append(self, jsonl: JsonlTraceStore, sqlite: SqliteTraceStore, event: TraceEvent) -> None:
        jsonl.append(event)
        sqlite.append(event)

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
        relative = Path(self._relative_path(repo_dir, path))
        if any(part in _IGNORED_DIRS for part in relative.parts):
            return True
        return path.suffix in _IGNORED_SUFFIXES

from __future__ import annotations

import json
import shlex
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable

from .code_index import build_code_index, grep_repo
from .policy import PermissionPolicy
from .tools import ToolResult, run_command


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, object]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class ToolCallResult:
    ok: bool
    data: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

    def to_observation(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"ok": self.ok}
        if self.error:
            payload["error"] = self.error
        payload.update(self.data)
        return payload


class LocalToolRegistry:
    """Auditable local tool layer for coding agents.

    The registry is intentionally small but extensible. Adding a tool means adding its schema and
    one handler, instead of changing the agent loop itself.
    """

    def __init__(self, repo_dir: Path, policy: PermissionPolicy, *, timeout_seconds: float = 30.0) -> None:
        self.repo_dir = repo_dir
        self.policy = policy
        self.timeout_seconds = timeout_seconds
        self._handlers: dict[str, Callable[[dict[str, Any]], ToolCallResult]] = {
            "read_file": self._read_file,
            "write_file": self._write_file,
            "edit_file": self._edit_file,
            "run_command": self._run_command,
            "search_repo": self._search_repo,
            "inspect_symbols": self._inspect_symbols,
        }

    def specs(self) -> list[ToolSpec]:
        return [
            ToolSpec("read_file", "Read a UTF-8 text file from the repository.", {"path": "string"}),
            ToolSpec(
                "write_file",
                "Replace a full allowlisted file. Use only when local edit is unsafe.",
                {"path": "string", "content": "string"},
            ),
            ToolSpec(
                "edit_file",
                "Patch an allowlisted file by replacing exact old_text with new_text.",
                {"path": "string", "old_text": "string", "new_text": "string", "expected_replacements": "integer?"},
            ),
            ToolSpec("run_command", "Run a policy-approved test/lint/build command.", {"command": "string"}),
            ToolSpec(
                "search_repo",
                "Search text files for relevant lines.",
                {"query": "string", "limit": "integer?"},
            ),
            ToolSpec(
                "inspect_symbols",
                "Inspect Python functions/classes using AST indexing.",
                {"query": "string?", "limit": "integer?"},
            ),
        ]

    def specs_json(self) -> str:
        return json.dumps([spec.to_dict() for spec in self.specs()], ensure_ascii=False, indent=2)

    def dispatch(self, action: str, payload: dict[str, Any]) -> ToolCallResult:
        handler = self._handlers.get(action)
        if handler is None:
            return ToolCallResult(False, error=f"Unknown action: {action}")
        try:
            return handler(payload)
        except Exception as exc:  # noqa: BLE001 - local tools should surface structured failures to the agent.
            return ToolCallResult(False, error=f"{type(exc).__name__}: {exc}")

    def _read_file(self, payload: dict[str, Any]) -> ToolCallResult:
        path = str(payload.get("path", ""))
        decision = self.policy.check_read_path(path)
        if not decision.allowed:
            return ToolCallResult(False, error=decision.reason)
        file_path = self.repo_dir / path
        return ToolCallResult(True, {"path": path, "content": file_path.read_text(encoding="utf-8", errors="replace")})

    def _write_file(self, payload: dict[str, Any]) -> ToolCallResult:
        path = str(payload.get("path", ""))
        content = str(payload.get("content", ""))
        decision = self.policy.check_write_path(path)
        if not decision.allowed:
            return ToolCallResult(False, error=decision.reason)
        file_path = self.repo_dir / path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        if file_path.exists():
            content = _adapt_to_newline_style(content, _dominant_newline(_read_text_preserve_newlines(file_path)))
        _write_text_preserve_newlines(file_path, content)
        return ToolCallResult(True, {"path": path, "bytes": len(content.encode("utf-8")), "edit_type": "full_replace"})

    def _edit_file(self, payload: dict[str, Any]) -> ToolCallResult:
        path = str(payload.get("path", ""))
        old_text = str(payload.get("old_text", ""))
        new_text = str(payload.get("new_text", ""))
        expected = payload.get("expected_replacements", 1)
        expected_replacements = int(expected) if isinstance(expected, int | str) and str(expected).isdigit() else 1
        decision = self.policy.check_write_path(path)
        if not decision.allowed:
            return ToolCallResult(False, error=decision.reason)
        if not old_text:
            return ToolCallResult(False, error="old_text must be non-empty for edit_file.")
        file_path = self.repo_dir / path
        text = _read_text_preserve_newlines(file_path)
        edit_old, edit_new, count = _select_newline_aware_edit(text, old_text, new_text)
        if count != expected_replacements:
            return ToolCallResult(
                False,
                {"path": path, "matches": count, "expected_replacements": expected_replacements},
                error="Exact edit anchor count mismatch.",
            )
        _write_text_preserve_newlines(file_path, text.replace(edit_old, edit_new, expected_replacements))
        return ToolCallResult(
            True,
            {
                "path": path,
                "replacements": expected_replacements,
                "bytes_delta": len(edit_new.encode("utf-8")) - len(edit_old.encode("utf-8")),
                "edit_type": "search_replace",
            },
        )

    def _run_command(self, payload: dict[str, Any]) -> ToolCallResult:
        command = str(payload.get("command", ""))
        decision = self.policy.check_shell_command(command)
        if not decision.allowed:
            return ToolCallResult(False, error=decision.reason)
        parts = shlex.split(command)
        env = {"PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1"} if any(part == "pytest" or part.endswith("pytest") for part in parts) else None
        result: ToolResult = run_command(parts, self.repo_dir, timeout_seconds=self.timeout_seconds, env=env)
        return ToolCallResult(
            result.exit_code == 0,
            {
                "command": command,
                "exit_code": result.exit_code,
                "stdout": result.stdout[-4000:],
                "stderr": result.stderr[-4000:],
                "timed_out": result.timed_out,
                "duration_seconds": result.duration_seconds,
            },
        )

    def _search_repo(self, payload: dict[str, Any]) -> ToolCallResult:
        query = str(payload.get("query", ""))
        limit = int(payload.get("limit", 20) or 20)
        return ToolCallResult(True, {"query": query, "hits": [hit.to_dict() for hit in grep_repo(self.repo_dir, query, limit=limit)]})

    def _inspect_symbols(self, payload: dict[str, Any]) -> ToolCallResult:
        query = str(payload.get("query", ""))
        limit = int(payload.get("limit", 20) or 20)
        index = build_code_index(self.repo_dir)
        symbols = index.search_symbols(query, limit=limit) if query else index.symbols[:limit]
        return ToolCallResult(
            True,
            {
                "files_indexed": index.files_indexed,
                "errors": index.errors,
                "symbols": [symbol.to_dict() for symbol in symbols],
            },
        )


def _read_text_preserve_newlines(path: Path) -> str:
    with path.open("r", encoding="utf-8", errors="replace", newline="") as handle:
        return handle.read()


def _write_text_preserve_newlines(path: Path, text: str) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        handle.write(text)


def _dominant_newline(text: str) -> str:
    crlf = text.count("\r\n")
    lf = text.count("\n") - crlf
    cr = text.count("\r") - crlf
    if crlf >= lf and crlf >= cr and crlf > 0:
        return "\r\n"
    if cr > lf and cr > 0:
        return "\r"
    return "\n"


def _adapt_to_newline_style(text: str, newline: str) -> str:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    return normalized.replace("\n", newline)


def _select_newline_aware_edit(file_text: str, old_text: str, new_text: str) -> tuple[str, str, int]:
    direct_count = file_text.count(old_text)
    if direct_count:
        return old_text, new_text, direct_count
    newline = _dominant_newline(file_text)
    adapted_old = _adapt_to_newline_style(old_text, newline)
    adapted_new = _adapt_to_newline_style(new_text, newline)
    adapted_count = file_text.count(adapted_old)
    if adapted_count:
        return adapted_old, adapted_new, adapted_count
    return old_text, new_text, direct_count

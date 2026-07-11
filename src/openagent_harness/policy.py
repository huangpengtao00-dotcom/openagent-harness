from __future__ import annotations

import fnmatch
import shlex
from dataclasses import dataclass
from pathlib import Path


def normalize_repo_pattern(pattern: str) -> str:
    return pattern.replace("\\", "/").strip()


def is_path_allowed_by_patterns(path: str, allowlist: list[str]) -> bool:
    """Return whether a repo-relative path is allowed by task allowlist patterns.

    This helper is shared by the runtime policy and the post-run quality gate so
    an agent is not allowed during execution and rejected later by different
    matching semantics. Patterns use fnmatch, so entries such as ``src/*.py``
    and ``*`` work consistently across both layers.
    """
    normalized = normalize_repo_pattern(path)
    patterns = [normalize_repo_pattern(item) for item in allowlist if normalize_repo_pattern(item)]
    return any(fnmatch.fnmatch(normalized, pattern) for pattern in patterns)


_DANGEROUS_SHELL_PATTERNS = [
    "rm -rf",
    "del /s",
    "format ",
    "mkfs",
    "shutdown",
    "reboot",
    "curl *|*sh",
    "wget *|*sh",
    "Invoke-Expression",
    "irm *|*iex",
    "iwr *|*iex",
    "git push",
    "git reset --hard",
    "chmod 777",
]

_DEFAULT_COMMAND_PREFIXES = [
    "python",
    "python3",
    "py",
    "pytest",
    "uv",
    "ruff",
    "mypy",
]
_ALLOWED_PYTHON_MODULES = {"pytest", "compileall", "mypy", "ruff"}
_ALLOWED_UV_SUBCOMMANDS = {"run"}


@dataclass(frozen=True)
class PolicyDecision:
    allowed: bool
    reason: str


class PermissionPolicy:
    """Local safety boundary for an agent loop.

    It is intentionally conservative: writes must be inside the task allowlist and shell commands must
    look like test/lint/build commands unless the task explicitly widens the budget policy.
    """

    def __init__(self, repo_dir: Path, allowlist: list[str], budget: dict[str, object] | None = None) -> None:
        self.repo_dir = repo_dir.resolve()
        self.allowlist = [normalize_repo_pattern(item) for item in allowlist]
        self.budget = budget or {}
        configured = self.budget.get("allowed_command_prefixes")
        if isinstance(configured, list) and all(isinstance(item, str) for item in configured):
            self.allowed_command_prefixes = configured
        else:
            self.allowed_command_prefixes = _DEFAULT_COMMAND_PREFIXES

    def check_read_path(self, path: str) -> PolicyDecision:
        resolved = self._resolve_repo_path(path)
        if resolved is None:
            return PolicyDecision(False, "Path escapes repository.")
        if not resolved.exists():
            return PolicyDecision(False, "Path does not exist.")
        if not resolved.is_file():
            return PolicyDecision(False, "Path is not a regular file.")
        return PolicyDecision(True, "Read allowed.")

    def check_write_path(self, path: str) -> PolicyDecision:
        resolved = self._resolve_repo_path(path)
        if resolved is None:
            return PolicyDecision(False, "Path escapes repository.")
        normalized = resolved.relative_to(self.repo_dir).as_posix()
        if not self.allowlist:
            return PolicyDecision(False, "Task allowlist is empty; writes are blocked.")
        if is_path_allowed_by_patterns(normalized, self.allowlist):
            return PolicyDecision(True, "Write allowed by task allowlist.")
        return PolicyDecision(False, f"Write blocked: {normalized} is outside allowlist {self.allowlist}.")

    def check_shell_command(self, command: str | list[str]) -> PolicyDecision:
        text = command if isinstance(command, str) else " ".join(command)
        compact = " ".join(text.strip().split())
        if not compact:
            return PolicyDecision(False, "Empty command blocked.")
        for pattern in _DANGEROUS_SHELL_PATTERNS:
            if fnmatch.fnmatch(compact, pattern) or pattern in compact:
                return PolicyDecision(False, f"Dangerous shell pattern blocked: {pattern}")
        try:
            parts = shlex.split(compact)
        except ValueError as exc:
            return PolicyDecision(False, f"Invalid shell command: {exc}")
        if not parts:
            return PolicyDecision(False, "Empty command blocked.")
        binary = Path(parts[0]).name
        if binary in {"python", "python3", "py"}:
            return self._check_python_command(parts)
        if binary == "uv":
            return self._check_uv_command(parts)
        if any(binary == prefix or compact.startswith(prefix + " ") for prefix in self.allowed_command_prefixes):
            return PolicyDecision(True, "Command allowed by prefix policy.")
        return PolicyDecision(False, f"Command blocked by prefix policy: {binary}")

    def _resolve_repo_path(self, path: str) -> Path | None:
        candidate = (self.repo_dir / path).resolve()
        try:
            candidate.relative_to(self.repo_dir)
        except ValueError:
            return None
        return candidate

    def _check_python_command(self, parts: list[str]) -> PolicyDecision:
        if len(parts) == 1:
            return PolicyDecision(False, "Interactive Python commands are blocked.")
        first_arg = parts[1]
        if first_arg in {"-c", "--command"}:
            return PolicyDecision(False, "Inline Python execution is blocked.")
        if first_arg == "-m":
            if len(parts) < 3:
                return PolicyDecision(False, "Python module command is missing a module name.")
            module = parts[2]
            if module in _ALLOWED_PYTHON_MODULES:
                return PolicyDecision(True, "Python module command allowed by policy.")
            return PolicyDecision(False, f"Python module blocked by policy: {module}")
        if first_arg.startswith("-"):
            return PolicyDecision(False, f"Python flag blocked by policy: {first_arg}")
        script = self._resolve_repo_path(first_arg)
        if script is None:
            return PolicyDecision(False, "Python script path escapes repository.")
        if script.suffix != ".py":
            return PolicyDecision(False, "Python direct execution is limited to repo .py files.")
        if not script.exists() or not script.is_file():
            return PolicyDecision(False, "Python script does not exist.")
        return PolicyDecision(True, "Repo Python script command allowed by policy.")

    def _check_uv_command(self, parts: list[str]) -> PolicyDecision:
        if len(parts) < 2 or parts[1] not in _ALLOWED_UV_SUBCOMMANDS:
            return PolicyDecision(False, "uv command is limited to explicit test/lint run commands.")
        if len(parts) >= 3 and parts[2] in {"pytest", "ruff", "mypy"}:
            return PolicyDecision(True, "uv run command allowed by policy.")
        if len(parts) >= 5 and parts[2] in {"python", "python3", "py"} and parts[3] == "-m" and parts[4] in _ALLOWED_PYTHON_MODULES:
            return PolicyDecision(True, "uv run Python module command allowed by policy.")
        return PolicyDecision(False, "uv command target blocked by policy.")

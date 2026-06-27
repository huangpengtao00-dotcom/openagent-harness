from __future__ import annotations

import os
import signal
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path


_SECRET_ENV_MARKERS = ("KEY", "SECRET", "TOKEN", "PASSWORD", "CREDENTIAL")
_SAFE_ENV_ALLOWLIST = {
    "PATH",
    "PATHEXT",
    "SYSTEMROOT",
    "WINDIR",
    "COMSPEC",
    "TEMP",
    "TMP",
    "TMPDIR",
    "HOME",
    "USERPROFILE",
    "PYTHONPATH",
    "PYTHONIOENCODING",
    "PYTHONDONTWRITEBYTECODE",
    "PYTEST_DISABLE_PLUGIN_AUTOLOAD",
    "VIRTUAL_ENV",
}


@dataclass(frozen=True)
class ToolResult:
    command: list[str]
    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool = False
    duration_seconds: float = 0.0


def _coerce_timeout_output(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def _kill_process_tree(process: subprocess.Popen[str]) -> None:
    """Best-effort termination for timed-out tool commands.

    Acceptance commands often run test runners that may spawn children. Killing only
    the direct child can leave orphaned processes and make full-suite tests or demos
    appear to hang, so POSIX runs use a new process session and kill the process group.
    """
    if process.poll() is not None:
        return
    try:
        if os.name == "posix":
            os.killpg(process.pid, signal.SIGKILL)
        else:  # pragma: no cover - Windows-specific fallback.
            process.kill()
    except ProcessLookupError:
        return


def run_command(
    command: list[str],
    cwd: Path,
    timeout_seconds: float | None = None,
    env: dict[str, str] | None = None,
) -> ToolResult:
    """Run a subprocess and return structured evidence for the quality gate."""
    started = time.monotonic()
    merged_env = _safe_child_environment()
    # Keep acceptance subprocesses isolated from a parent pytest session.
    # Without this, nested pytest invocations can inherit PYTEST_CURRENT_TEST and
    # become flaky or slow in full-suite runs.
    merged_env.pop("PYTEST_CURRENT_TEST", None)
    if env:
        merged_env.update(env)

    creationflags = 0
    start_new_session = False
    if os.name == "posix":
        start_new_session = True
    elif os.name == "nt":  # pragma: no cover - Windows-only constant.
        creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)

    process = subprocess.Popen(
        command,
        cwd=str(cwd),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=merged_env,
        start_new_session=start_new_session,
        creationflags=creationflags,
    )
    try:
        stdout, stderr = process.communicate(timeout=timeout_seconds)
        return ToolResult(
            command=command,
            exit_code=int(process.returncode or 0),
            stdout=stdout,
            stderr=stderr,
            timed_out=False,
            duration_seconds=round(time.monotonic() - started, 4),
        )
    except subprocess.TimeoutExpired as exc:
        _kill_process_tree(process)
        stdout, stderr = process.communicate()
        timeout_msg = f"Command timed out after {timeout_seconds} seconds."
        stderr = _coerce_timeout_output(stderr or exc.stderr)
        if stderr:
            stderr = stderr.rstrip() + "\n" + timeout_msg
        else:
            stderr = timeout_msg
        return ToolResult(
            command=command,
            exit_code=124,
            stdout=_coerce_timeout_output(stdout or exc.stdout),
            stderr=stderr,
            timed_out=True,
            duration_seconds=round(time.monotonic() - started, 4),
        )


def _safe_child_environment() -> dict[str, str]:
    env: dict[str, str] = {}
    for key, value in os.environ.items():
        upper = key.upper()
        if upper in _SAFE_ENV_ALLOWLIST or upper.startswith(("PYTEST_", "PYTHON")):
            env[key] = value
            continue
        if any(marker in upper for marker in _SECRET_ENV_MARKERS):
            continue
        if upper in {"LANG", "LC_ALL", "NUMBER_OF_PROCESSORS", "PROCESSOR_ARCHITECTURE"}:
            env[key] = value
    return env

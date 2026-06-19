from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Mapping

_SECRET_NAME_RE = re.compile(r"(api[_-]?key|access[_-]?token|refresh[_-]?token|id[_-]?token|secret|password|authorization)", re.IGNORECASE)
_SECRET_VALUE_RE = re.compile(r"(?i)(sk-[A-Za-z0-9_\-]{4,}|Bearer\s+[A-Za-z0-9._\-+/=]+)")


def load_env_file(path: Path | str = ".env", *, override: bool = False) -> dict[str, str]:
    """Load a minimal dotenv file without adding a runtime dependency.

    Only KEY=VALUE lines are supported. Quotes are stripped. Lines beginning with '#'
    and blank lines are ignored. Existing environment variables are preserved unless
    ``override=True`` is passed.
    """
    env_path = Path(path)
    loaded: dict[str, str] = {}
    if not env_path.exists() or not env_path.is_file():
        return loaded

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key.lower().startswith("export "):
            key = key[7:].strip()
        value = value.strip().strip('"').strip("'")
        if not key:
            continue
        if override or key not in os.environ:
            os.environ[key] = value
            loaded[key] = value
    return loaded


def redact_secret(value: object) -> object:
    """Redact values before writing logs, reports, or support output."""
    if value is None:
        return None
    if not isinstance(value, str):
        return value
    if not value:
        return value
    redacted = _SECRET_VALUE_RE.sub("<redacted>", value)
    if len(redacted) > 12 and (redacted.startswith("sk-") or redacted.lower().startswith("bearer ")):
        return redacted[:4] + "..." + redacted[-4:]
    return redacted


def sanitize_mapping(mapping: Mapping[str, object]) -> dict[str, object]:
    sanitized: dict[str, object] = {}
    for key, value in mapping.items():
        if _SECRET_NAME_RE.search(key):
            sanitized[key] = "<redacted>" if value else value
        elif isinstance(value, Mapping):
            sanitized[key] = sanitize_mapping(value)  # type: ignore[arg-type]
        elif isinstance(value, list):
            sanitized[key] = [sanitize_mapping(v) if isinstance(v, Mapping) else redact_secret(v) for v in value]
        else:
            sanitized[key] = redact_secret(value)
    return sanitized


def safe_env_status(names: list[str]) -> dict[str, bool]:
    return {name: bool(os.getenv(name)) for name in names}

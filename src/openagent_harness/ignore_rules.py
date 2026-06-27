from __future__ import annotations

from pathlib import Path


IGNORED_DIR_NAMES = {
    ".git",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "node_modules",
    ".venv",
    "runs",
    "runs_deepseek",
    "runs_deepseek_real",
    "artifacts",
}
IGNORED_FILE_NAMES = {
    ".env",
    ".env.local",
    ".env.development",
    ".env.test",
    ".env.production",
}
IGNORED_SUFFIXES = {
    ".pyc",
    ".pyo",
    ".sqlite",
    ".db",
}


def should_ignore_repo_path(path: Path, repo_dir: Path) -> bool:
    relative = path.relative_to(repo_dir)
    if any(part in IGNORED_DIR_NAMES for part in relative.parts[:-1]):
        return True
    if path.name in IGNORED_FILE_NAMES:
        return True
    return path.suffix in IGNORED_SUFFIXES

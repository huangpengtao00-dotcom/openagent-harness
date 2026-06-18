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


def should_ignore_repo_name(name: str) -> bool:
    if name in IGNORED_DIR_NAMES or name in IGNORED_FILE_NAMES:
        return True
    if name.startswith("runs_"):
        return True
    return name.startswith(".env.")


def should_ignore_repo_path(path: Path, repo_dir: Path) -> bool:
    relative = path.relative_to(repo_dir)
    if any(should_ignore_repo_name(part) for part in relative.parts[:-1]):
        return True
    if should_ignore_repo_name(path.name):
        return True
    return path.suffix in IGNORED_SUFFIXES

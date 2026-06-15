from __future__ import annotations

import ast
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

_IGNORED_PARTS = {".git", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", "node_modules", ".venv"}


@dataclass(frozen=True)
class SymbolRecord:
    path: str
    name: str
    kind: str
    line: int
    signature: str = ""
    doc: str = ""

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class SearchHit:
    path: str
    line: int
    text: str
    score: int

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class CodeIndex:
    symbols: list[SymbolRecord]
    files_indexed: int
    errors: dict[str, str]

    def to_dict(self) -> dict[str, object]:
        return {
            "files_indexed": self.files_indexed,
            "symbols": [symbol.to_dict() for symbol in self.symbols],
            "errors": self.errors,
        }

    def search_symbols(self, query: str, limit: int = 20) -> list[SymbolRecord]:
        tokens = _tokens(query)
        scored: list[tuple[int, SymbolRecord]] = []
        for symbol in self.symbols:
            haystack = f"{symbol.path} {symbol.name} {symbol.kind} {symbol.signature}".lower()
            score = sum(4 for token in tokens if token in symbol.name.lower()) + sum(1 for token in tokens if token in haystack)
            if score > 0:
                scored.append((score, symbol))
        return [symbol for _, symbol in sorted(scored, key=lambda item: (-item[0], item[1].path, item[1].line))[:limit]]


def build_code_index(repo_dir: Path) -> CodeIndex:
    repo_dir = repo_dir.resolve()
    symbols: list[SymbolRecord] = []
    errors: dict[str, str] = {}
    files_indexed = 0

    for path in _iter_python_files(repo_dir):
        relative = path.relative_to(repo_dir).as_posix()
        files_indexed += 1
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError as exc:
            errors[relative] = f"SyntaxError:{exc.lineno}:{exc.msg}"
            continue
        except OSError as exc:
            errors[relative] = str(exc)
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                symbols.append(SymbolRecord(relative, node.name, "class", node.lineno, _class_signature(node), _doc(node)))
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                symbols.append(SymbolRecord(relative, node.name, "function", node.lineno, _function_signature(node), _doc(node)))
    return CodeIndex(symbols=sorted(symbols, key=lambda s: (s.path, s.line, s.name)), files_indexed=files_indexed, errors=errors)


def grep_repo(repo_dir: Path, query: str, *, limit: int = 20, suffixes: Iterable[str] | None = None) -> list[SearchHit]:
    repo_dir = repo_dir.resolve()
    terms = _tokens(query)
    if not terms:
        return []
    allowed_suffixes = set(suffixes or [".py", ".md", ".json", ".toml", ".yaml", ".yml", ".txt"])
    hits: list[SearchHit] = []
    for path in sorted(repo_dir.rglob("*")):
        if not path.is_file() or any(part in _IGNORED_PARTS for part in path.relative_to(repo_dir).parts):
            continue
        if path.suffix not in allowed_suffixes:
            continue
        relative = path.relative_to(repo_dir).as_posix()
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for line_no, line in enumerate(lines, start=1):
            lowered = line.lower()
            score = sum(1 for term in terms if term in lowered or term in relative.lower())
            if score:
                hits.append(SearchHit(relative, line_no, line.strip()[:240], score))
    return sorted(hits, key=lambda hit: (-hit.score, hit.path, hit.line))[:limit]


def _iter_python_files(repo_dir: Path) -> Iterable[Path]:
    for path in sorted(repo_dir.rglob("*.py")):
        if any(part in _IGNORED_PARTS for part in path.relative_to(repo_dir).parts):
            continue
        yield path


def _tokens(text: str) -> list[str]:
    return [token.lower() for token in re.findall(r"[a-zA-Z_][a-zA-Z0-9_]+|[\u4e00-\u9fff]+", text) if len(token) >= 2]


def _function_signature(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    args = [arg.arg for arg in node.args.args]
    if node.args.vararg:
        args.append("*" + node.args.vararg.arg)
    args.extend(arg.arg for arg in node.args.kwonlyargs)
    if node.args.kwarg:
        args.append("**" + node.args.kwarg.arg)
    prefix = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
    return f"{prefix} {node.name}({', '.join(args)})"


def _class_signature(node: ast.ClassDef) -> str:
    bases = [getattr(base, "id", ast.unparse(base) if hasattr(ast, "unparse") else "?") for base in node.bases]
    suffix = f"({', '.join(bases)})" if bases else ""
    return f"class {node.name}{suffix}"


def _doc(node: ast.AST) -> str:
    doc = ast.get_docstring(node) or ""
    return doc.splitlines()[0][:160] if doc else ""

"""Loading and parsing candidate Python files. Parsing never executes candidate code."""

from __future__ import annotations

import ast
import os
from dataclasses import dataclass
from pathlib import Path

SKIP_DIRS = frozenset(
    {
        ".git",
        "__pycache__",
        ".venv",
        "venv",
        "env",
        "node_modules",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        "site-packages",
        "build",
        "dist",
        ".tox",
    }
)
MAX_PARSED_FILE_BYTES = 1_000_000


@dataclass(frozen=True)
class ParsedFile:
    path: str  # POSIX-style, relative to the repository root
    source: str
    tree: ast.Module | None
    syntax_error: str | None = None
    error_line: int | None = None

    @property
    def is_test(self) -> bool:
        return is_test_path(self.path)


def is_test_path(relative_path: str) -> bool:
    parts = relative_path.split("/")
    name = parts[-1]
    return (
        name.startswith("test_")
        or name.endswith("_test.py")
        or name == "conftest.py"
        or any(part in {"tests", "test"} for part in parts[:-1])
    )


def iter_repo_files(root: Path) -> list[Path]:
    """All regular files under root in a deterministic order, skipping junk and symlinks."""
    found: list[Path] = []
    for current, dirs, files in os.walk(root):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
        for name in sorted(files):
            path = Path(current) / name
            if not path.is_symlink():
                found.append(path)
    return found


def parse_source(relative_path: str, source: str) -> ParsedFile:
    try:
        return ParsedFile(relative_path, source, ast.parse(source, filename=relative_path))
    except SyntaxError as exc:
        return ParsedFile(relative_path, source, None, f"{exc.msg}", exc.lineno)
    except (ValueError, RecursionError, MemoryError) as exc:
        return ParsedFile(relative_path, source, None, f"cannot parse: {type(exc).__name__}", None)


def load_python_files(root: Path) -> list[ParsedFile]:
    parsed: list[ParsedFile] = []
    for path in iter_repo_files(root):
        if path.suffix != ".py" or path.stat().st_size > MAX_PARSED_FILE_BYTES:
            continue
        relative = path.relative_to(root).as_posix()
        source = path.read_text(encoding="utf-8", errors="replace")
        parsed.append(parse_source(relative, source))
    return parsed

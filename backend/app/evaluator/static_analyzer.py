"""Lightweight static quality analysis based on the Python AST."""

from __future__ import annotations

import ast
from dataclasses import dataclass

from app.evaluator.source_files import ParsedFile
from app.models import Finding, Severity

MAX_FUNCTION_LINES = 50
HYGIENE_PENALTY_PER_FINDING = 0.25
_HYGIENE_RULES = {"QUALITY-SYNTAX-001", "QUALITY-EXCEPT-001", "QUALITY-LENGTH-001"}

FunctionNode = ast.FunctionDef | ast.AsyncFunctionDef


@dataclass(frozen=True)
class QualityMetrics:
    """Ratios in [0, 1] that feed the quality score."""

    type_hint_ratio: float
    docstring_ratio: float
    hygiene_ratio: float
    public_function_count: int


def _is_public(name: str) -> bool:
    return not name.startswith("_")


def _has_full_annotations(func: FunctionNode) -> bool:
    args = func.args
    all_args = [*args.posonlyargs, *args.args, *args.kwonlyargs]
    if all_args and all_args[0].arg in {"self", "cls"}:
        all_args = all_args[1:]
    extras = [a for a in (args.vararg, args.kwarg) if a is not None]
    return func.returns is not None and all(a.annotation is not None for a in [*all_args, *extras])


def _function_length(func: FunctionNode) -> int:
    return (func.end_lineno or func.lineno) - func.lineno + 1


def _finding(rule: str, severity: Severity, message: str, path: str, line: int | None) -> Finding:
    return Finding(severity=severity, rule=rule, message=message, file=path, line=line)


def _analyze_file(parsed: ParsedFile) -> tuple[list[Finding], int, int, int, int]:
    """Return findings plus (typed, public_functions, documented, documentable)."""
    if parsed.tree is None:
        message = f"syntax error: {parsed.syntax_error}"
        return (
            [
                _finding(
                    "QUALITY-SYNTAX-001", Severity.HIGH, message, parsed.path, parsed.error_line
                )
            ],
            0,
            0,
            0,
            0,
        )

    findings: list[Finding] = []
    typed = public = documented = documentable = 0
    documentable += 1
    documented += 1 if ast.get_docstring(parsed.tree) else 0
    for node in ast.walk(parsed.tree):
        if isinstance(node, ast.ExceptHandler) and node.type is None:
            findings.append(
                _finding(
                    "QUALITY-EXCEPT-001",
                    Severity.MEDIUM,
                    "bare 'except:' hides unexpected errors",
                    parsed.path,
                    node.lineno,
                )
            )
        if isinstance(node, ast.ClassDef) and _is_public(node.name):
            documentable += 1
            documented += 1 if ast.get_docstring(node) else 0
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            if _function_length(node) > MAX_FUNCTION_LINES:
                findings.append(
                    _finding(
                        "QUALITY-LENGTH-001",
                        Severity.LOW,
                        f"function '{node.name}' is {_function_length(node)} lines long",
                        parsed.path,
                        node.lineno,
                    )
                )
            if not _is_public(node.name):
                continue
            public += 1
            documentable += 1
            if _has_full_annotations(node):
                typed += 1
            else:
                findings.append(
                    _finding(
                        "QUALITY-TYPES-001",
                        Severity.LOW,
                        f"'{node.name}' lacks complete type annotations",
                        parsed.path,
                        node.lineno,
                    )
                )
            if ast.get_docstring(node):
                documented += 1
            else:
                findings.append(
                    _finding(
                        "QUALITY-DOC-001",
                        Severity.LOW,
                        f"'{node.name}' has no docstring",
                        parsed.path,
                        node.lineno,
                    )
                )
    return findings, typed, public, documented, documentable


def analyze_quality(files: list[ParsedFile]) -> tuple[list[Finding], QualityMetrics]:
    """Analyse non-test source files. Tests are excluded so they cannot inflate the metrics."""
    findings: list[Finding] = []
    typed = public = documented = documentable = 0
    for parsed in files:
        if parsed.is_test:
            continue
        file_findings, t, p, d, n = _analyze_file(parsed)
        findings += file_findings
        typed, public, documented, documentable = (
            typed + t,
            public + p,
            documented + d,
            documentable + n,
        )

    hygiene_hits = sum(1 for f in findings if f.rule in _HYGIENE_RULES)
    metrics = QualityMetrics(
        type_hint_ratio=typed / public if public else 0.0,
        docstring_ratio=documented / documentable if documentable else 0.0,
        hygiene_ratio=max(0.0, 1.0 - HYGIENE_PENALTY_PER_FINDING * hygiene_hits),
        public_function_count=public,
    )
    findings.sort(key=lambda f: (f.file, f.line or 0, f.rule))
    return findings, metrics

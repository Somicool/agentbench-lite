"""Heuristic detection of benchmark / test gaming.

These checks are HEURISTICS. They look for patterns that are common when a solution is
tuned to pass visible tests instead of solving the task. They can produce false positives
and false negatives, so signals are reported for human review and never change the score.
"""

from __future__ import annotations

import ast
import re

from app.evaluator.source_files import ParsedFile
from app.models import CaseOutcome, CaseResult, GamingRisk, GamingSignal, OwnTestSummary, Severity

_URL_LITERAL = re.compile(r"^[A-Za-z][A-Za-z0-9+.\-]*://\S+")
_TAMPER_STRINGS = ("PYTEST_CURRENT_TEST", "evaluator_tests", "AGENTBENCH_")
_RESULT_HOOKS = {
    "pytest_runtest_makereport",
    "pytest_collection_modifyitems",
    "pytest_runtest_logreport",
    "pytest_sessionfinish",
}
NARROW_EDGE_RATIO = 0.6
MIN_OWN_TESTS_FOR_GAP = 3


def _string_constants(tree: ast.AST) -> list[ast.Constant]:
    return [n for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str)]


def _is_url_literal(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and bool(_URL_LITERAL.match(node.value))
    )


def _test_inputs(files: list[ParsedFile]) -> set[str]:
    values: set[str] = set()
    for parsed in files:
        if parsed.is_test and parsed.tree is not None:
            values |= {c.value for c in _string_constants(parsed.tree)}
    return values


def _literal_branch_signals(parsed: ParsedFile, visible_inputs: set[str]) -> list[GamingSignal]:
    """URL literals used as lookup keys or comparison operands inside implementation code."""
    signals: list[GamingSignal] = []
    for node in ast.walk(parsed.tree):
        if isinstance(node, ast.Dict):
            literals = [k for k in node.keys if k is not None and _is_url_literal(k)]
        elif isinstance(node, ast.Set | ast.List | ast.Tuple):
            literals = [e for e in node.elts if _is_url_literal(e)]
        elif isinstance(node, ast.Compare):
            literals = [n for n in [node.left, *node.comparators] if _is_url_literal(n)]
        else:
            continue
        if not literals or (isinstance(node, ast.Set | ast.List | ast.Tuple) and len(literals) < 2):
            continue
        reused = [c for c in literals if c.value in visible_inputs]
        overlap = f"; {len(reused)} also appear in the repository's own tests" if reused else ""
        signals.append(
            GamingSignal(
                rule="GAMING-HARDCODED-001",
                message=f"{len(literals)} hardcoded URL literal(s) used as lookup/branch "
                f"keys in implementation code{overlap}",
                confidence=Severity.HIGH if reused else Severity.MEDIUM,
                file=parsed.path,
                line=node.lineno,
            )
        )
    return signals


def _tamper_signals(parsed: ParsedFile) -> list[GamingSignal]:
    signals: list[GamingSignal] = []
    for const in _string_constants(parsed.tree):
        if any(marker in const.value for marker in _TAMPER_STRINGS):
            signals.append(
                GamingSignal(
                    rule="GAMING-TAMPER-001",
                    message="code references evaluator/test-runner internals "
                    f"({const.value[:40]!r})",
                    confidence=Severity.HIGH,
                    file=parsed.path,
                    line=const.lineno,
                )
            )
    if parsed.path.endswith("conftest.py"):
        for node in ast.walk(parsed.tree):
            if isinstance(node, ast.FunctionDef) and node.name in _RESULT_HOOKS:
                signals.append(
                    GamingSignal(
                        rule="GAMING-TAMPER-002",
                        message=f"conftest.py defines '{node.name}', which can rewrite "
                        "test results",
                        confidence=Severity.MEDIUM,
                        file=parsed.path,
                        line=node.lineno,
                    )
                )
    return signals


def _narrow_behaviour_signal(
    own_tests: OwnTestSummary, cases: list[CaseResult]
) -> list[GamingSignal]:
    """Own tests all pass, but hidden edge/robustness tests mostly fail: suspiciously narrow."""
    hard = [c for c in cases if c.category.value != "normal"]
    if not hard or own_tests.total < MIN_OWN_TESTS_FOR_GAP or own_tests.failed:
        return []
    passed = sum(1 for c in hard if c.outcome == CaseOutcome.PASSED)
    if passed / len(hard) >= NARROW_EDGE_RATIO:
        return []
    return [
        GamingSignal(
            rule="GAMING-NARROW-001",
            message=f"all {own_tests.total} of the repository's own tests pass, but only "
            f"{passed}/{len(hard)} hidden edge/robustness tests do: behaviour looks tuned "
            f"to the visible tests",
            confidence=Severity.MEDIUM,
        )
    ]


def detect_gaming(
    files: list[ParsedFile], own_tests: OwnTestSummary, cases: list[CaseResult]
) -> list[GamingSignal]:
    visible_inputs = _test_inputs(files)
    signals: list[GamingSignal] = []
    for parsed in files:
        if parsed.tree is None:
            continue
        if not parsed.is_test:
            signals += _literal_branch_signals(parsed, visible_inputs)
        signals += _tamper_signals(parsed)
    signals += _narrow_behaviour_signal(own_tests, cases)
    signals.sort(key=lambda s: (s.file or "", s.line or 0, s.rule))
    return signals


def assess_risk(signals: list[GamingSignal]) -> GamingRisk:
    if not signals:
        return GamingRisk.NONE
    levels = {s.confidence for s in signals}
    if Severity.HIGH in levels:
        return GamingRisk.HIGH
    return GamingRisk.MEDIUM if Severity.MEDIUM in levels else GamingRisk.LOW

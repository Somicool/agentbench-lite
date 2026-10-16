"""Plain-text evaluation report."""

from __future__ import annotations

from collections import Counter

from app.models import EvaluationResult, Failure, FailureCategory

BAR_WIDTH = 20
MAX_FAILURES_PER_CATEGORY = 6


def _bar(percent: int) -> str:
    filled = round(BAR_WIDTH * percent / 100)
    return "█" * filled + "░" * (BAR_WIDTH - filled)


def _score_lines(result: EvaluationResult) -> list[str]:
    rows = [
        ("Functional Correctness", result.functional_score),
        ("Edge Cases", result.edge_case_score),
        ("Requirements", result.requirement_score),
        ("Security", result.security_score),
        ("Code Quality", result.quality_score),
    ]
    return [f"{label:<24}{_bar(score)} {score:>3}%" for label, score in rows]


def _calculation_lines(result: EvaluationResult) -> list[str]:
    lines = ["Score Calculation (weight x measured ratio)"]
    for c in result.score_breakdown:
        lines.append(f"  {c.label:<24}{c.points:>5.1f}/{c.weight:<4g} {c.explanation}")
    if result.score_cap_applied:
        lines.append(f"  {'Raw total':<24}{result.raw_score:>5}/100")
        lines.append("  Integrity cap applied: a HIGH-confidence gaming signal limits the score.")
    lines.append(f"  {'TOTAL':<24}{result.overall_score:>5}/100")
    return lines


def _failure_lines(failures: list[Failure]) -> list[str]:
    if not failures:
        return ["  No failures detected."]
    lines: list[str] = []
    shown: Counter[FailureCategory] = Counter()
    hidden: Counter[FailureCategory] = Counter()
    for failure in failures:
        if shown[failure.category] >= MAX_FAILURES_PER_CATEGORY:
            hidden[failure.category] += 1
            continue
        shown[failure.category] += 1
        where = f" ({failure.file}:{failure.line})" if failure.file and failure.line else ""
        lines.append(f"  [{failure.category.value}] {failure.message}{where}")
    lines += [f"  ... and {n} more {cat.value}" for cat, n in hidden.items()]
    return lines


def _gaming_lines(result: EvaluationResult) -> list[str]:
    lines = [f"Possible Test Gaming (heuristic, risk: {result.gaming_risk.value})"]
    if not result.gaming_signals:
        return [*lines, "  No suspicious patterns found."]
    for signal in result.gaming_signals:
        where = f" ({signal.file}:{signal.line})" if signal.file and signal.line else ""
        lines.append(f"  [{signal.confidence.value}] {signal.message}{where}")
    return lines


def generate_text_report(result: EvaluationResult) -> str:
    """Render a human-readable report. Everything shown comes from the EvaluationResult."""
    own = result.own_tests
    sections: list[list[str]] = [
        [
            "AGENTBENCH LITE",
            f"Task: {result.task_title}",
            f"Repository: {result.repository_name}   Evaluation: {result.evaluation_id}",
            f"Overall Score: {result.overall_score}/100",
        ],
        _score_lines(result),
        _calculation_lines(result),
        [
            f"Hidden tests: {result.tests_passed} passed, {result.tests_failed} failed",
            f"Repository's own tests: {own.passed} passed, {own.failed} failed ({own.total} total)",
        ],
        ["Failures", *_failure_lines(result.failures)],
        _gaming_lines(result),
        ["Recommendations", *[f"  - {r}" for r in result.recommendations or ["None."]]],
        [
            f"Execution: {result.execution_mode} mode, {result.duration_seconds}s, "
            f"Bandit {'used' if result.bandit_used else 'not used'}"
        ],
    ]
    return "\n\n".join("\n".join(lines) for lines in sections) + "\n"

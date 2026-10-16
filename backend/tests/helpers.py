"""Small helpers shared by the evaluator's own tests."""

from __future__ import annotations

from pathlib import Path

from app.config import EvaluatorConfig
from app.models import (
    CaseCategory,
    CaseOutcome,
    CaseResult,
    ExecutionRecord,
    OwnTestSummary,
)

TEST_CONFIG = EvaluatorConfig(use_bandit=False, own_tests_timeout=30, hidden_tests_timeout=20)
FAST_TIMEOUT_CONFIG = EvaluatorConfig(use_bandit=False, own_tests_timeout=2, hidden_tests_timeout=2)


def write_repo(root: Path, files: dict[str, str]) -> Path:
    """Create a throwaway candidate repository from {relative_path: source}."""
    for relative, source in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source, encoding="utf-8")
    return root


def make_case(
    category: CaseCategory = CaseCategory.NORMAL,
    outcome: CaseOutcome = CaseOutcome.PASSED,
    requirements: list[str] | None = None,
    error_type: str | None = None,
    error_message: str | None = None,
    file: str = "test_normal.py",
    description: str = "case",
) -> CaseResult:
    return CaseResult(
        test_id=f"{file}::{description}",
        file=file,
        category=category,
        description=description,
        outcome=outcome,
        requirements=requirements or [],
        error_type=error_type,
        error_message=error_message,
    )


def make_execution(
    name: str = "candidate tests", exit_code: int | None = 0, timed_out: bool = False
) -> ExecutionRecord:
    return ExecutionRecord(
        name=name,
        command="python -m pytest",
        exit_code=exit_code,
        duration_seconds=1.0,
        timed_out=timed_out,
        stdout="",
        stderr="",
        mode="local",
    )


def passing_own_tests(total: int = 4) -> OwnTestSummary:
    return OwnTestSummary(ran=True, found=True, total=total, passed=total)

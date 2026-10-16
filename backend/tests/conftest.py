"""Shared fixtures. Example repositories are evaluated once per test session."""

from __future__ import annotations

import pytest

from app.config import EXAMPLES_DIR
from app.evaluator.runner import EvaluationRunner
from app.models import EvaluationResult
from tests.helpers import TEST_CONFIG


@pytest.fixture(scope="session")
def example_results() -> dict[str, EvaluationResult]:
    runner = EvaluationRunner(TEST_CONFIG)
    return {
        name: runner.evaluate("task", EXAMPLES_DIR / name)
        for name in ("good_solution", "buggy_solution", "cheating_solution")
    }

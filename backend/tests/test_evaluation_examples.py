"""End-to-end checks: the evaluator must tell the three example repositories apart."""

from __future__ import annotations

from app.config import EXAMPLES_DIR
from app.evaluator.runner import EvaluationRunner
from app.models import EvaluationResult, FailureCategory, GamingRisk, Severity
from tests.helpers import FAST_TIMEOUT_CONFIG, TEST_CONFIG, write_repo


def _categories(result: EvaluationResult) -> set[FailureCategory]:
    return {f.category for f in result.failures}


def test_good_repository_gets_a_high_score(example_results):
    good = example_results["good_solution"]
    assert good.overall_score >= 95
    assert good.tests_failed == 0
    assert good.failures == []
    assert good.gaming_risk == GamingRisk.NONE


def test_buggy_repository_scores_lower_than_good(example_results):
    good, buggy = example_results["good_solution"], example_results["buggy_solution"]
    assert buggy.overall_score < good.overall_score - 15
    assert buggy.tests_failed > 0


def test_cheating_repository_scores_lower_than_good(example_results):
    good, cheat = example_results["good_solution"], example_results["cheating_solution"]
    assert cheat.overall_score < good.overall_score - 30


def test_empty_input_failure_is_detected(example_results):
    buggy = example_results["buggy_solution"]
    empty = [f for f in buggy.failures if "Empty string" in f.message]
    assert empty, "buggy repo crashes on '' and the evaluator must say so"
    assert empty[0].category == FailureCategory.EDGE_CASE_FAILURE
    assert "IndexError" in empty[0].message


def test_malformed_url_failure_is_detected(example_results):
    buggy = example_results["buggy_solution"]
    malformed = [f for f in buggy.failures if "malformed URL" in f.message]
    assert any("exa mple" in f.message for f in malformed)


def test_unsafe_eval_is_reported_as_security_issue(example_results):
    buggy = example_results["buggy_solution"]
    assert any(f.rule == "PYTHON-EVAL-001" for f in buggy.security_findings)
    assert FailureCategory.SECURITY_ISSUE in _categories(buggy)
    assert buggy.security_score < 100


def test_buggy_repository_failure_categories(example_results):
    assert {
        FailureCategory.FUNCTIONAL_ERROR,
        FailureCategory.EDGE_CASE_FAILURE,
        FailureCategory.ROBUSTNESS_FAILURE,
        FailureCategory.REQUIREMENT_MISSED,
        FailureCategory.TEST_FAILURE,
    } <= _categories(example_results["buggy_solution"])


def test_cheating_repository_is_flagged_as_possible_gaming(example_results):
    cheat = example_results["cheating_solution"]
    gaming = [f for f in cheat.failures if f.category == FailureCategory.POSSIBLE_TEST_GAMING]
    assert gaming and all(f.heuristic for f in gaming)
    assert cheat.gaming_risk == GamingRisk.HIGH
    assert cheat.own_tests.failed == 0  # it passes its own tests...
    assert cheat.edge_case_score < 80  # ...but the hidden edge cases expose it


def test_cheating_repository_hits_the_integrity_cap(example_results):
    cheat = example_results["cheating_solution"]
    assert cheat.score_cap_applied
    assert cheat.raw_score > cheat.overall_score == 60


def test_every_requirement_is_covered_by_hidden_tests(example_results):
    requirements = example_results["good_solution"].requirements
    assert requirements
    assert all(r.total > 0 and r.passed == r.total for r in requirements)


def test_evaluation_is_deterministic(example_results):
    first = example_results["buggy_solution"]
    again = EvaluationRunner(TEST_CONFIG).evaluate("task", EXAMPLES_DIR / "buggy_solution")
    assert again.overall_score == first.overall_score
    assert again.score_breakdown == first.score_breakdown
    assert [f.message for f in again.failures] == [f.message for f in first.failures]


def test_evaluation_times_out_instead_of_hanging(tmp_path):
    repo = write_repo(tmp_path / "repo", {"url_validator.py": "while True:\n    pass\n"})
    result = EvaluationRunner(FAST_TIMEOUT_CONFIG).evaluate("task", repo)

    assert any(run.timed_out for run in result.executions)
    assert result.duration_seconds < 40
    assert any(
        f.category == FailureCategory.PERFORMANCE_FAILURE and f.severity == Severity.HIGH
        for f in result.failures
    )
    assert result.overall_score < 25


def test_import_failure_is_an_environment_failure(tmp_path):
    repo = write_repo(tmp_path / "repo", {"url_validator.py": "import not_a_real_package\n"})
    result = EvaluationRunner(TEST_CONFIG).evaluate("task", repo)
    environment = [f for f in result.failures if f.category == FailureCategory.ENVIRONMENT_FAILURE]
    assert any("not_a_real_package" in f.message for f in environment)
    assert result.functional_score == 0


def test_original_repository_is_left_untouched(tmp_path):
    repo = write_repo(
        tmp_path / "repo", {"url_validator.py": "def is_valid_url(u):\n    return False\n"}
    )
    before = sorted(p.name for p in repo.rglob("*"))
    EvaluationRunner(TEST_CONFIG).evaluate("task", repo)
    assert sorted(p.name for p in repo.rglob("*")) == before

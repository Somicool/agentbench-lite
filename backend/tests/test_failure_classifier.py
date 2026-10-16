from __future__ import annotations

from app.evaluator.failure_classifier import (
    LOAD_ERROR_TYPE,
    build_recommendations,
    classify_failures,
)
from app.evaluator.requirement_checker import check_requirements
from app.evaluator.tasks import URL_VALIDATOR
from app.models import (
    CaseCategory,
    CaseOutcome,
    Failure,
    FailureCategory,
    Finding,
    GamingSignal,
    OwnTestSummary,
    Severity,
)
from tests.helpers import make_case, make_execution, passing_own_tests

OK_RUN = make_execution()


def classify(cases, hidden_runs=(), findings=(), own=None, own_run=OK_RUN, gaming=()):
    requirements = check_requirements(URL_VALIDATOR, cases)
    return classify_failures(
        cases,
        list(hidden_runs),
        requirements,
        list(findings),
        [],
        own or passing_own_tests(),
        own_run,
        list(gaming),
    )


def by_category(failures: list[Failure]) -> dict[FailureCategory, list[Failure]]:
    grouped: dict[FailureCategory, list[Failure]] = {}
    for failure in failures:
        grouped.setdefault(failure.category, []).append(failure)
    return grouped


def test_each_case_category_maps_to_its_failure_category():
    failed = CaseOutcome.FAILED
    cases = [
        make_case(CaseCategory.NORMAL, failed, error_type="AssertionError", error_message="x"),
        make_case(CaseCategory.EDGE, failed, error_type="AssertionError", error_message="x"),
        make_case(CaseCategory.ROBUSTNESS, failed, error_type="TypeError", error_message="x"),
        make_case(CaseCategory.PERFORMANCE, failed, error_type="AssertionError", error_message="x"),
    ]
    found = by_category(classify(cases))
    assert {
        FailureCategory.FUNCTIONAL_ERROR,
        FailureCategory.EDGE_CASE_FAILURE,
        FailureCategory.ROBUSTNESS_FAILURE,
        FailureCategory.PERFORMANCE_FAILURE,
    } <= set(found)


def test_exception_type_is_included_in_the_message():
    case = make_case(
        CaseCategory.EDGE,
        CaseOutcome.ERROR,
        error_type="ValueError",
        error_message="bad",
        description="Empty input is rejected",
    )
    (failure,) = by_category(classify([case]))[FailureCategory.EDGE_CASE_FAILURE]
    assert failure.message == "Empty input is rejected: raised ValueError: bad"


def test_passing_cases_produce_no_failures():
    assert classify([make_case(CaseCategory.NORMAL, requirements=["HTTP_SUPPORTED"])]) == []


def test_candidate_load_error_is_one_environment_failure_not_many():
    cases = [
        make_case(
            CaseCategory.NORMAL,
            CaseOutcome.ERROR,
            error_type=LOAD_ERROR_TYPE,
            error_message="cannot load url_validator.is_valid_url: ImportError",
        )
        for _ in range(5)
    ]
    found = by_category(classify(cases))
    assert len(found[FailureCategory.ENVIRONMENT_FAILURE]) == 1
    assert FailureCategory.FUNCTIONAL_ERROR not in found


def test_timed_out_run_is_a_performance_failure_with_unfinished_count():
    cases = [make_case(CaseCategory.EDGE, CaseOutcome.NOT_RUN, file="test_edge_cases.py")] * 3
    run = make_execution("hidden tests: test_edge_cases.py", exit_code=None, timed_out=True)
    (failure,) = by_category(classify(cases, [run]))[FailureCategory.PERFORMANCE_FAILURE]
    assert "3 test(s) never finished" in failure.message
    assert failure.severity == Severity.HIGH


def test_unmet_requirements_are_reported_with_pass_counts():
    cases = [
        make_case(outcome=CaseOutcome.PASSED, requirements=["HTTP_SUPPORTED"]),
        make_case(outcome=CaseOutcome.FAILED, requirements=["HTTP_SUPPORTED"], error_message="x"),
        make_case(outcome=CaseOutcome.FAILED, requirements=["HTTPS_SUPPORTED"], error_message="x"),
    ]
    missed = by_category(classify(cases))[FailureCategory.REQUIREMENT_MISSED]
    severities = {f.message.split(" (")[0]: f.severity for f in missed}
    assert severities["HTTP URLs are accepted"] == Severity.MEDIUM  # partial
    assert severities["HTTPS URLs are accepted"] == Severity.HIGH  # nothing passed


def test_security_findings_become_security_issues_with_location():
    finding = Finding(
        severity=Severity.HIGH,
        rule="PYTHON-EVAL-001",
        message="use of eval()",
        file="validator.py",
        line=18,
    )
    (failure,) = by_category(classify([], findings=[finding]))[FailureCategory.SECURITY_ISSUE]
    assert (failure.file, failure.line, failure.severity) == ("validator.py", 18, Severity.HIGH)


def test_failing_own_tests_are_a_test_failure():
    own = OwnTestSummary(ran=True, found=True, total=5, passed=4, failed=1, failing_tests=["t::a"])
    (failure,) = by_category(classify([], own=own))[FailureCategory.TEST_FAILURE]
    assert "1 of 5" in failure.message


def test_repository_without_tests_is_a_low_severity_test_failure():
    (failure,) = by_category(classify([], own=OwnTestSummary(ran=True)))[
        FailureCategory.TEST_FAILURE
    ]
    assert failure.severity == Severity.LOW


def test_gaming_signals_are_labelled_heuristic():
    signal = GamingSignal(
        rule="GAMING-HARDCODED-001", message="hardcoded", confidence=Severity.HIGH
    )
    (failure,) = by_category(classify([], gaming=[signal]))[FailureCategory.POSSIBLE_TEST_GAMING]
    assert failure.heuristic and failure.message.startswith("(heuristic)")


def test_failures_are_sorted_most_severe_first():
    cases = [
        make_case(CaseCategory.EDGE, CaseOutcome.FAILED, error_message="x"),
        make_case(CaseCategory.NORMAL, CaseOutcome.FAILED, error_message="x"),
    ]
    severities = [f.severity for f in classify(cases)]
    assert severities == sorted(severities, key=lambda s: ["HIGH", "MEDIUM", "LOW"].index(s.value))


def test_recommendations_are_unique_and_tied_to_failures():
    cases = [
        make_case(CaseCategory.EDGE, CaseOutcome.FAILED, ["EMPTY_INPUT_SAFE"], "IndexError", "x")
    ]
    requirements = check_requirements(URL_VALIDATOR, cases)
    failures = classify(cases)
    advice = build_recommendations(URL_VALIDATOR, failures, requirements, [])
    assert any("empty input" in line.lower() for line in advice)
    assert len(advice) == len(set(advice))

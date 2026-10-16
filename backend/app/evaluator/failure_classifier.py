"""Turns raw evaluation evidence into classified failures and recommendations."""

from __future__ import annotations

from app.evaluator.tasks import TaskSpec
from app.models import (
    CaseCategory,
    CaseOutcome,
    CaseResult,
    ExecutionRecord,
    Failure,
    FailureCategory,
    Finding,
    GamingSignal,
    OwnTestSummary,
    RequirementResult,
    RequirementStatus,
    Severity,
)

LOAD_ERROR_TYPE = "CandidateLoadError"
_SEVERITY_RANK = {Severity.HIGH: 0, Severity.MEDIUM: 1, Severity.LOW: 2}
_CASE_FAILURE = {
    CaseCategory.NORMAL: (FailureCategory.FUNCTIONAL_ERROR, Severity.HIGH),
    CaseCategory.EDGE: (FailureCategory.EDGE_CASE_FAILURE, Severity.MEDIUM),
    CaseCategory.ROBUSTNESS: (FailureCategory.ROBUSTNESS_FAILURE, Severity.MEDIUM),
    CaseCategory.PERFORMANCE: (FailureCategory.PERFORMANCE_FAILURE, Severity.MEDIUM),
}
_CATEGORY_ADVICE = {
    FailureCategory.FUNCTIONAL_ERROR: "Fix core behaviour first: valid URLs must be accepted.",
    FailureCategory.EDGE_CASE_FAILURE: "Add tests for empty, whitespace, malformed and "
    "unusual-but-valid inputs.",
    FailureCategory.ROBUSTNESS_FAILURE: "Validate input types and catch parser errors so the "
    "function never raises.",
    FailureCategory.PERFORMANCE_FAILURE: "Bound input size and avoid unbounded loops or "
    "backtracking-prone regular expressions.",
    FailureCategory.TEST_FAILURE: "Make the repository's own tests pass and extend them.",
    FailureCategory.POSSIBLE_TEST_GAMING: "Replace hardcoded outputs with general logic and "
    "re-check against inputs the tests never mention.",
}


def _case_message(case: CaseResult) -> str:
    if case.error_type and case.error_type != "AssertionError":
        return f"{case.description}: raised {case.error_type}: {case.error_message}"
    return f"{case.description}: {case.error_message or 'failed'}"


def _case_failures(cases: list[CaseResult]) -> list[Failure]:
    failures: list[Failure] = []
    load_errors = [c for c in cases if c.error_type == LOAD_ERROR_TYPE]
    if load_errors:
        failures.append(
            Failure(
                category=FailureCategory.ENVIRONMENT_FAILURE,
                severity=Severity.HIGH,
                message=load_errors[0].error_message or "candidate could not be imported",
            )
        )
    for case in cases:
        if case.outcome in {CaseOutcome.PASSED, CaseOutcome.NOT_RUN}:
            continue
        if case.error_type == LOAD_ERROR_TYPE:
            continue
        category, severity = _CASE_FAILURE[case.category]
        failures.append(
            Failure(
                category=category,
                severity=severity,
                message=_case_message(case),
                test_id=case.test_id,
            )
        )
    return failures


def _execution_failures(
    cases: list[CaseResult], executions: list[ExecutionRecord]
) -> list[Failure]:
    """Timeouts and crashes of the hidden test runs (tests that never reported a result)."""
    failures: list[Failure] = []
    for run in executions:
        file_name = run.name.removeprefix("hidden tests: ")
        unfinished = sum(
            1 for c in cases if c.file == file_name and c.outcome == CaseOutcome.NOT_RUN
        )
        if run.timed_out:
            failures.append(
                Failure(
                    category=FailureCategory.PERFORMANCE_FAILURE,
                    severity=Severity.HIGH,
                    message=(
                        f"{file_name} hit the {run.duration_seconds:.0f}s timeout and was "
                        f"killed; {unfinished} test(s) never finished (infinite loop or "
                        f"catastrophic backtracking?)"
                    ),
                )
            )
        elif run.exit_code not in (0, 1) and not any(c.file == file_name for c in cases):
            first_line = (run.stderr.strip().splitlines() or ["no error output"])[-1]
            failures.append(
                Failure(
                    category=FailureCategory.ENVIRONMENT_FAILURE,
                    severity=Severity.HIGH,
                    message=f"{file_name} crashed (exit code {run.exit_code}): {first_line[:200]}",
                )
            )
    return failures


def _requirement_failures(requirements: list[RequirementResult]) -> list[Failure]:
    failures: list[Failure] = []
    for req in requirements:
        if req.status in {RequirementStatus.MET, RequirementStatus.NOT_EVALUATED}:
            continue
        severity = Severity.HIGH if req.status == RequirementStatus.NOT_MET else Severity.MEDIUM
        failures.append(
            Failure(
                category=FailureCategory.REQUIREMENT_MISSED,
                severity=severity,
                message=f"{req.description} ({req.passed}/{req.total} checks passed)",
            )
        )
    return failures


def _security_failures(findings: list[Finding]) -> list[Failure]:
    return [
        Failure(
            category=FailureCategory.SECURITY_ISSUE,
            severity=f.severity,
            message=f"{f.message} [{f.rule}]",
            file=f.file,
            line=f.line,
        )
        for f in findings
    ]


def _own_test_failures(own: OwnTestSummary, run: ExecutionRecord) -> list[Failure]:
    if run.timed_out:
        return [
            Failure(
                category=FailureCategory.PERFORMANCE_FAILURE,
                severity=Severity.MEDIUM,
                message=f"the repository's own tests hit the {run.duration_seconds:.0f}s timeout",
            )
        ]
    if own.failed:
        names = ", ".join(own.failing_tests[:3])
        return [
            Failure(
                category=FailureCategory.TEST_FAILURE,
                severity=Severity.MEDIUM,
                message=f"{own.failed} of {own.total} of the repository's own tests fail ({names})",
            )
        ]
    if not own.found:
        return [
            Failure(
                category=FailureCategory.TEST_FAILURE,
                severity=Severity.LOW,
                message="the repository ships no runnable tests of its own",
            )
        ]
    return []


def _gaming_failures(signals: list[GamingSignal]) -> list[Failure]:
    return [
        Failure(
            category=FailureCategory.POSSIBLE_TEST_GAMING,
            severity=s.confidence,
            message=f"(heuristic) {s.message}",
            file=s.file,
            line=s.line,
            heuristic=True,
        )
        for s in signals
    ]


def classify_failures(
    cases: list[CaseResult],
    hidden_runs: list[ExecutionRecord],
    requirements: list[RequirementResult],
    security_findings: list[Finding],
    syntax_findings: list[Finding],
    own_tests: OwnTestSummary,
    own_run: ExecutionRecord,
    gaming_signals: list[GamingSignal],
) -> list[Failure]:
    failures = [
        *_execution_failures(cases, hidden_runs),
        *_case_failures(cases),
        *_requirement_failures(requirements),
        *_security_failures(security_findings),
        *_own_test_failures(own_tests, own_run),
        *_gaming_failures(gaming_signals),
        *(
            Failure(
                category=FailureCategory.ENVIRONMENT_FAILURE,
                severity=Severity.HIGH,
                message=f.message,
                file=f.file,
                line=f.line,
            )
            for f in syntax_findings
        ),
    ]
    return sorted(failures, key=lambda f: _SEVERITY_RANK[f.severity])  # stable: keeps order


def build_recommendations(
    spec: TaskSpec,
    failures: list[Failure],
    requirements: list[RequirementResult],
    security_findings: list[Finding],
) -> list[str]:
    advice: list[str] = []
    advice += [
        r.recommendation
        for r in spec.requirements
        if any(
            res.id == r.id and res.status in {RequirementStatus.NOT_MET, RequirementStatus.PARTIAL}
            for res in requirements
        )
    ]
    advice += [
        f.recommendation
        for f in security_findings
        if f.recommendation and f.severity != Severity.LOW
    ]
    present = {f.category for f in failures}
    advice += [text for cat, text in _CATEGORY_ADVICE.items() if cat in present]
    if FailureCategory.ENVIRONMENT_FAILURE in present:
        advice.append(
            f"Expose {spec.module_name}.{spec.function_name} and keep the code importable "
            f"with the standard library only."
        )
    return list(dict.fromkeys(advice))

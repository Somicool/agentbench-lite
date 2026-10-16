"""Requirement checking: a requirement is evaluated through the hidden tests tagged with it."""

from __future__ import annotations

from app.evaluator.tasks import TaskSpec
from app.models import CaseOutcome, CaseResult, RequirementResult, RequirementStatus


def _status(passed: int, total: int) -> RequirementStatus:
    if total == 0:
        return RequirementStatus.NOT_EVALUATED
    if passed == total:
        return RequirementStatus.MET
    return RequirementStatus.NOT_MET if passed == 0 else RequirementStatus.PARTIAL


def check_requirements(spec: TaskSpec, cases: list[CaseResult]) -> list[RequirementResult]:
    results: list[RequirementResult] = []
    for requirement in spec.requirements:
        linked = [c for c in cases if requirement.id in c.requirements]
        passed = sum(1 for c in linked if c.outcome == CaseOutcome.PASSED)
        results.append(
            RequirementResult(
                id=requirement.id,
                description=requirement.description,
                status=_status(passed, len(linked)),
                passed=passed,
                total=len(linked),
                failing_tests=[c.test_id for c in linked if c.outcome != CaseOutcome.PASSED],
            )
        )
    return results

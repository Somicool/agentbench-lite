from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.evaluator.requirement_checker import check_requirements
from app.evaluator.scorer import INTEGRITY_CAP, calculate_score
from app.evaluator.static_analyzer import QualityMetrics
from app.evaluator.tasks import URL_VALIDATOR
from app.models import (
    CaseCategory,
    CaseOutcome,
    Finding,
    GamingRisk,
    OwnTestSummary,
    ScoreWeights,
    Severity,
)
from tests.helpers import make_case, passing_own_tests

PERFECT_QUALITY = QualityMetrics(1.0, 1.0, 1.0, 3)


def score(
    cases, findings=(), own=None, metrics=PERFECT_QUALITY, weights=None, risk=GamingRisk.NONE
):
    requirements = check_requirements(URL_VALIDATOR, cases)
    return calculate_score(
        cases,
        requirements,
        list(findings),
        own or passing_own_tests(),
        metrics,
        weights or ScoreWeights(),
        risk,
    )


def mixed_cases():
    return [
        make_case(CaseCategory.NORMAL, CaseOutcome.PASSED, ["HTTP_SUPPORTED"]),
        make_case(CaseCategory.NORMAL, CaseOutcome.PASSED, ["HTTPS_SUPPORTED"]),
        make_case(CaseCategory.NORMAL, CaseOutcome.FAILED, ["HTTP_SUPPORTED"]),
        make_case(CaseCategory.EDGE, CaseOutcome.PASSED, ["EMPTY_INPUT_SAFE"]),
        make_case(CaseCategory.ROBUSTNESS, CaseOutcome.FAILED, ["NO_UNEXPECTED_EXCEPTIONS"]),
    ]


def test_score_calculation_is_deterministic():
    findings = [Finding(severity=Severity.HIGH, rule="R", message="m", file="a.py")]
    first = score(mixed_cases(), findings)
    second = score(mixed_cases(), findings)
    assert first == second


def test_points_are_weight_times_measured_ratio():
    card = score(mixed_cases())
    by_key = {c.key: c for c in card.components}
    assert by_key["functional"].ratio == pytest.approx(2 / 3, abs=1e-4)
    assert by_key["functional"].points == pytest.approx(40 * 2 / 3, abs=0.01)
    assert by_key["edge_cases"].ratio == 0.5
    assert by_key["edge_cases"].points == 10.0
    assert by_key["quality"].points == 10.0


def test_overall_score_is_the_sum_of_displayed_points():
    card = score(mixed_cases())
    assert card.overall_score == round(sum(c.points for c in card.components))


def test_security_penalties_by_severity():
    def sec(*severities):
        findings = [Finding(severity=s, rule="R", message="m", file="a.py") for s in severities]
        return next(c for c in score(mixed_cases(), findings).components if c.key == "security")

    assert sec().ratio == 1.0
    assert sec(Severity.HIGH).ratio == 0.6
    assert sec(Severity.MEDIUM).ratio == 0.85
    assert sec(Severity.LOW).ratio == 0.95
    assert sec(Severity.HIGH, Severity.HIGH, Severity.HIGH).ratio == 0.0  # floored at zero


def test_no_hidden_results_scores_zero_not_full_marks():
    card = score([], own=OwnTestSummary(), metrics=QualityMetrics(0, 0, 1.0, 0))
    by_key = {c.key: c.ratio for c in card.components}
    assert by_key["functional"] == by_key["edge_cases"] == by_key["requirements"] == 0.0


def test_weights_are_configurable():
    cases = [make_case(CaseCategory.NORMAL, CaseOutcome.PASSED)] + [
        make_case(CaseCategory.EDGE, CaseOutcome.FAILED)
    ]
    heavy_edge = ScoreWeights(functional=10, edge_cases=70, requirements=10, security=5, quality=5)
    assert score(cases, weights=heavy_edge).overall_score < score(cases).overall_score


def test_weights_must_add_up_to_100():
    with pytest.raises(ValidationError):
        ScoreWeights(functional=50, edge_cases=20, requirements=20, security=10, quality=10)


def test_integrity_cap_applies_only_for_high_gaming_risk():
    perfect = [make_case(CaseCategory.NORMAL, CaseOutcome.PASSED, ["HTTP_SUPPORTED"])]
    assert not score(perfect, risk=GamingRisk.MEDIUM).cap_applied
    capped = score(perfect, risk=GamingRisk.HIGH)
    assert capped.cap_applied and capped.overall_score == INTEGRITY_CAP
    assert capped.raw_score > INTEGRITY_CAP

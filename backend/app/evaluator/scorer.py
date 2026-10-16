"""Transparent scoring: every point is derived from a measured ratio and a visible weight.

    points = weight * ratio            overall = sum(points), rounded half-up

Ratios:
    functional   = passed / total hidden *normal* tests
    edge_cases   = passed / total hidden edge + robustness + performance tests
    requirements = mean over requirements of (passed / total linked hidden tests)
    security     = 1 - sum(penalty per finding), floored at 0 (HIGH .40, MEDIUM .15, LOW .05)
    quality      = 0.4 * own-test pass rate + 0.2 * type hints + 0.2 * docstrings + 0.2 * hygiene

Integrity cap: if the gaming heuristics report HIGH risk, the overall score is capped at
INTEGRITY_CAP. The report shows both the raw and the capped score.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from app.evaluator.static_analyzer import QualityMetrics
from app.models import (
    CaseCategory,
    CaseOutcome,
    CaseResult,
    Finding,
    GamingRisk,
    OwnTestSummary,
    RequirementResult,
    ScoreComponent,
    ScoreWeights,
    Severity,
)

# A HIGH-confidence gaming signal means the passing results cannot be fully trusted, so the
# overall score is capped. The raw score and the cap are both reported.
INTEGRITY_CAP = 60
SECURITY_PENALTY = {Severity.HIGH: 0.40, Severity.MEDIUM: 0.15, Severity.LOW: 0.05}
QUALITY_PARTS = {"own tests": 0.4, "type hints": 0.2, "docstrings": 0.2, "hygiene": 0.2}
_EDGE_GROUP = {CaseCategory.EDGE, CaseCategory.ROBUSTNESS, CaseCategory.PERFORMANCE}


@dataclass(frozen=True)
class ScoreCard:
    components: list[ScoreComponent]
    overall_score: int
    raw_score: int  # before the integrity cap
    cap_applied: bool
    ratios: dict[str, float]


def _round_half_up(value: float) -> int:
    return math.floor(value + 0.5)


def _pass_ratio(cases: list[CaseResult]) -> tuple[float, int, int]:
    passed = sum(1 for c in cases if c.outcome == CaseOutcome.PASSED)
    return (passed / len(cases) if cases else 0.0), passed, len(cases)


def _requirement_ratio(requirements: list[RequirementResult]) -> float:
    if not requirements:
        return 0.0
    return sum(r.passed / r.total if r.total else 0.0 for r in requirements) / len(requirements)


def _security_ratio(findings: list[Finding]) -> float:
    return max(0.0, 1.0 - sum(SECURITY_PENALTY[f.severity] for f in findings))


def _quality_ratio(own_tests: OwnTestSummary, metrics: QualityMetrics) -> float:
    own_rate = own_tests.passed / own_tests.total if own_tests.total else 0.0
    return (
        QUALITY_PARTS["own tests"] * own_rate
        + QUALITY_PARTS["type hints"] * metrics.type_hint_ratio
        + QUALITY_PARTS["docstrings"] * metrics.docstring_ratio
        + QUALITY_PARTS["hygiene"] * metrics.hygiene_ratio
    )


def _component(key: str, label: str, weight: float, ratio: float, why: str) -> ScoreComponent:
    return ScoreComponent(
        key=key,
        label=label,
        weight=weight,
        ratio=round(ratio, 4),
        points=round(weight * ratio, 2),
        explanation=why,
    )


def calculate_score(
    cases: list[CaseResult],
    requirements: list[RequirementResult],
    security_findings: list[Finding],
    own_tests: OwnTestSummary,
    metrics: QualityMetrics,
    weights: ScoreWeights,
    gaming_risk: GamingRisk = GamingRisk.NONE,
) -> ScoreCard:
    normal = [c for c in cases if c.category == CaseCategory.NORMAL]
    hard = [c for c in cases if c.category in _EDGE_GROUP]
    functional, f_pass, f_total = _pass_ratio(normal)
    edge, e_pass, e_total = _pass_ratio(hard)
    requirement = _requirement_ratio(requirements)
    met = sum(1 for r in requirements if r.total and r.passed == r.total)
    security = _security_ratio(security_findings)
    quality = _quality_ratio(own_tests, metrics)

    components = [
        _component(
            "functional",
            "Functional correctness",
            weights.functional,
            functional,
            f"{f_pass}/{f_total} hidden normal tests passed",
        ),
        _component(
            "edge_cases",
            "Edge cases & robustness",
            weights.edge_cases,
            edge,
            f"{e_pass}/{e_total} hidden edge/robustness/performance tests passed",
        ),
        _component(
            "requirements",
            "Requirement compliance",
            weights.requirements,
            requirement,
            f"{met}/{len(requirements)} requirements fully met "
            f"(partial credit = share of linked tests passed)",
        ),
        _component(
            "security",
            "Security",
            weights.security,
            security,
            f"{len(security_findings)} finding(s); HIGH costs 40%, MEDIUM 15%, LOW 5%",
        ),
        _component(
            "quality",
            "Code quality",
            weights.quality,
            quality,
            f"own tests {own_tests.passed}/{own_tests.total}, "
            f"type hints {metrics.type_hint_ratio:.0%}, docstrings "
            f"{metrics.docstring_ratio:.0%}, hygiene {metrics.hygiene_ratio:.0%}",
        ),
    ]
    # Summing the displayed (rounded) points means the report's arithmetic always adds up.
    raw = min(100, _round_half_up(sum(c.points for c in components)))
    capped = gaming_risk == GamingRisk.HIGH and raw > INTEGRITY_CAP
    ratios = {c.key: c.ratio for c in components}
    return ScoreCard(components, INTEGRITY_CAP if capped else raw, raw, capped, ratios)

"""Pydantic models shared by the evaluator and the API."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field, model_validator


class Severity(StrEnum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class FailureCategory(StrEnum):
    FUNCTIONAL_ERROR = "FUNCTIONAL_ERROR"
    EDGE_CASE_FAILURE = "EDGE_CASE_FAILURE"
    REQUIREMENT_MISSED = "REQUIREMENT_MISSED"
    SECURITY_ISSUE = "SECURITY_ISSUE"
    ROBUSTNESS_FAILURE = "ROBUSTNESS_FAILURE"
    TEST_FAILURE = "TEST_FAILURE"
    ENVIRONMENT_FAILURE = "ENVIRONMENT_FAILURE"
    PERFORMANCE_FAILURE = "PERFORMANCE_FAILURE"
    POSSIBLE_TEST_GAMING = "POSSIBLE_TEST_GAMING"


class CaseCategory(StrEnum):
    NORMAL = "normal"
    EDGE = "edge"
    ROBUSTNESS = "robustness"
    PERFORMANCE = "performance"


class CaseOutcome(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    ERROR = "error"
    SKIPPED = "skipped"
    NOT_RUN = "not_run"  # collected but never reported, e.g. the run timed out


class RequirementStatus(StrEnum):
    MET = "met"
    PARTIAL = "partial"
    NOT_MET = "not_met"
    NOT_EVALUATED = "not_evaluated"


class GamingRisk(StrEnum):
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ScoreWeights(BaseModel):
    """Points each dimension is worth. Must add up to 100 so totals read as x/100."""

    functional: float = Field(40, ge=0)
    edge_cases: float = Field(20, ge=0)
    requirements: float = Field(20, ge=0)
    security: float = Field(10, ge=0)
    quality: float = Field(10, ge=0)

    @model_validator(mode="after")
    def _weights_sum_to_100(self) -> ScoreWeights:
        total = self.functional + self.edge_cases + self.requirements + self.security + self.quality
        if abs(total - 100) > 1e-6:
            raise ValueError(f"score weights must add up to 100, got {total}")
        return self


class Finding(BaseModel):
    severity: Severity
    rule: str
    message: str
    file: str
    line: int | None = None
    recommendation: str | None = None


class CaseResult(BaseModel):
    """Outcome of one hidden evaluator test."""

    test_id: str
    file: str
    category: CaseCategory
    description: str
    outcome: CaseOutcome
    requirements: list[str] = Field(default_factory=list)
    error_type: str | None = None
    error_message: str | None = None


class OwnTestSummary(BaseModel):
    """Results of the tests shipped inside the candidate repository."""

    ran: bool = False
    found: bool = False
    total: int = 0
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    failing_tests: list[str] = Field(default_factory=list)


class RequirementResult(BaseModel):
    id: str
    description: str
    status: RequirementStatus
    passed: int
    total: int
    failing_tests: list[str] = Field(default_factory=list)


class GamingSignal(BaseModel):
    """A heuristic hint of benchmark gaming. Never proof."""

    rule: str
    message: str
    confidence: Severity
    file: str | None = None
    line: int | None = None


class Failure(BaseModel):
    category: FailureCategory
    severity: Severity
    message: str
    test_id: str | None = None
    file: str | None = None
    line: int | None = None
    heuristic: bool = False


class ScoreComponent(BaseModel):
    key: str
    label: str
    weight: float
    ratio: float
    points: float
    explanation: str


class ExecutionRecord(BaseModel):
    name: str
    command: str
    exit_code: int | None
    duration_seconds: float
    timed_out: bool
    stdout: str
    stderr: str
    output_truncated: bool = False
    mode: str


class EvaluationResult(BaseModel):
    evaluation_id: str
    created_at: datetime
    task_id: str
    task_title: str
    task_description: str
    repository_name: str

    overall_score: int
    raw_score: int
    score_cap_applied: bool
    functional_score: int
    edge_case_score: int
    requirement_score: int
    security_score: int
    quality_score: int
    score_breakdown: list[ScoreComponent]

    tests_passed: int
    tests_failed: int
    own_tests: OwnTestSummary
    failures: list[Failure]
    cases: list[CaseResult]
    requirements: list[RequirementResult]
    security_findings: list[Finding]
    quality_findings: list[Finding]
    gaming_signals: list[GamingSignal]
    gaming_risk: GamingRisk
    dependencies: list[str]
    recommendations: list[str]
    executions: list[ExecutionRecord]

    execution_mode: str
    bandit_used: bool
    duration_seconds: float


class ReportResponse(BaseModel):
    evaluation_id: str
    format: str = "text"
    content: str

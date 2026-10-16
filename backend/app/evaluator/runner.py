"""EvaluationRunner: the entry point of the evaluation engine."""

from __future__ import annotations

import shutil
import tempfile
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

from app import config
from app.config import EvaluatorConfig
from app.evaluator.failure_classifier import build_recommendations, classify_failures
from app.evaluator.gaming_detector import assess_risk, detect_gaming
from app.evaluator.requirement_checker import check_requirements
from app.evaluator.sandbox import create_backend
from app.evaluator.scorer import calculate_score
from app.evaluator.security_checker import (
    bandit_available,
    inspect_dependencies,
    merge_findings,
    run_bandit,
    scan_security,
)
from app.evaluator.source_files import ParsedFile, iter_repo_files, load_python_files
from app.evaluator.static_analyzer import analyze_quality
from app.evaluator.tasks import TaskSpec, get_task
from app.evaluator.test_runner import Workspace, run_hidden_tests, run_own_tests
from app.models import CaseOutcome, EvaluationResult, Finding, ScoreWeights

DEFAULT_TASK_ID = "url-validator"


class RepositoryError(ValueError):
    """The candidate repository cannot be evaluated (too large, unreadable, ...)."""


def _copy_repository(source: Path, destination: Path, cfg: EvaluatorConfig) -> None:
    """Copy regular files only (no symlinks, no junk directories) and enforce size limits."""
    if not source.is_dir():
        raise RepositoryError(f"repository path is not a directory: {source}")
    total_bytes = 0
    files = iter_repo_files(source)
    if len(files) > cfg.max_repo_files:
        raise RepositoryError(f"repository has {len(files)} files (limit {cfg.max_repo_files})")
    for path in files:
        total_bytes += path.stat().st_size
        if total_bytes > cfg.max_repo_bytes:
            raise RepositoryError(f"repository exceeds {cfg.max_repo_bytes // 1024 // 1024} MB")
        target = destination / path.relative_to(source)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)  # copyfile drops permission bits, so cleanup always works


def _copy_evaluator_tests(destination: Path) -> None:
    for path in iter_repo_files(config.EVALUATOR_TESTS_DIR):
        target = destination / path.relative_to(config.EVALUATOR_TESTS_DIR)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)


def _create_workspace(root: Path, repo_path: Path, cfg: EvaluatorConfig) -> Workspace:
    ws = Workspace(root, root / "work", root / "hidden", root / "out", root / "home")
    for directory in (ws.work, ws.hidden, ws.out, ws.home):
        directory.mkdir()
    _copy_repository(repo_path, ws.work, cfg)
    _copy_evaluator_tests(ws.hidden)
    return ws


def _security_findings(
    ws: Workspace, files: list[ParsedFile], cfg: EvaluatorConfig
) -> tuple[list[Finding], list[str], bool]:
    findings = scan_security(files)
    dependencies, dependency_findings = inspect_dependencies(ws.work)
    use_bandit = cfg.use_bandit and bandit_available()
    if use_bandit:
        findings = merge_findings(findings, run_bandit(ws.work, ws.home, cfg.bandit_timeout))
    return findings + dependency_findings, dependencies, use_bandit


class EvaluationRunner:
    def __init__(self, cfg: EvaluatorConfig | None = None) -> None:
        self._config = cfg or EvaluatorConfig()

    def evaluate(
        self,
        task_description: str,
        repo_path: Path,
        task_id: str = DEFAULT_TASK_ID,
        weights: ScoreWeights | None = None,
        repository_name: str | None = None,
    ) -> EvaluationResult:
        """Evaluate the repository at ``repo_path``. The original directory is never modified."""
        spec = get_task(task_id)
        started = time.monotonic()
        root = Path(tempfile.mkdtemp(prefix="agentbench-"))
        try:
            ws = _create_workspace(root, repo_path, self._config)
            return self._evaluate_workspace(
                spec,
                task_description,
                ws,
                weights or ScoreWeights(),
                repository_name or repo_path.name,
                started,
            )
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def _evaluate_workspace(
        self,
        spec: TaskSpec,
        task_description: str,
        ws: Workspace,
        weights: ScoreWeights,
        repository_name: str,
        started: float,
    ) -> EvaluationResult:
        cfg = self._config
        mounts = {ws.work: "/work", ws.hidden: "/hidden", ws.out: "/out"}
        backend = create_backend(cfg, mounts if cfg.execution_mode == "docker" else None)

        files = load_python_files(ws.work)
        security, dependencies, bandit_used = _security_findings(ws, files, cfg)
        quality_findings, metrics = analyze_quality(files)

        own_tests, own_run = run_own_tests(backend, ws, cfg)
        cases, hidden_runs = run_hidden_tests(backend, ws, spec, cfg)
        requirements = check_requirements(spec, cases)
        gaming = detect_gaming(files, own_tests, cases)

        syntax_findings = [f for f in quality_findings if f.rule == "QUALITY-SYNTAX-001"]
        failures = classify_failures(
            cases,
            hidden_runs,
            requirements,
            security,
            syntax_findings,
            own_tests,
            own_run,
            gaming,
        )
        gaming_risk = assess_risk(gaming)
        card = calculate_score(
            cases, requirements, security, own_tests, metrics, weights, gaming_risk
        )
        passed = sum(1 for c in cases if c.outcome == CaseOutcome.PASSED)

        return EvaluationResult(
            evaluation_id=uuid.uuid4().hex[:12],
            created_at=datetime.now(UTC),
            task_id=spec.task_id,
            task_title=spec.title,
            task_description=task_description,
            repository_name=repository_name,
            overall_score=card.overall_score,
            raw_score=card.raw_score,
            score_cap_applied=card.cap_applied,
            functional_score=round(card.ratios["functional"] * 100),
            edge_case_score=round(card.ratios["edge_cases"] * 100),
            requirement_score=round(card.ratios["requirements"] * 100),
            security_score=round(card.ratios["security"] * 100),
            quality_score=round(card.ratios["quality"] * 100),
            score_breakdown=card.components,
            tests_passed=passed,
            tests_failed=len(cases) - passed,
            own_tests=own_tests,
            failures=failures,
            cases=cases,
            requirements=requirements,
            security_findings=security,
            quality_findings=quality_findings,
            gaming_signals=gaming,
            gaming_risk=gaming_risk,
            dependencies=dependencies,
            recommendations=build_recommendations(spec, failures, requirements, security),
            executions=[own_run, *hidden_runs],
            execution_mode=backend.mode,
            bandit_used=bandit_used,
            duration_seconds=round(time.monotonic() - started, 2),
        )

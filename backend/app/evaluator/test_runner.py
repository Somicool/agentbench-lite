"""Runs pytest against a candidate repository through the sandbox and parses the results.

Two kinds of runs:
* the candidate's own tests, run inside the candidate repository (JUnit XML output);
* the hidden evaluator tests, run from a private copy, one subprocess per test file so a
  hang in one file cannot wipe out the results of the others (JSON-lines output).
"""

from __future__ import annotations

import json
import os
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

from app.config import EvaluatorConfig
from app.evaluator.sandbox import ProcessResult, SandboxBackend, build_env
from app.evaluator.tasks import TaskSpec
from app.models import (
    CaseCategory,
    CaseOutcome,
    CaseResult,
    ExecutionRecord,
    OwnTestSummary,
)

MAX_RESULT_FILE_BYTES = 5 * 1024 * 1024


@dataclass(frozen=True)
class Workspace:
    """Directories for one evaluation. All of them live inside one temporary directory."""

    root: Path
    work: Path  # copy of the candidate repository
    hidden: Path  # private copy of the evaluator tests
    out: Path  # result files written by pytest
    home: Path  # fake HOME / TEMP for the child process


def to_record(name: str, result: ProcessResult) -> ExecutionRecord:
    return ExecutionRecord(
        name=name,
        command=result.command,
        exit_code=result.exit_code,
        duration_seconds=result.duration_seconds,
        timed_out=result.timed_out,
        stdout=result.stdout,
        stderr=result.stderr,
        output_truncated=result.output_truncated,
        mode=result.mode,
    )


def _python_path(backend: SandboxBackend, ws: Workspace, include_hidden: bool) -> str:
    """PYTHONPATH with evaluator files first so the candidate cannot shadow the plugin."""
    entries = [ws.hidden] if include_hidden else []
    entries += [ws.work, ws.work / "src"]
    separator = ":" if backend.mode == "docker" else os.pathsep  # containers are Linux
    return separator.join(map(str, entries))


# --- the candidate's own tests -----------------------------------------------------------


def _read_capped(path: Path) -> str | None:
    if not path.is_file() or path.stat().st_size > MAX_RESULT_FILE_BYTES:
        return None
    return path.read_text(encoding="utf-8", errors="replace")


def parse_junit(xml_text: str) -> OwnTestSummary:
    """Summarise a pytest JUnit XML report."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return OwnTestSummary(ran=True)
    summary = OwnTestSummary(ran=True, found=False)
    for case in root.iter("testcase"):
        name = f"{case.get('classname', '')}::{case.get('name', '')}".strip(":")
        summary.total += 1
        if case.find("skipped") is not None:
            summary.skipped += 1
        elif case.find("failure") is not None or case.find("error") is not None:
            summary.failed += 1
            summary.failing_tests.append(name)
        else:
            summary.passed += 1
    summary.found = summary.total > 0
    return summary


def run_own_tests(
    backend: SandboxBackend, ws: Workspace, config: EvaluatorConfig
) -> tuple[OwnTestSummary, ExecutionRecord]:
    report = ws.out / "own_tests.xml"
    env = build_env(ws.home, {"PYTHONPATH": _python_path(backend, ws, include_hidden=False)})
    args = ["-m", "pytest", "-p", "no:cacheprovider", "-q", "--tb=short", f"--junitxml={report}"]
    result = backend.run(args, ws.work, env, config.own_tests_timeout)
    xml_text = None if result.timed_out else _read_capped(report)
    summary = parse_junit(xml_text) if xml_text else OwnTestSummary(ran=not result.timed_out)
    return summary, to_record("candidate tests", result)


# --- hidden evaluator tests --------------------------------------------------------------


def _read_json_lines(path: Path) -> list[dict]:
    text = _read_capped(path)
    records: list[dict] = []
    for line in (text or "").splitlines():
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(record, dict):
            records.append(record)
    return records


def _category(value: object) -> CaseCategory:
    try:
        return CaseCategory(value)
    except ValueError:
        return CaseCategory.NORMAL


def _outcome(value: object) -> CaseOutcome:
    try:
        return CaseOutcome(value)
    except ValueError:
        return CaseOutcome.FAILED


def parse_hidden_results(records: list[dict]) -> list[CaseResult]:
    """Merge 'collected' and 'result' records. Collected tests with no result are NOT_RUN."""
    results = {r["id"]: r for r in records if r.get("event") == "result" and "id" in r}
    cases: list[CaseResult] = []
    for record in records:
        if record.get("event") != "collected":
            continue
        for test in record.get("tests", []):
            outcome = results.get(test.get("id"), {})
            cases.append(
                CaseResult(
                    test_id=str(test["id"]),
                    file=str(test.get("file", "")),
                    category=_category(test.get("category")),
                    description=str(test.get("description", test["id"])),
                    outcome=_outcome(outcome.get("outcome")) if outcome else CaseOutcome.NOT_RUN,
                    requirements=[str(r) for r in test.get("requirements", [])],
                    error_type=outcome.get("error_type"),
                    error_message=outcome.get("error_message"),
                )
            )
    return cases


def _hidden_test_files(ws: Workspace, spec: TaskSpec) -> list[str]:
    suite = ws.hidden / spec.tests_subdir
    return sorted(p.relative_to(ws.hidden).as_posix() for p in suite.glob("test_*.py"))


def run_hidden_tests(
    backend: SandboxBackend, ws: Workspace, spec: TaskSpec, config: EvaluatorConfig
) -> tuple[list[CaseResult], list[ExecutionRecord]]:
    cases: list[CaseResult] = []
    executions: list[ExecutionRecord] = []
    for index, test_file in enumerate(_hidden_test_files(ws, spec)):
        results_file = ws.out / f"hidden_{index}.jsonl"
        env = build_env(
            ws.home,
            {
                "PYTHONPATH": _python_path(backend, ws, include_hidden=True),
                "AGENTBENCH_RESULTS": str(results_file),
                "AGENTBENCH_MODULE": spec.module_name,
                "AGENTBENCH_FUNCTION": spec.function_name,
            },
        )
        args = ["-m", "pytest", "-p", "agentbench_plugin", "-q", "--tb=line", test_file]
        result = backend.run(args, ws.hidden, env, config.hidden_tests_timeout)
        cases += parse_hidden_results(_read_json_lines(results_file))
        executions.append(to_record(f"hidden tests: {Path(test_file).name}", result))
    return cases, executions

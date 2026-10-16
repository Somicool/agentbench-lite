"""Pytest plugin shared by every hidden evaluator test suite.

It does three things:
* loads the candidate callable (module/function names come from the environment),
* tags each test with its scoring category and requirement ids,
* appends one JSON line per test to the file named by AGENTBENCH_RESULTS, so partial results
  survive when the run is killed by a timeout.
"""

from __future__ import annotations

import importlib
import json
import os

import pytest

RESULTS_ENV = "AGENTBENCH_RESULTS"
MODULE_ENV = "AGENTBENCH_MODULE"
FUNCTION_ENV = "AGENTBENCH_FUNCTION"
MAX_MESSAGE_CHARS = 300


class CandidateLoadError(Exception):
    """The candidate module or function could not be imported."""


def _emit(record: dict) -> None:
    path = os.environ.get(RESULTS_ENV)
    if path:
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(record) + "\n")


def _description(item: pytest.Item) -> str:
    doc = (getattr(item.function, "__doc__", None) or item.name).strip().splitlines()[0]
    callspec = getattr(item, "callspec", None)
    return f"{doc} [{callspec.id}]" if callspec else doc


def _describe(item: pytest.Item) -> dict:
    category = item.get_closest_marker("category")
    requirements = [arg for marker in item.iter_markers("requirement") for arg in marker.args]
    return {
        "id": item.nodeid,
        "file": item.path.name,
        "category": category.args[0] if category else "normal",
        "description": _description(item),
        "requirements": sorted(set(requirements)),
    }


def _short(text: str) -> str:
    first_line = text.strip().splitlines()[0] if text.strip() else ""
    return first_line[:MAX_MESSAGE_CHARS]


def pytest_collection_finish(session: pytest.Session) -> None:
    _emit({"event": "collected", "tests": [_describe(item) for item in session.items]})


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo):
    outcome = yield
    report = outcome.get_result()
    if not (report.when == "call" or (report.when == "setup" and not report.passed)):
        return
    record = {"event": "result", "id": item.nodeid, "outcome": report.outcome}
    if report.when == "setup" and report.failed:
        record["outcome"] = "error"
    if call.excinfo is not None:
        record["error_type"] = call.excinfo.typename
        record["error_message"] = _short(str(call.excinfo.value))
    _emit(record)


@pytest.fixture(scope="session")
def candidate():
    """The function under test, imported from the candidate repository."""
    module_name = os.environ[MODULE_ENV]
    function_name = os.environ[FUNCTION_ENV]
    try:
        module = importlib.import_module(module_name)
        func = getattr(module, function_name)
    except (Exception, SystemExit) as exc:
        raise CandidateLoadError(
            f"cannot load {module_name}.{function_name}: {type(exc).__name__}: {exc}"
        ) from None
    if not callable(func):
        raise CandidateLoadError(f"{module_name}.{function_name} is not callable")
    return func

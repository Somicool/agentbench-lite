from __future__ import annotations

import subprocess
import time

import pytest

from app.config import EvaluatorConfig
from app.evaluator.sandbox import DockerBackend, LocalBackend, build_env


def _run(tmp_path, code: str, timeout: float = 10, extra: dict[str, str] | None = None):
    backend = LocalBackend(max_output_chars=1000)
    return backend.run(["-c", code], tmp_path, build_env(tmp_path / "home", extra), timeout)


def test_timeout_kills_runaway_process(tmp_path):
    started = time.monotonic()
    result = _run(tmp_path, "while True: pass", timeout=1)
    assert result.timed_out
    assert result.exit_code is None
    assert time.monotonic() - started < 15


def test_successful_run_captures_output_and_exit_code(tmp_path):
    result = _run(tmp_path, "import sys; print('out'); print('err', file=sys.stderr); sys.exit(3)")
    assert (result.exit_code, result.stdout.strip(), result.stderr.strip()) == (3, "out", "err")
    assert not result.timed_out
    assert result.duration_seconds >= 0


def test_host_environment_variables_are_not_inherited(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTBENCH_TEST_SECRET", "top-secret")
    result = _run(tmp_path, "import os; print(os.environ.get('AGENTBENCH_TEST_SECRET'))")
    assert result.stdout.strip() == "None"


def test_explicit_environment_variables_are_passed(tmp_path):
    result = _run(tmp_path, "import os; print(os.environ['MY_FLAG'])", extra={"MY_FLAG": "on"})
    assert result.stdout.strip() == "on"


def test_output_is_truncated(tmp_path):
    result = _run(tmp_path, "print('x' * 100000)")
    assert len(result.stdout) == 1000
    assert result.output_truncated


def test_temp_directory_points_inside_the_sandbox(tmp_path):
    result = _run(tmp_path, "import tempfile; print(tempfile.gettempdir())")
    assert str(tmp_path) in result.stdout


def test_docker_backend_builds_an_isolated_command(tmp_path, monkeypatch):
    """Docker itself is not available in CI, so this only checks the command we would run."""
    captured: list[str] = []

    def fake_run(args, **kwargs):
        captured.extend(args)
        return subprocess.CompletedProcess(args, 0, b"ok", b"")

    monkeypatch.setattr(subprocess, "run", fake_run)
    work = tmp_path / "work"
    backend = DockerBackend(EvaluatorConfig(execution_mode="docker"), {work: "/work"})
    env = {"PYTHONPATH": str(work), "PATH": "host-path", "HOME": "host-home"}
    result = backend.run(["-m", "pytest", str(work / "tests")], work, env, timeout=5)

    assert result.stdout == "ok" and result.mode == "docker"
    assert captured[captured.index("--network") + 1] == "none"
    assert "--read-only" in captured and "--cap-drop" in captured
    assert "PYTHONPATH=/work" in captured  # host paths are rewritten
    assert "/work/tests" in captured
    assert not any("host-path" in arg or "host-home" in arg for arg in captured)


def test_config_rejects_unknown_execution_mode(monkeypatch):
    monkeypatch.setenv("AGENTBENCH_EXECUTION_MODE", "kubernetes")
    with pytest.raises(ValueError, match="kubernetes"):
        EvaluatorConfig.from_env()

"""Process isolation for running untrusted candidate code.

Two backends share one interface:

* LocalBackend: a child Python process with a scrubbed environment, a hard timeout,
  process-tree kill and (on POSIX) resource limits. This is a *process boundary*, not a
  security sandbox: the child still runs as the current user on the host.
* DockerBackend: one throwaway container per run with no network, a read-only root
  filesystem, dropped capabilities and memory/CPU/PID limits. Prefer this for untrusted code.
"""

from __future__ import annotations

import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import uuid
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import Protocol

from app.config import EvaluatorConfig

_IS_WINDOWS = os.name == "nt"
_KILL_GRACE_SECONDS = 5

# Applied through an exec'd bootstrap so we avoid preexec_fn, which is unsafe with threads.
_POSIX_BOOTSTRAP = (
    "import os, resource, sys\n"
    "cpu, mem, fsize = (int(v) for v in sys.argv[1:4])\n"
    "resource.setrlimit(resource.RLIMIT_CPU, (cpu, cpu))\n"
    "resource.setrlimit(resource.RLIMIT_AS, (mem, mem))\n"
    "resource.setrlimit(resource.RLIMIT_FSIZE, (fsize, fsize))\n"
    "os.execv(sys.executable, [sys.executable] + sys.argv[4:])\n"
)
_MEMORY_LIMIT_BYTES = 2 * 1024**3
_FILE_SIZE_LIMIT_BYTES = 50 * 1024**2


@dataclass(frozen=True)
class ProcessResult:
    exit_code: int | None
    stdout: str
    stderr: str
    duration_seconds: float
    timed_out: bool
    output_truncated: bool
    command: str
    mode: str


class SandboxBackend(Protocol):
    mode: str

    def run(
        self,
        python_args: list[str],
        cwd: Path,
        env: dict[str, str],
        timeout: float,
    ) -> ProcessResult: ...


def build_env(home: Path, extra: dict[str, str] | None = None) -> dict[str, str]:
    """Return a minimal environment. Nothing is inherited, so host secrets cannot leak."""
    scratch = home / "tmp"
    scratch.mkdir(parents=True, exist_ok=True)
    env = {
        "PATH": str(Path(sys.executable).parent) if _IS_WINDOWS else "/usr/bin:/bin",
        "HOME": str(home),
        "TMPDIR": str(scratch),
        "TEMP": str(scratch),
        "TMP": str(scratch),
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONHASHSEED": "0",
        "PYTHONIOENCODING": "utf-8",
        "PYTHONUTF8": "1",
        "NO_COLOR": "1",
    }
    if _IS_WINDOWS:
        env["SYSTEMROOT"] = os.environ.get("SYSTEMROOT", r"C:\Windows")
        env["USERPROFILE"] = str(home)
    env.update(extra or {})
    return env


def _read_capped(handle, limit: int) -> tuple[str, bool]:
    handle.seek(0, os.SEEK_END)
    size = handle.tell()
    handle.seek(0)
    data = handle.read(limit)
    return data.decode("utf-8", errors="replace"), size > limit


def _kill_process_tree(process: subprocess.Popen) -> None:
    try:
        if _IS_WINDOWS:
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                capture_output=True,
                timeout=_KILL_GRACE_SECONDS,
                check=False,
            )
        else:
            os.killpg(process.pid, signal.SIGKILL)
    except (OSError, subprocess.SubprocessError):
        process.kill()


class LocalBackend:
    mode = "local"

    def __init__(self, max_output_chars: int) -> None:
        self._max_output_chars = max_output_chars

    def run(
        self,
        python_args: list[str],
        cwd: Path,
        env: dict[str, str],
        timeout: float,
    ) -> ProcessResult:
        command = [sys.executable, *python_args]
        popen_kwargs: dict = {}
        if _IS_WINDOWS:
            popen_kwargs["creationflags"] = (
                subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
            )
        else:
            popen_kwargs["start_new_session"] = True
            command = [
                sys.executable,
                "-c",
                _POSIX_BOOTSTRAP,
                str(int(timeout) + 5),
                str(_MEMORY_LIMIT_BYTES),
                str(_FILE_SIZE_LIMIT_BYTES),
                *python_args,
            ]

        # Output goes to temp files, not pipes: no pipe deadlocks and no unbounded buffering.
        with tempfile.TemporaryFile() as out_file, tempfile.TemporaryFile() as err_file:
            started = time.monotonic()
            try:
                process = subprocess.Popen(
                    command,
                    cwd=cwd,
                    env=env,
                    stdin=subprocess.DEVNULL,
                    stdout=out_file,
                    stderr=err_file,
                    **popen_kwargs,
                )
            except OSError as exc:
                return ProcessResult(
                    None,
                    "",
                    f"failed to start process: {exc}",
                    0.0,
                    False,
                    False,
                    " ".join(python_args),
                    self.mode,
                )
            timed_out = False
            try:
                process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                timed_out = True
                _kill_process_tree(process)
                process.wait(timeout=_KILL_GRACE_SECONDS)
            duration = time.monotonic() - started
            stdout, out_cut = _read_capped(out_file, self._max_output_chars)
            stderr, err_cut = _read_capped(err_file, self._max_output_chars)

        return ProcessResult(
            exit_code=None if timed_out else process.returncode,
            stdout=stdout,
            stderr=stderr,
            duration_seconds=round(duration, 3),
            timed_out=timed_out,
            output_truncated=out_cut or err_cut,
            command="python " + " ".join(python_args),
            mode=self.mode,
        )


class DockerBackend:
    """Runs each command in a disposable, network-less container.

    The evaluator workspace is bind-mounted, so host paths in arguments and environment
    values are rewritten to their in-container locations.
    """

    mode = "docker"

    def __init__(self, config: EvaluatorConfig, mounts: dict[Path, str]) -> None:
        self._config = config
        self._mounts = mounts  # host directory -> container path

    def _translate(self, value: str) -> str:
        """Rewrite host paths to container paths, also turning Windows backslashes into slashes."""
        for host, container in self._mounts.items():
            pattern = re.escape(str(host)) + r"((?:[\\/][^:;]+)?)"
            value = re.sub(pattern, partial(_rewrite_match, container), value)
        return value

    def run(
        self,
        python_args: list[str],
        cwd: Path,
        env: dict[str, str],
        timeout: float,
    ) -> ProcessResult:
        container_name = f"agentbench-{uuid.uuid4().hex[:12]}"
        docker_args = [
            "docker",
            "run",
            "--rm",
            "--name",
            container_name,
            "--network",
            "none",
            "--memory",
            self._config.docker_memory,
            "--cpus",
            "1",
            "--pids-limit",
            "128",
            "--read-only",
            "--tmpfs",
            "/tmp:rw,size=64m",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
        ]
        if hasattr(os, "getuid"):
            docker_args += ["--user", f"{os.getuid()}:{os.getgid()}"]
        for host, container in self._mounts.items():
            docker_args += ["-v", f"{host}:{container}"]
        docker_args += ["-w", self._translate(str(cwd))]
        for key, value in env.items():
            if key in {"PATH", "HOME", "TMPDIR", "TEMP", "TMP", "SYSTEMROOT", "USERPROFILE"}:
                continue
            docker_args += ["-e", f"{key}={self._translate(value)}"]
        docker_args += ["-e", "HOME=/tmp", self._config.docker_image, "python"]
        docker_args += [self._translate(arg) for arg in python_args]

        started = time.monotonic()
        try:
            completed = subprocess.run(
                docker_args,
                capture_output=True,
                timeout=timeout + 15,  # container start-up is outside the candidate's budget
                check=False,
            )
        except subprocess.TimeoutExpired:
            # Killing the CLI does not stop the container, so stop it explicitly.
            subprocess.run(["docker", "kill", container_name], capture_output=True, check=False)
            return ProcessResult(
                None,
                "",
                "",
                round(time.monotonic() - started, 3),
                True,
                False,
                "docker run ... python " + " ".join(python_args),
                self.mode,
            )
        except OSError as exc:
            return ProcessResult(
                None,
                "",
                f"docker is not available: {exc}",
                0.0,
                False,
                False,
                "docker run ...",
                self.mode,
            )
        limit = self._config.max_output_chars
        return ProcessResult(
            exit_code=completed.returncode,
            stdout=completed.stdout.decode("utf-8", errors="replace")[:limit],
            stderr=completed.stderr.decode("utf-8", errors="replace")[:limit],
            duration_seconds=round(time.monotonic() - started, 3),
            timed_out=False,
            output_truncated=len(completed.stdout) > limit or len(completed.stderr) > limit,
            command="docker run ... python " + " ".join(python_args),
            mode=self.mode,
        )


def _rewrite_match(container: str, match: re.Match[str]) -> str:
    return container + match.group(1).replace("\\", "/")


def docker_available() -> bool:
    return shutil.which("docker") is not None


def create_backend(
    config: EvaluatorConfig, mounts: dict[Path, str] | None = None
) -> SandboxBackend:
    if config.execution_mode == "docker":
        if not docker_available():
            raise RuntimeError("AGENTBENCH_EXECUTION_MODE=docker but 'docker' is not on PATH")
        return DockerBackend(config, mounts or {})
    return LocalBackend(config.max_output_chars)

"""Runtime configuration. Everything can be overridden with environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _path_from_env(name: str, default: Path) -> Path:
    return Path(os.environ.get(name, str(default))).resolve()


EXAMPLES_DIR = _path_from_env("AGENTBENCH_EXAMPLES_DIR", PROJECT_ROOT / "examples")
EVALUATOR_TESTS_DIR = _path_from_env(
    "AGENTBENCH_EVALUATOR_TESTS_DIR", PROJECT_ROOT / "evaluator_tests"
)

MAX_UPLOAD_BYTES = 5 * 1024 * 1024


@dataclass(frozen=True)
class EvaluatorConfig:
    """Limits and switches for one evaluation run."""

    execution_mode: str = "local"  # "local" (subprocess) or "docker" (container per run)
    own_tests_timeout: float = 30.0
    hidden_tests_timeout: float = 20.0
    use_bandit: bool = True
    bandit_timeout: float = 60.0
    max_repo_bytes: int = 20 * 1024 * 1024
    max_repo_files: int = 500
    max_output_chars: int = 20_000
    docker_image: str = "agentbench-sandbox"
    docker_memory: str = "512m"

    @classmethod
    def from_env(cls) -> EvaluatorConfig:
        defaults = cls()
        mode = os.environ.get("AGENTBENCH_EXECUTION_MODE", defaults.execution_mode).lower()
        if mode not in {"local", "docker"}:
            raise ValueError(f"AGENTBENCH_EXECUTION_MODE must be 'local' or 'docker', got {mode!r}")
        return cls(
            execution_mode=mode,
            own_tests_timeout=float(os.environ.get("AGENTBENCH_OWN_TESTS_TIMEOUT", 30)),
            hidden_tests_timeout=float(os.environ.get("AGENTBENCH_HIDDEN_TESTS_TIMEOUT", 20)),
            use_bandit=os.environ.get("AGENTBENCH_USE_BANDIT", "1") != "0",
            docker_image=os.environ.get("AGENTBENCH_DOCKER_IMAGE", defaults.docker_image),
        )

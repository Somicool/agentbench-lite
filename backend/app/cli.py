"""Command-line entry point: ``python -m app.cli examples/buggy_solution``."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from app.config import EvaluatorConfig
from app.evaluator.runner import DEFAULT_TASK_ID, EvaluationRunner, RepositoryError
from app.evaluator.tasks import get_task
from app.services.report_generator import generate_text_report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate a candidate repository.")
    parser.add_argument("repository", type=Path, help="path to the candidate repository")
    parser.add_argument("--task", default=DEFAULT_TASK_ID, help="task id (default: %(default)s)")
    parser.add_argument("--json", action="store_true", help="print the full result as JSON")
    args = parser.parse_args(argv)

    spec = get_task(args.task)
    runner = EvaluationRunner(EvaluatorConfig.from_env())
    try:
        result = runner.evaluate(spec.default_description, args.repository, args.task)
    except RepositoryError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(result.model_dump_json(indent=2))
    else:
        sys.stdout.reconfigure(encoding="utf-8")
        print(generate_text_report(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

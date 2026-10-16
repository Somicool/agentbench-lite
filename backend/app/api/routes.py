"""HTTP routes. Evaluations run in a worker thread; candidate code never runs in this process."""

from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, ValidationError

from app import config
from app.evaluator.runner import DEFAULT_TASK_ID, EvaluationRunner, RepositoryError
from app.evaluator.sandbox import docker_available
from app.evaluator.security_checker import bandit_available
from app.evaluator.tasks import TASKS, UnknownTaskError, get_task
from app.models import EvaluationResult, ReportResponse, ScoreWeights
from app.services.archive import ArchiveError, extract_zip
from app.services.evaluation_store import EvaluationStore
from app.services.report_generator import generate_text_report

router = APIRouter()
store = EvaluationStore()

MAX_DESCRIPTION_CHARS = 10_000
_UPLOAD_CHUNK = 64 * 1024


class ExampleInfo(BaseModel):
    name: str
    description: str


class TaskInfo(BaseModel):
    task_id: str
    title: str
    default_description: str
    requirements: list[str]


EXAMPLE_DESCRIPTIONS = {
    "good_solution": "Correct implementation",
    "buggy_solution": "Realistic bugs: empty input, hostnames, schemes, unsafe eval",
    "cheating_solution": "Hardcoded answers that pass the visible tests only",
}


def list_examples() -> list[str]:
    if not config.EXAMPLES_DIR.is_dir():
        return []
    return sorted(p.name for p in config.EXAMPLES_DIR.iterdir() if p.is_dir())


def _parse_weights(raw: str | None) -> ScoreWeights | None:
    if not raw:
        return None
    try:
        return ScoreWeights.model_validate(json.loads(raw))
    except (json.JSONDecodeError, ValidationError) as exc:
        raise HTTPException(status_code=422, detail=f"invalid weights: {exc}") from exc


def _save_upload(upload: UploadFile, destination: Path) -> None:
    """Stream the upload to disk, refusing anything above the size limit."""
    size = 0
    with destination.open("wb") as sink:
        while chunk := upload.file.read(_UPLOAD_CHUNK):
            size += len(chunk)
            if size > config.MAX_UPLOAD_BYTES:
                raise HTTPException(status_code=413, detail="upload exceeds the 5 MB limit")
            sink.write(chunk)


@router.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "execution_mode": config.EvaluatorConfig.from_env().execution_mode,
        "bandit_available": bandit_available(),
        "docker_available": docker_available(),
    }


@router.get("/api/examples")
def examples() -> list[ExampleInfo]:
    return [
        ExampleInfo(name=n, description=EXAMPLE_DESCRIPTIONS.get(n, "")) for n in list_examples()
    ]


@router.get("/api/tasks")
def tasks() -> list[TaskInfo]:
    return [
        TaskInfo(
            task_id=t.task_id,
            title=t.title,
            default_description=t.default_description,
            requirements=[r.description for r in t.requirements],
        )
        for t in TASKS.values()
    ]


def _run_evaluation(
    description: str, repo_path: Path, task_id: str, weights: ScoreWeights | None, name: str
) -> EvaluationResult:
    runner = EvaluationRunner(config.EvaluatorConfig.from_env())
    try:
        return runner.evaluate(description, repo_path, task_id, weights, name)
    except RepositoryError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:  # e.g. docker mode requested but docker is not installed
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/api/evaluate")
def evaluate(
    task_description: str = Form(..., min_length=1, max_length=MAX_DESCRIPTION_CHARS),
    task_id: str = Form(DEFAULT_TASK_ID),
    example: str | None = Form(None),
    repository: UploadFile | None = File(None),
    weights: str | None = Form(None),
) -> EvaluationResult:
    """Evaluate a bundled example or an uploaded ZIP against a task."""
    try:
        get_task(task_id)
    except UnknownTaskError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if bool(example) == bool(repository):
        raise HTTPException(
            status_code=400, detail="provide exactly one of 'example' or 'repository'"
        )
    parsed_weights = _parse_weights(weights)

    if example:
        if example not in list_examples():  # allow-list: never build paths from raw input
            raise HTTPException(status_code=404, detail=f"unknown example '{example}'")
        result = _run_evaluation(
            task_description, config.EXAMPLES_DIR / example, task_id, parsed_weights, example
        )
    else:
        scratch = Path(tempfile.mkdtemp(prefix="agentbench-upload-"))
        try:
            archive = scratch / "upload.zip"
            _save_upload(repository, archive)
            try:
                root = extract_zip(archive, scratch / "repo")
            except ArchiveError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            result = _run_evaluation(
                task_description, root, task_id, parsed_weights, repository.filename or "upload.zip"
            )
        finally:
            shutil.rmtree(scratch, ignore_errors=True)

    store.save(result)
    return result


def _get_or_404(evaluation_id: str) -> EvaluationResult:
    result = store.get(evaluation_id)
    if result is None:
        raise HTTPException(status_code=404, detail="evaluation not found")
    return result


@router.get("/api/evaluations/{evaluation_id}")
def get_evaluation(evaluation_id: str) -> EvaluationResult:
    return _get_or_404(evaluation_id)


@router.post("/api/evaluations/{evaluation_id}/report")
def create_report(evaluation_id: str) -> ReportResponse:
    result = _get_or_404(evaluation_id)
    return ReportResponse(evaluation_id=evaluation_id, content=generate_text_report(result))

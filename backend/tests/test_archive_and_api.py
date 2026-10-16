from __future__ import annotations

import io
import json
import zipfile

import pytest
from fastapi.testclient import TestClient

from app.config import EXAMPLES_DIR
from app.main import app
from app.services.archive import MAX_MEMBER_BYTES, ArchiveError, extract_zip

client = TestClient(app)
DESCRIPTION = "Build a URL validator"


def make_zip(path, entries: dict[str, str | bytes]) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        for name, content in entries.items():
            archive.writestr(name, content)


def zip_bytes(entries: dict[str, str | bytes]) -> bytes:
    buffer = io.BytesIO()
    make_zip(buffer, entries)
    return buffer.getvalue()


# --- archive safety ------------------------------------------------------------------


def test_path_traversal_is_rejected(tmp_path):
    make_zip(tmp_path / "evil.zip", {"../escape.py": "x = 1"})
    with pytest.raises(ArchiveError, match="unsafe path"):
        extract_zip(tmp_path / "evil.zip", tmp_path / "out")
    assert not (tmp_path / "escape.py").exists()


@pytest.mark.parametrize("name", ["/etc/passwd", "C:/Windows/evil.py", "a/../../b.py"])
def test_absolute_and_nested_traversal_paths_are_rejected(tmp_path, name):
    make_zip(tmp_path / "evil.zip", {name: "x"})
    with pytest.raises(ArchiveError):
        extract_zip(tmp_path / "evil.zip", tmp_path / "out")


def test_symlink_entries_are_rejected(tmp_path):
    archive_path = tmp_path / "link.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        info = zipfile.ZipInfo("link.py")
        info.external_attr = 0o120777 << 16
        archive.writestr(info, "/etc/passwd")
    with pytest.raises(ArchiveError, match="symbolic links"):
        extract_zip(archive_path, tmp_path / "out")


def test_oversized_members_are_rejected(tmp_path):
    make_zip(tmp_path / "big.zip", {"big.py": b"0" * (MAX_MEMBER_BYTES + 1)})
    with pytest.raises(ArchiveError, match="larger than"):
        extract_zip(tmp_path / "big.zip", tmp_path / "out")


def test_non_zip_files_are_rejected(tmp_path):
    (tmp_path / "x.zip").write_bytes(b"not a zip")
    with pytest.raises(ArchiveError, match="not a valid ZIP"):
        extract_zip(tmp_path / "x.zip", tmp_path / "out")


def test_single_top_level_folder_is_unwrapped(tmp_path):
    make_zip(tmp_path / "repo.zip", {"project/url_validator.py": "x = 1"})
    root = extract_zip(tmp_path / "repo.zip", tmp_path / "out")
    assert (root / "url_validator.py").is_file()


# --- API -----------------------------------------------------------------------------


def test_health():
    body = client.get("/health").json()
    assert body["status"] == "ok" and body["execution_mode"] == "local"


def test_examples_and_tasks_are_listed():
    names = {e["name"] for e in client.get("/api/examples").json()}
    assert {"good_solution", "buggy_solution", "cheating_solution"} <= names
    (task,) = client.get("/api/tasks").json()
    assert task["task_id"] == "url-validator" and task["requirements"]


def test_evaluate_example_then_fetch_and_report():
    response = client.post(
        "/api/evaluate", data={"task_description": DESCRIPTION, "example": "buggy_solution"}
    )
    assert response.status_code == 200
    result = response.json()
    assert 0 < result["overall_score"] < 100
    assert result["failures"] and result["score_breakdown"]

    fetched = client.get(f"/api/evaluations/{result['evaluation_id']}")
    assert fetched.status_code == 200
    assert fetched.json()["overall_score"] == result["overall_score"]

    report = client.post(f"/api/evaluations/{result['evaluation_id']}/report").json()
    assert report["content"].startswith("AGENTBENCH LITE")
    assert "[SECURITY_ISSUE]" in report["content"]


def test_evaluate_uploaded_zip():
    source = (EXAMPLES_DIR / "good_solution" / "url_validator.py").read_text(encoding="utf-8")
    payload = zip_bytes({"my-repo/url_validator.py": source})
    response = client.post(
        "/api/evaluate",
        data={"task_description": DESCRIPTION},
        files={"repository": ("my-repo.zip", payload, "application/zip")},
    )
    assert response.status_code == 200
    assert response.json()["repository_name"] == "my-repo.zip"
    assert response.json()["functional_score"] == 100


def test_custom_weights_are_applied():
    weights = {"functional": 100, "edge_cases": 0, "requirements": 0, "security": 0, "quality": 0}
    response = client.post(
        "/api/evaluate",
        data={
            "task_description": DESCRIPTION,
            "example": "good_solution",
            "weights": json.dumps(weights),
        },
    )
    assert response.json()["score_breakdown"][0]["weight"] == 100


def test_invalid_weights_are_rejected():
    response = client.post(
        "/api/evaluate",
        data={
            "task_description": DESCRIPTION,
            "example": "good_solution",
            "weights": '{"functional": 90}',
        },
    )
    assert response.status_code == 422


@pytest.mark.parametrize(
    ("data", "status"),
    [
        ({"task_description": DESCRIPTION}, 400),  # neither example nor upload
        ({"task_description": DESCRIPTION, "example": "../../etc"}, 404),
        ({"task_description": DESCRIPTION, "example": "good_solution", "task_id": "nope"}, 404),
        ({"task_description": ""}, 422),
    ],
)
def test_bad_requests(data, status):
    assert client.post("/api/evaluate", data=data).status_code == status


def test_malicious_upload_is_rejected_with_400():
    payload = zip_bytes({"../evil.py": "x = 1"})
    response = client.post(
        "/api/evaluate",
        data={"task_description": DESCRIPTION},
        files={"repository": ("evil.zip", payload, "application/zip")},
    )
    assert response.status_code == 400 and "unsafe path" in response.json()["detail"]


def test_unknown_evaluation_is_404():
    assert client.get("/api/evaluations/missing").status_code == 404
    assert client.post("/api/evaluations/missing/report").status_code == 404

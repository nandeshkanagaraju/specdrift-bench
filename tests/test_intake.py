"""User-supplied projects: paste and zip both become a workspace the checker can run."""

from __future__ import annotations

import io
import zipfile

import pytest
from fastapi.testclient import TestClient

from specdrift.api.app import create_app
from specdrift.intake import IntakeError, materialize_files, materialize_zip

SPEC = "- **R01** The limit MUST be 3.\n"
CODE = "LIMIT = 3\n\ndef allow(n):\n    return n < LIMIT\n"


def _zip(entries: dict[str, str]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, text in entries.items():
            archive.writestr(name, text)
    return buffer.getvalue()


def test_pasted_project_is_written_under_src(settings):
    record = materialize_files(settings, "My Service", SPEC, [("service.py", CODE)])
    assert record.rules[0].id == "R01"
    assert (record.root / "spec.md").is_file()
    assert (record.root / "src" / "service.py").read_text(encoding="utf-8") == CODE
    assert record.name == "my-service"


def test_a_folder_of_files_is_identified_without_a_separate_spec(settings):
    record = materialize_files(
        settings,
        "library",
        "",
        [
            ("README.md", "A readme, not the spec.\n"),
            ("docs/requirements.md", "- **R01** The limit MUST be 3.\n"),
            ("src/app.py", CODE),
            ("notes.py", "LIMIT = 9\n"),
        ],
    )
    assert [rule.id for rule in record.rules] == ["R01"]
    assert record.spec_path == "docs/requirements.md"
    assert [item.path for item in record.files] == ["src/app.py"]
    assert any("src/" in warning for warning in record.warnings)


def test_a_named_spec_wins_over_other_markdown(settings):
    record = materialize_files(
        settings,
        "boxed",
        "",
        [
            ("notes.md", "- **R09** Something MUST be 9.\n"),
            ("specification.md", SPEC),
            ("app.py", CODE),
        ],
    )
    assert record.rules[0].id == "R01"
    assert record.spec_path == "specification.md"


def test_a_spec_without_numbered_rules_is_rejected(settings):
    with pytest.raises(IntakeError, match="No numbered rules"):
        materialize_files(settings, "x", "just some prose\n", [("a.py", CODE)])


def test_a_path_that_escapes_the_workspace_is_rejected(settings):
    with pytest.raises(IntakeError, match="Unsafe path"):
        materialize_files(settings, "x", SPEC, [("../secrets.py", CODE)])


def test_zip_unwraps_a_single_root_folder_and_keeps_src(settings):
    data = _zip(
        {
            "demo/spec.md": SPEC,
            "demo/src/app.py": CODE,
            "demo/tests/test_app.py": "def test_ok():\n    assert True\n",
            "demo/README.md": "ignore me\n",
        }
    )
    record = materialize_zip(settings, "demo.zip", data)
    assert (record.root / "src" / "app.py").is_file()
    assert not (record.root / "src" / "tests").exists()
    assert any("tests" in warning for warning in record.warnings)


def test_zip_rejects_a_path_that_climbs_out(settings):
    data = _zip({"../spec.md": SPEC, "app.py": CODE})
    with pytest.raises(IntakeError, match="unsafe path"):
        materialize_zip(settings, "bad", data)


@pytest.fixture()
def client(settings):
    return TestClient(create_app(settings))


def test_upload_then_check_streams_a_summary(client):
    created = client.post(
        "/api/uploads",
        json={"name": "tiny", "spec": SPEC, "files": [{"path": "app.py", "source": CODE}]},
    )
    assert created.status_code == 200, created.text
    upload_id = created.json()["id"]
    assert created.json()["rules"][0]["id"] == "R01"

    fetched = client.get(f"/api/uploads/{upload_id}")
    assert fetched.status_code == 200
    assert fetched.json()["files"][0]["path"] == "src/app.py"

    with client.stream("POST", "/api/check", json={"upload_id": upload_id}) as response:
        assert response.status_code == 200
        events = [line for line in response.iter_lines() if line.startswith("event:")]

    assert "event: verdict" in events
    assert events[-1] == "event: summary"


def test_archive_finds_a_spec_that_is_not_named_spec_md(client):
    response = client.post(
        "/api/uploads/archive?name=boxed",
        content=_zip(
            {
                "proj/README.md": "not the spec\n",
                "proj/docs/requirements.md": SPEC,
                "proj/src/lib.py": CODE,
            }
        ),
        headers={"Content-Type": "application/zip"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["spec_path"] == "docs/requirements.md"
    assert body["rules"][0]["id"] == "R01"
    assert body["files"][0]["path"] == "src/lib.py"


def test_archive_upload_accepts_a_zip_body(client):
    response = client.post(
        "/api/uploads/archive?name=boxed",
        content=_zip({"spec.md": SPEC, "lib.py": CODE}),
        headers={"Content-Type": "application/zip"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["name"] == "boxed"
    assert response.json()["files"][0]["path"] == "src/lib.py"


def test_unknown_upload_is_404(client):
    assert client.get("/api/uploads/nope").status_code == 404
    assert client.post("/api/check", json={"upload_id": "nope"}).status_code == 404


def test_a_check_needs_a_project_or_an_upload(client):
    assert client.post("/api/check", json={}).status_code == 422

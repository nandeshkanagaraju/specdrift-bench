import pytest
from fastapi.testclient import TestClient

from specdrift.api.app import create_app
from specdrift.api.store import changed_lines


@pytest.fixture()
def client(settings):
    """Serves the repository's real results, with scratch dirs for anything written."""
    from specdrift.config import REPO_ROOT

    settings.results_dir = REPO_ROOT / "results"
    settings.work_dir = REPO_ROOT / "work"
    settings.cases_dir = REPO_ROOT / "cases"
    return TestClient(create_app(settings))


def test_changed_lines_marks_the_replacement():
    assert changed_lines("a\nb\nc\n", "a\nB\nc\n") == [2]


def test_changed_lines_marks_insertions():
    assert changed_lines("a\nc\n", "a\nb\nc\n") == [2]


def test_changed_lines_is_empty_for_identical_text():
    assert changed_lines("a\nb\n", "a\nb\n") == []


def test_summary_reports_the_dataset(client):
    body = client.get("/api/summary").json()
    assert body["valid_cases"] >= 60
    assert body["drift_cases"] + body["negative_cases"] == body["valid_cases"]
    assert 0.0 <= body["escapes_rate"] <= 1.0
    assert {c["category"] for c in body["categories"]} >= {"D1", "D8", "N1"}


def test_summary_lists_every_detector_that_has_run(client):
    names = {d["name"] for d in client.get("/api/summary").json()["detectors"]}
    assert names == {"specguard", "keyword", "wholefile"}


def test_metrics_returns_every_scored_detector(client):
    body = client.get("/api/metrics").json()
    assert len(body["detectors"]) == 3
    first = body["detectors"][0]
    assert {"precision", "recall", "f1", "false_alarm_rate"} <= set(first["overall"])


def test_metrics_can_be_filtered(client):
    body = client.get("/api/metrics?detector=keyword").json()
    assert [d["detector"] for d in body["detectors"]] == ["keyword"]


def test_metrics_for_an_unknown_detector_is_404(client):
    assert client.get("/api/metrics?detector=nope").status_code == 404


def test_cases_can_be_filtered_by_category_and_label(client):
    body = client.get("/api/cases?category=N2&label=no_drift").json()
    assert body["total"] == 18
    assert all(row["category"] == "N2" for row in body["items"])


def test_cases_search_matches_the_id(client):
    body = client.get("/api/cases?q=D8").json()
    assert body["total"] >= 6
    assert all("D8" in row["id"] for row in body["items"])


def test_case_rows_carry_each_detector_verdict(client):
    row = client.get("/api/cases?q=library-D2-01").json()["items"][0]
    assert set(row["verdicts"]) == {"specguard", "keyword", "wholefile"}


def test_case_detail_returns_the_diff_and_the_verdicts(client):
    body = client.get("/api/cases/library-D2-01").json()
    assert "LOAN_PERIOD_DAYS = 14" in body["before_source"]
    assert "LOAN_PERIOD_DAYS = 21" in body["after_source"]
    assert body["changed_lines"]
    assert body["rules"][0]["id"] == "R12"
    assert body["verdicts"]["specguard"]


def test_case_detail_marks_the_gold_chunk(client):
    body = client.get("/api/cases/library-D7-01").json()
    hits = body["retrieved"]["R09"]
    assert any(hit["is_gold"] for hit in hits)
    assert all(0.0 <= hit["score"] <= 1.0 for hit in hits)


def test_unknown_case_is_404(client):
    assert client.get("/api/cases/nope").status_code == 404


def test_projects_expose_their_rules(client):
    body = client.get("/api/projects").json()
    assert {p["name"] for p in body} == {"library", "wallet", "ratelimiter"}
    library = next(p for p in body if p["name"] == "library")
    assert library["rule_count"] == 14
    assert library["rules"][0]["id"] == "R01"
    assert "# Library Specification" in library["spec"]


def test_reload_rereads_from_disk(client):
    body = client.post("/api/reload").json()
    assert body["cases"] >= 60
    assert "specguard" in body["detectors"]


def test_check_streams_a_verdict_per_rule_then_a_summary(client):
    with client.stream("POST", "/api/check", json={"project": "library"}) as response:
        assert response.status_code == 200
        events = [line for line in response.iter_lines() if line.startswith("event:")]

    assert events[0] == "event: start"
    assert events.count("event: verdict") == 14
    assert events[-1] == "event: summary"


def test_check_on_a_drifted_case_reports_drift(client):
    import json as _json

    with client.stream(
        "POST", "/api/check", json={"project": "library", "case_id": "library-D2-01"}
    ) as response:
        payloads = [
            _json.loads(line.removeprefix("data: "))
            for line in response.iter_lines()
            if line.startswith("data: ")
        ]

    assert payloads[-1]["status"] == "DRIFT"
    assert any(p.get("rule_id") == "R12" and p.get("verdict") == "DRIFT" for p in payloads)


def test_check_on_an_unknown_project_is_404(client):
    assert client.post("/api/check", json={"project": "nope"}).status_code == 404

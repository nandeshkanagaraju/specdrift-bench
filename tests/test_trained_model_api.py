import pytest
from fastapi.testclient import TestClient

from specdrift.api.app import create_app


@pytest.fixture()
def client(settings):
    settings.api_rate_limit_per_min = 0
    settings.demo_pacing = False
    return TestClient(create_app(settings))


def test_the_committed_results_are_served(client):
    body = client.get("/api/trained-model").json()
    assert body["verdict"]["headline"] == "H1 is not supported"
    assert [a["name"] for a in body["benchmark_arms"]] == [
        "gpt-4o-mini-zero-shot",
        "keyword-baseline",
        "qwen2.5-coder-1.5b-untuned",
        "qwen2.5-coder-1.5b-sft-r0",
    ]


def test_every_arm_mean_lies_inside_its_interval(client):
    for arm in client.get("/api/trained-model").json()["benchmark_arms"]:
        for key in ("recall", "precision", "false_alarm_rate"):
            low, high = arm[key]["ci95"]
            assert low <= arm[key]["mean"] <= high, (arm["name"], key)


def test_the_headline_matches_the_numbers_it_summarises(client):
    arms = {a["name"]: a for a in client.get("/api/trained-model").json()["benchmark_arms"]}
    tuned, zero_shot = arms["qwen2.5-coder-1.5b-sft-r0"], arms["gpt-4o-mini-zero-shot"]
    # "removes the false alarms but stops detecting drift": both halves must hold, or the headline is wrong
    assert tuned["false_alarm_rate"]["mean"] < zero_shot["false_alarm_rate"]["mean"]
    assert tuned["recall"]["mean"] < zero_shot["recall"]["mean"]


def test_exactly_one_training_run_passed_the_gate_and_run_three_is_the_one_scored(client):
    runs = client.get("/api/trained-model").json()["gate_runs"]
    assert [r["gate"] for r in runs].count("GO") == 1
    scored = [r for r in runs if "scored on the benchmark" in r["note"]]
    assert [r["run"] for r in scored] == [3]


def test_a_missing_results_file_is_a_404(client, settings, tmp_path):
    settings.trained_model_path = tmp_path / "absent.json"
    response = TestClient(create_app(settings)).get("/api/trained-model")
    assert response.status_code == 404


def test_a_broken_results_file_is_reported_not_swallowed(client, settings, tmp_path):
    broken = tmp_path / "broken.json"
    broken.write_text("{not json", encoding="utf-8")
    settings.trained_model_path = broken
    response = TestClient(create_app(settings)).get("/api/trained-model")
    assert response.status_code == 500
    assert "not valid JSON" in response.json()["detail"]

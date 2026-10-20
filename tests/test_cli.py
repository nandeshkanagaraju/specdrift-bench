import json

import pytest
from typer.testing import CliRunner

from specdrift import cli

runner = CliRunner()


@pytest.fixture()
def built(settings, monkeypatch):
    """The CLI wired to scratch directories, with a handful of ratelimiter cases built."""
    monkeypatch.setattr(cli, "get_settings", lambda: settings)
    result = runner.invoke(cli.app, ["build", "--case", "ratelimiter-D1"])
    assert result.exit_code == 0, result.output
    return settings


def test_commands_fail_cleanly_before_anything_is_built(settings, monkeypatch):
    monkeypatch.setattr(cli, "get_settings", lambda: settings)
    for args in (["run", "--detector", "keyword"], ["score"], ["report"], ["stability"],
                 ["retrieval-eval"], ["oracles"]):
        result = runner.invoke(cli.app, args)
        assert result.exit_code == 1, (args, result.output)
        assert "build" in result.output


def test_build_writes_the_manifest(built):
    assert built.built_cases_path.exists()
    assert "case" in built.built_cases_path.read_text() or built.built_cases_path.stat().st_size > 0


def test_run_score_stability_and_report_chain(built):
    ran = runner.invoke(cli.app, ["run", "--detector", "keyword", "--repeat", "2"])
    assert ran.exit_code == 0, ran.output
    assert (built.results_dir / "keyword" / "verdicts.jsonl").exists()
    assert (built.results_dir / "keyword" / "verdicts.run2.jsonl").exists()

    scored = runner.invoke(cli.app, ["score", "--detector", "keyword"])
    assert scored.exit_code == 0 and "strict" in scored.output
    assert json.loads((built.results_dir / "keyword" / "metrics.json").read_text())["detector"] == "keyword"

    stable = runner.invoke(cli.app, ["stability", "--detector", "keyword", "--boot", "50"])
    assert stable.exit_code == 0 and "95% CI" in stable.output
    assert (built.results_dir / "keyword" / "stability.json").exists()

    rendered = runner.invoke(cli.app, ["report"])
    assert rendered.exit_code == 0, rendered.output
    assert (built.results_dir / "report.html").exists()
    assert (built.results_dir / "report.md").exists()


def test_run_warns_when_the_fake_model_is_answering(built):
    result = runner.invoke(cli.app, ["run", "--detector", "specguard", "--limit", "1"])
    assert result.exit_code == 0, result.output
    assert "fake" in result.output.lower()


def test_retrieval_eval_prints_recall_and_writes_json(built):
    result = runner.invoke(cli.app, ["retrieval-eval"])
    assert result.exit_code == 0, result.output
    assert json.loads((built.results_dir / "retrieval.json").read_text())


def test_score_with_no_verdicts_says_how_to_get_some(built):
    result = runner.invoke(cli.app, ["score", "--detector", "wholefile"])
    assert "no verdicts for wholefile" in result.output

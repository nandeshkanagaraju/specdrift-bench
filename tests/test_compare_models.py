import importlib.util
import json

import pytest

from specdrift.bench.schema import CaseResult, Verdict
from specdrift.config import REPO_ROOT, Settings
from specdrift.runner import verdicts_path

SCRIPT = REPO_ROOT / "scripts" / "compare_models.py"
spec = importlib.util.spec_from_file_location("compare_models", SCRIPT)
cm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cm)

N_BOOT = 40
EXAMPLE = REPO_ROOT / "scripts" / "compare_arms.example.json"


def write_arms(tmp_path, arms, baseline=None):
    path = tmp_path / "arms.json"
    path.write_text(json.dumps({"baseline": baseline or arms[0]["name"], "arms": arms}))
    return path


def arm(name, env=None, **extra):
    return {"name": name, "env": env or {"LLM_PROVIDER": "fake"}, **extra}


# --- arm validation ---------------------------------------------------------------------------

def test_the_shipped_example_file_is_valid_and_its_unfinished_arms_are_not_run():
    arms, baseline = cm.load_arms(EXAMPLE)
    assert baseline == "gpt-4o-mini-zero-shot" and len(arms) == 5
    steps = {s["arm"]: s for s in cm.plan(arms, REPO_ROOT / "results_compare", runs=3)}
    assert "placeholder" in steps["stronger-zero-shot"]["skip"]
    assert "LLM_ADAPTER" in steps["qwen2.5-coder-1.5b-sft"]["skip"]
    assert "skip" not in steps["gpt-4o-mini-zero-shot"] and "skip" not in steps["qwen2.5-coder-1.5b-untuned"]


@pytest.mark.parametrize("key", ["LLM_API_KEY", "OPENAI_API_KEY", "HF_TOKEN", "RESULTS_DIR", "ANTHROPIC_API_KEY"])
def test_an_arm_cannot_carry_a_secret_or_redirect_results(tmp_path, key):
    path = write_arms(tmp_path, [arm("a", {key: "x"})])
    with pytest.raises(cm.ArmError, match=key):
        cm.load_arms(path)


def test_bad_names_duplicates_detectors_and_baselines_are_refused(tmp_path):
    with pytest.raises(cm.ArmError, match="name"):
        cm.load_arms(write_arms(tmp_path, [arm("../escape")]))
    with pytest.raises(cm.ArmError, match="duplicate"):
        cm.load_arms(write_arms(tmp_path, [arm("a"), arm("a")]))
    with pytest.raises(cm.ArmError, match="detector"):
        cm.load_arms(write_arms(tmp_path, [arm("a", detector="oracle")]))
    with pytest.raises(cm.ArmError, match="baseline"):
        cm.load_arms(write_arms(tmp_path, [arm("a")], baseline="missing"))


# --- the plan ---------------------------------------------------------------------------------

def test_a_specguard_arm_runs_the_86_cases_and_the_examples_other_detectors_only_the_cases(tmp_path):
    arms, _ = cm.load_arms(write_arms(tmp_path, [arm("s"), arm("k", detector="keyword")]))
    steps = {s["arm"]: s for s in cm.plan(arms, tmp_path / "out", runs=3)}

    assert [c[3:] for c in steps["s"]["commands"]] == [["run", "--detector", "specguard", "--repeat", "3"],
                                                       ["heldout", "--repeat", "3"]]
    assert [c[3:] for c in steps["k"]["commands"]] == [["run", "--detector", "keyword", "--repeat", "3"]]
    assert [c[3:] for c in cm.plan(arms, tmp_path, 3, heldout=False)[0]["commands"]] == [
        ["run", "--detector", "specguard", "--repeat", "3"]]


def test_results_go_to_a_directory_per_arm_so_arms_never_overwrite_each_other(tmp_path):
    arms, _ = cm.load_arms(write_arms(tmp_path, [arm("one"), arm("two", results_dir="results")]))
    out = tmp_path / "out"
    assert cm.arm_results_dir(arms[0], out) == out / "one"
    assert cm.env_for(arms[0], out)["RESULTS_DIR"] == str(out / "one")
    assert cm.arm_results_dir(arms[1], out) == REPO_ROOT / "results"
    assert "reuses existing" in cm.plan(arms, out, 3)[1]["skip"]


def test_the_environment_carries_only_the_arms_overrides_on_top_of_the_parents(tmp_path, monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "sentinel-not-a-real-key")
    arms, _ = cm.load_arms(write_arms(tmp_path, [arm("a", {"LLM_MODEL": "m1"})]))
    env = cm.env_for(arms[0], tmp_path)
    assert env["LLM_MODEL"] == "m1" and env["LLM_API_KEY"] == "sentinel-not-a-real-key"     # inherited, not stored
    printed = json.dumps(cm.plan(arms, tmp_path, 3))
    assert "sentinel-not-a-real-key" not in printed


def test_run_prints_a_plan_and_executes_nothing_without_the_flag(tmp_path, capsys, monkeypatch):
    called = []
    monkeypatch.setattr(cm.subprocess, "run", lambda *a, **k: called.append(a))
    path = write_arms(tmp_path, [arm("a", {"LLM_PROVIDER": "fake"})])

    assert cm.main(["run", "--arms", str(path), "--out", str(tmp_path / "o")]) == 0

    assert called == [] and "plan only" in capsys.readouterr().out


def test_execute_runs_each_command_with_that_arms_environment_and_stops_at_the_first_failure(tmp_path, monkeypatch):
    seen = []

    class Done:
        def __init__(self, code):
            self.returncode = code

    def fake_run(command, cwd, env):
        seen.append((command[3], env["RESULTS_DIR"], env["LLM_MODEL"]))
        return Done(3 if command[3] == "heldout" else 0)

    monkeypatch.setattr(cm.subprocess, "run", fake_run)
    monkeypatch.setattr(cm, "REPO_ROOT", tmp_path)
    (tmp_path / "cases").mkdir()
    (tmp_path / "cases" / "built.jsonl").write_text("")
    path = write_arms(tmp_path, [arm("a", {"LLM_MODEL": "ma"}), arm("b", {"LLM_MODEL": "mb"})])

    code = cm.main(["run", "--arms", str(path), "--out", str(tmp_path / "o"), "--execute"])

    assert code == 3                                    # heldout of arm a failed, so b never started
    assert seen == [("run", str(tmp_path / "o" / "a"), "ma"), ("heldout", str(tmp_path / "o" / "a"), "ma")]


def test_execute_refuses_when_the_cases_are_not_built(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cm, "REPO_ROOT", tmp_path)
    path = write_arms(tmp_path, [arm("a")])
    assert cm.main(["run", "--arms", str(path), "--out", str(tmp_path / "o"), "--execute"]) == 1
    assert "specdrift build" in capsys.readouterr().err


def test_an_arm_can_fix_its_own_run_count_and_the_example_does_so_for_local_models(tmp_path):
    arms, _ = cm.load_arms(write_arms(tmp_path, [arm("local", runs=1), arm("api")]))
    steps = {s["arm"]: s for s in cm.plan(arms, tmp_path, runs=3)}
    assert steps["local"]["commands"][0][-2:] == ["--repeat", "1"] and steps["local"]["commands"][1][-2:] == ["--repeat", "1"]
    assert steps["api"]["commands"][0][-2:] == ["--repeat", "3"]

    shipped, _ = cm.load_arms(EXAMPLE)
    assert {a["name"]: a["runs"] for a in shipped if a["env"].get("LLM_PROVIDER") == "huggingface"} == {
        "qwen2.5-coder-1.5b-untuned": 1, "qwen2.5-coder-1.5b-sft": 1}


@pytest.mark.parametrize("bad", [0, -1, "3", True, 1.5])
def test_a_bad_run_count_is_refused(tmp_path, bad):
    with pytest.raises(cm.ArmError, match="runs must be"):
        cm.load_arms(write_arms(tmp_path, [arm("a", runs=bad)]))


# --- the report -------------------------------------------------------------------------------

CASES = [
    CaseResult(case_id="c1", project="p", category="D1", label="drift", target_rules=["R01"]),
    CaseResult(case_id="c2", project="p", category="D2", label="drift", target_rules=["R02"]),
    CaseResult(case_id="c3", project="p", category="N1", label="no_drift"),
    CaseResult(case_id="c4", project="p", category="N1", label="no_drift"),
]


def vs(case_id, rule, verdict, confidence, run=1):
    return Verdict(case_id=case_id, rule_id=rule, detector="specguard", verdict=verdict,
                   confidence=confidence, run=run)


GOOD = [vs("c1", "R01", "DRIFT", 0.9), vs("c2", "R02", "DRIFT", 0.8),
        vs("c3", "R01", "COMPLIANT", 0.9), vs("c4", "R01", "COMPLIANT", 0.9)]
NOISY = [vs("c1", "R01", "DRIFT", 0.9), vs("c2", "R02", "COMPLIANT", 0.6),
         vs("c3", "R01", "DRIFT", 0.9), vs("c4", "R01", "DRIFT", 0.8)]
EXPECTED = {"p": {"R01"}}


def comparison(fake_baseline=False):
    data = {
        "base": {"detector": "specguard", "fake": fake_baseline, "sets": {1: NOISY, 2: NOISY},
                 "heldout": {1: [vs("p", "R01", "DRIFT", 0.9)], 2: [vs("p", "R01", "DRIFT", 0.9)]}},
        "tuned": {"detector": "specguard", "fake": False, "sets": {1: GOOD, 2: GOOD}, "heldout": {}},
    }
    return cm.build_comparison(CASES, EXPECTED, data, "base", n_boot=N_BOOT)


def test_report_pairs_every_other_arm_with_the_baseline_and_reads_the_interval_plainly():
    result = comparison()
    assert list(result["paired"]) == ["tuned"]
    fa = result["paired"]["tuned"]["false_alarm_rate"]
    assert fa["difference"] == -1.0 and result["paired"]["tuned"]["recall"]["difference"] == 0.5
    assert cm.paired_reading({"ci95": [-1.0, -0.5]}) == "lower (interval excludes 0)"
    assert cm.paired_reading({"ci95": [0.1, 0.5]}) == "higher (interval excludes 0)"
    assert cm.paired_reading({"ci95": [-0.2, 0.3]}) == "no detectable difference (interval includes 0)"
    assert cm.paired_reading({"ci95": None}) == "undefined"


def test_markdown_has_every_table_the_task_asks_for():
    text = cm.render_markdown(comparison())
    for needle in ("## 86 frozen cases", "strict precision", "false-alarm rate", "UNCERTAIN rate", "ECE",
                   "## Paired difference against `base`", "## Per category", "D1 (recall)", "N1 (false_alarm_rate)",
                   "## Abstention: coverage against accuracy", "| threshold | coverage | accuracy",
                   "## Unseen projects (test-2), per rule", "Read this before quoting a number",
                   "not a significance test of H1"):
        assert needle in text, needle
    assert "[" in text and "(FAKE" not in text


def test_an_arm_answered_by_the_offline_stand_in_is_labelled_so_it_cannot_pass_as_a_model():
    text = cm.render_markdown(comparison(fake_baseline=True))
    assert "base (FAKE offline stand-in)" in text and "tuned (FAKE" not in text


def test_a_missing_baseline_or_few_runs_is_said_not_hidden():
    data = {"tuned": {"detector": "specguard", "fake": False, "sets": {1: GOOD}, "heldout": {}}}
    result = cm.build_comparison(CASES, EXPECTED, data, "base", n_boot=N_BOOT)
    assert result["paired"] == {}
    assert any("no results, so no paired" in n for n in result["notes"])
    assert any("1 run(s)" in n for n in result["notes"])


def test_a_single_run_by_design_is_explained_and_other_thin_arms_are_still_flagged():
    data = {"local": {"detector": "specguard", "fake": False, "sets": {1: GOOD}, "heldout": {}, "planned_runs": 1},
            "api": {"detector": "specguard", "fake": False, "sets": {1: GOOD}, "heldout": {}, "planned_runs": None}}
    notes = cm.build_comparison(CASES, EXPECTED, data, "local", n_boot=N_BOOT)["notes"]
    assert any("local: 1 run by design" in n and "deterministic" in n for n in notes)
    assert any("api: 1 run(s)" in n for n in notes) and not any("local: 1 run(s)" in n for n in notes)


def test_load_arm_data_reads_every_stored_run_and_spots_the_fake_provider(tmp_path):
    arms, _ = cm.load_arms(write_arms(tmp_path, [arm("a")]))
    out = tmp_path / "out"
    assert cm.load_arm_data(arms[0], out) is None                       # not run yet

    settings = Settings(results_dir=out / "a")
    for run, rows in ((1, GOOD), (2, NOISY)):
        path = verdicts_path(settings, "specguard", run)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("".join(r.model_dump_json() + "\n" for r in rows))
    (settings.detector_dir("specguard") / "run.json").write_text(json.dumps({"model": "fake"}))

    loaded = cm.load_arm_data(arms[0], out)
    assert sorted(loaded["sets"]) == [1, 2] and loaded["fake"] is True and loaded["heldout"] == {}

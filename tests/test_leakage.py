import json

import pytest
from typer.testing import CliRunner

from specdrift import cli
from specdrift.bench.builder import load_all_manifests, patched_sources
from specdrift.bench.schema import Chunk, Rule
from specdrift.code.chunker import chunk_source, chunk_workspace
from specdrift.config import REPO_ROOT
from specdrift.data import leakage
from specdrift.data.leakage import (
    ManifestMismatch,
    collect_test_material,
    edit_distance_within,
    freeze,
    rules_are_near,
    run_checks,
    verify_frozen,
)
from specdrift.data.schema import Provenance, Target, TrainingExample

runner = CliRunner()
EXAMPLES = REPO_ROOT / "examples"


@pytest.fixture(scope="module")
def material():
    return collect_test_material(REPO_ROOT / "cases", REPO_ROOT / "projects", EXAMPLES)


def long_chunk(root, min_tokens=80):
    for chunk in chunk_workspace(root, "src"):
        if len(leakage.code_tokens(chunk.source)) >= min_tokens:
            return chunk
    raise AssertionError("no long chunk found")


def example(source="def f(x):\n    return x + 1\n", rule="Return one more than the input value.", **over):
    base = dict(
        example_id="t-1", source="synth", split="train", project_id="synth-clean-1",
        rule=Rule(id="R01", text=rule),
        chunks=[Chunk(id="a.py::f", file="a.py", qualname="f", start_line=1, end_line=2, source=source)],
        label="COMPLIANT", category="N1", target=Target(verdict="COMPLIANT"),
        provenance=Provenance(label_method="execution", generator="test"),
    )
    base.update(over)
    return TrainingExample(**base)


def kinds(report):
    return {f.check for f in report.findings}


# ---------------------------------------------------------------- what the frozen set holds


def test_the_frozen_set_covers_every_case_and_all_test_projects(material):
    manifest = material.manifest()
    assert len(manifest["cases"]) == 86
    assert {"library", "wallet", "ratelimiter"} <= set(manifest["projects"])
    assert {"examples/auth-gateway", "examples/clinic-desk", "examples/shop-checkout",
            "examples/task-queue"} <= set(manifest["projects"])
    assert manifest["fingerprint"] == material.manifest()["fingerprint"]


def test_drifted_code_is_part_of_the_test_set_not_only_the_original(material):
    assert any(chunk_id.startswith("library-D1-01/") for chunk_id in material.chunk_hashes.values())


# ---------------------------------------------------------------- a clean example passes


def test_an_unrelated_example_is_clean(material):
    report = run_checks([example()], material)
    assert report.ok, report.findings


# ---------------------------------------------------------------- planted leaks are caught


def test_a_test_chunk_with_new_comments_and_layout_is_still_caught(material):
    chunk = long_chunk(REPO_ROOT / "projects" / "library")
    disguised = "# a harmless new comment\n" + "\n".join(
        line.replace("    ", "  ") + "  # tweaked" if line.strip() else line for line in chunk.source.splitlines()
    ).replace("\n\n", "\n\n\n")
    report = run_checks([example(source=disguised)], material)
    assert "chunks" in kinds(report)


def test_a_chunk_from_an_unseen_example_project_is_caught(material):
    chunk = long_chunk(EXAMPLES / "shop-checkout", min_tokens=40)
    report = run_checks([example(source=chunk.source)], material)
    assert "chunks" in kinds(report)


def test_a_chunk_the_drift_patch_produced_is_caught(material):
    # the *drifted* code is test data too; a model must not learn it as a COMPLIANT example
    case = next(c for c in load_all_manifests(REPO_ROOT / "cases") if c.id == "library-D1-01")
    before, after = patched_sources(case, REPO_ROOT / "projects")
    originals = {c.source for c in chunk_source(before, case.file)}
    drifted = next(c for c in chunk_source(after, case.file) if c.source not in originals)

    assert "chunks" in kinds(run_checks([example(source=drifted.source)], material))


def test_a_lightly_reworded_test_rule_is_caught(material):
    reworded = "A member MUST be at least 19 years old at registration."   # R01 with 18 -> 19
    assert "rules" in kinds(run_checks([example(rule=reworded)], material))
    shouted = "A MEMBER must be AT LEAST 18 years old at registration."
    assert "rules" in kinds(run_checks([example(rule=shouted)], material))


def test_an_unrelated_rule_is_not_flagged(material):
    assert "rules" not in kinds(run_checks([example(rule="Parse the config file and return a dict.")], material))


def test_a_host_project_id_is_caught(material):
    assert "projects" in kinds(run_checks([example(project_id="library")], material))
    assert "projects" in kinds(run_checks([example(project_id="examples/auth-gateway")], material))


def test_one_project_in_two_splits_is_caught(material):
    pair = [example(example_id="a", split="train"), example(example_id="b", split="val")]
    report = run_checks(pair, material)
    assert "projects" in kinds(report)
    assert "more than one split" in report.findings[0].detail


def test_a_test_cases_find_replace_pair_is_caught(material):
    notes = {"inject_find": "        if age < MINIMUM_AGE:", "inject_replace": "        if age <= MINIMUM_AGE:"}
    leaked = example(provenance=Provenance(label_method="execution", generator="t", notes=notes))
    assert "injections" in kinds(run_checks([leaked], material))
    other = {"inject_find": "x = 1", "inject_replace": "x = 2"}
    clean = example(provenance=Provenance(label_method="execution", generator="t", notes=other))
    assert "injections" not in kinds(run_checks([clean], material))


def test_examples_with_no_injection_record_are_reported_not_silently_passed(material):
    report = run_checks([example()], material)
    assert any("record no injection" in note for note in report.notes)


def test_a_near_copy_is_caught_by_ngrams_even_when_no_chunk_matches_exactly(material):
    chunk = long_chunk(REPO_ROOT / "projects" / "wallet")
    lines = chunk.source.splitlines()
    mid = len(lines) // 2
    lines[mid] = lines[mid] + "\n    marker = 0  # one extra statement"
    near_copy = "\n".join(lines)

    report = run_checks([example(source=near_copy)], material, ngram_fail=0.5)
    assert "chunks" not in kinds(report)          # not an exact copy ...
    assert "ngrams" in kinds(report)              # ... but mostly the same tokens
    assert report.ngram["max"] >= 0.5


def test_ngram_overlap_is_zero_for_unrelated_code(material):
    assert run_checks([example()], material).ngram["max"] == 0.0


# ---------------------------------------------------------------- the frozen manifest


def test_freeze_is_idempotent_and_refuses_a_changed_test_set(settings, tmp_path):
    manifest = tmp_path / "m.json"
    material = collect_test_material(settings.cases_dir, settings.projects_dir, None)
    first = freeze(material, manifest)
    assert freeze(material, manifest) == first

    victim = next(settings.cases_dir.glob("library.yaml"))
    victim.write_text(victim.read_text().replace("age <= MINIMUM_AGE", "age <= MINIMUM_AGE + 0", 1))
    moved = collect_test_material(settings.cases_dir, settings.projects_dir, None)

    with pytest.raises(ManifestMismatch):
        freeze(moved, manifest)
    with pytest.raises(ManifestMismatch):
        verify_frozen(moved, manifest)
    assert freeze(moved, manifest, force=True)["fingerprint"] != first["fingerprint"]


def test_check_without_a_manifest_fails_cleanly(material, tmp_path):
    with pytest.raises(ManifestMismatch, match="data-freeze"):
        verify_frozen(material, tmp_path / "missing.json")


# ---------------------------------------------------------------- small pieces


@pytest.mark.parametrize(
    ("a", "b", "limit", "expected"),
    [("kitten", "sitting", 3, 3), ("kitten", "sitting", 2, None), ("same", "same", 0, 0), ("a", "abcdef", 2, None)],
)
def test_banded_edit_distance(a, b, limit, expected):
    assert edit_distance_within(a, b, limit) == expected


def test_rule_nearness_threshold():
    base = "the late fee must be 0.50 per day late, capped at 20.00"
    assert rules_are_near(base, base.replace("0.50", "0.75"))
    assert not rules_are_near(base, "borrowing must raise an error when the book is unavailable")


# ---------------------------------------------------------------- the command line


@pytest.fixture()
def wired(settings, tmp_path, monkeypatch):
    manifest = tmp_path / "data" / "test_manifest.json"
    monkeypatch.setattr(cli, "get_settings", lambda: settings)
    monkeypatch.setattr(
        cli, "_leak_paths", lambda s: (s.cases_dir, s.projects_dir, EXAMPLES, manifest)
    )
    return manifest


def test_cli_freeze_then_check_clean_then_check_dirty(wired, tmp_path):
    assert runner.invoke(cli.app, ["data-freeze"]).exit_code == 0
    assert wired.exists()

    clean = tmp_path / "clean.jsonl"
    clean.write_text(example().model_dump_json() + "\n")
    ok = runner.invoke(cli.app, ["data-check", str(clean)])
    assert ok.exit_code == 0, ok.output
    assert "RESULT: clean" in ok.output

    dirty = tmp_path / "dirty.jsonl"
    dirty.write_text(example(project_id="library").model_dump_json() + "\n")
    bad = runner.invoke(cli.app, ["data-check", str(dirty), "--report", str(tmp_path / "r.json")])
    assert bad.exit_code == 1
    assert "do not train" in bad.output
    assert json.loads((tmp_path / "r.json").read_text())["ok"] is False


def test_cli_check_refuses_when_the_test_set_moved(wired, settings, tmp_path):
    assert runner.invoke(cli.app, ["data-freeze"]).exit_code == 0
    victim = settings.cases_dir / "wallet.yaml"
    text = victim.read_text()
    assert "category: D1" in text
    victim.write_text(text.replace("category: D1", "category: D2", 1))

    clean = tmp_path / "clean.jsonl"
    clean.write_text(example().model_dump_json() + "\n")
    result = runner.invoke(cli.app, ["data-check", str(clean)])
    assert result.exit_code == 1
    assert "cannot check" in result.output
    assert "changed after it was frozen" in result.output

import pytest

from specdrift.bench.builder import PatchError, apply_patch, build_case, load_all_manifests
from specdrift.bench.schema import CaseSpec


def test_applies_a_single_occurrence():
    assert apply_patch("a = 1\nb = 2\n", "b = 2", "b = 3") == "a = 1\nb = 3\n"


def test_missing_find_string_is_an_error():
    with pytest.raises(PatchError, match="does not occur"):
        apply_patch("a = 1", "nope", "x")


def test_ambiguous_find_string_is_an_error():
    with pytest.raises(PatchError, match="occurs 2 times"):
        apply_patch("x = 1\nx = 1\n", "x = 1", "y = 1")


def test_empty_find_is_the_unchanged_control():
    assert apply_patch("a = 1", "", "") == "a = 1"


def test_patch_written_as_lines_keeps_indentation():
    case = CaseSpec(
        id="t", project="p", category="D5", label="drift",
        find=["        first()", "", "        second()"],
        replace=["        second()", "", "        first()"],
    )
    assert case.find == "        first()\n\n        second()"


def test_build_copies_the_project_and_patches_it(settings, tmp_path):
    case = CaseSpec(
        id="t-1", project="library", category="D2", label="drift",
        file="src/library/service.py",
        find="LOAN_PERIOD_DAYS = 14     # R12",
        replace="LOAN_PERIOD_DAYS = 21     # R12",
    )
    workspace = build_case(case, settings.projects_dir, settings.work_dir)
    patched = (workspace / case.file).read_text()

    assert "LOAN_PERIOD_DAYS = 21" in patched
    assert (workspace / "spec.md").exists()
    assert not (workspace / "__pycache__").exists()


def test_build_leaves_the_host_project_untouched(settings):
    case = CaseSpec(
        id="t-2", project="library", category="D2", label="drift",
        file="src/library/service.py",
        find="LOAN_PERIOD_DAYS = 14     # R12",
        replace="LOAN_PERIOD_DAYS = 99     # R12",
    )
    build_case(case, settings.projects_dir, settings.work_dir)
    original = (settings.projects_dir / "library" / case.file).read_text()
    assert "LOAN_PERIOD_DAYS = 14" in original


def test_every_manifest_case_is_well_formed(settings):
    cases = load_all_manifests(settings.cases_dir)
    assert len(cases) >= 60
    assert len({case.id for case in cases}) == len(cases)

    for case in cases:
        if case.category.startswith("D") and case.category != "D8":
            assert case.target_rules, f"{case.id} names no target rule"
        if case.find:
            assert case.file, f"{case.id} patches nothing"

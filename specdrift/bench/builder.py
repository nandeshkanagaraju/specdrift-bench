"""Materialise a case: copy its host project, then apply the case's patch."""

from __future__ import annotations

import shutil
from pathlib import Path

import yaml

from specdrift.bench.schema import CaseSpec

IGNORED = shutil.ignore_patterns(
    "__pycache__", "*.pyc", ".pytest_cache", ".venv", ".git", ".DS_Store"
)


class PatchError(ValueError):
    """The patch could not be applied exactly once, so the case is unusable."""


def load_manifest(path: str | Path) -> list[CaseSpec]:
    """Read one cases/<project>.yaml into CaseSpec objects."""
    path = Path(path)
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or []
    if not isinstance(raw, list):
        raise ValueError(f"{path} must hold a list of cases")
    return [CaseSpec(**entry) for entry in raw]


def load_all_manifests(cases_dir: str | Path) -> list[CaseSpec]:
    cases_dir = Path(cases_dir)
    cases: list[CaseSpec] = []
    seen: set[str] = set()

    for manifest in sorted(cases_dir.glob("*.yaml")):
        for case in load_manifest(manifest):
            if case.id in seen:
                raise ValueError(f"duplicate case id {case.id}")
            seen.add(case.id)
            cases.append(case)

    return cases


def apply_patch(source: str, find: str, replace: str) -> str:
    """Replace the single occurrence of ``find``. Anything else is an error."""
    if not find:
        return source   # N1: the unchanged control.

    occurrences = source.count(find)
    if occurrences == 0:
        raise PatchError("find string does not occur in the file")
    if occurrences > 1:
        raise PatchError(f"find string occurs {occurrences} times, it must occur once")

    return source.replace(find, replace, 1)


def build_case(case: CaseSpec, projects_dir: str | Path, work_dir: str | Path) -> Path:
    """Copy the host project into work/<case_id>/ and patch it. Returns the workspace."""
    projects_dir, work_dir = Path(projects_dir), Path(work_dir)
    project_dir = projects_dir / case.project
    if not project_dir.exists():
        raise PatchError(f"unknown project {case.project}")

    workspace = work_dir / case.id
    if workspace.exists():
        shutil.rmtree(workspace)
    workspace.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(project_dir, workspace, ignore=IGNORED)

    if case.find:
        target = workspace / case.file
        if not target.exists():
            raise PatchError(f"{case.file} does not exist in {case.project}")
        original = target.read_text(encoding="utf-8")
        target.write_text(apply_patch(original, case.find, case.replace), encoding="utf-8")

    return workspace


def patched_sources(case: CaseSpec, projects_dir: str | Path) -> tuple[str, str]:
    """Return (before, after) text of the file a case touches, without touching disk."""
    project_dir = Path(projects_dir) / case.project
    if not case.file:
        return "", ""

    target = project_dir / case.file
    if not target.exists():
        return "", ""

    before = target.read_text(encoding="utf-8")
    try:
        after = apply_patch(before, case.find, case.replace)
    except PatchError:
        after = before
    return before, after

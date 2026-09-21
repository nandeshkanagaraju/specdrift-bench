"""Shared fixtures. No test in this suite is ever allowed to call a real model."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from specdrift.config import REPO_ROOT, Settings


@pytest.fixture()
def settings(tmp_path: Path) -> Settings:
    """Real projects and manifests, but scratch directories for anything written.

    The manifests are *copied* into the scratch directory rather than read in place:
    `build_all` writes built.jsonl next to them, and pointing that at the repository
    would leave cases/built.jsonl full of pytest temp paths after every test run.
    """
    cases_dir = tmp_path / "cases"
    cases_dir.mkdir(parents=True, exist_ok=True)
    for manifest in sorted((REPO_ROOT / "cases").glob("*.yaml")):
        shutil.copy2(manifest, cases_dir / manifest.name)

    return Settings(
        llm_provider="fake",
        embed_backend="local",
        top_k=3,
        projects_dir=REPO_ROOT / "projects",
        cases_dir=cases_dir,
        results_dir=tmp_path / "results",
        cache_dir=tmp_path / "cache",
        work_dir=tmp_path / "work",
    )


@pytest.fixture()
def library_dir() -> Path:
    return REPO_ROOT / "projects" / "library"


SAMPLE_SOURCE = '''"""Module docstring."""

LIMIT = 3


class Service:
    """A class."""

    MAX = 10

    def borrow(self, n):
        # R01 - the check
        if n >= LIMIT:
            raise ValueError("too many")
        return n


def helper(x):
    return x * 2
'''

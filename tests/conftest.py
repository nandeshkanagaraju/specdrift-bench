"""Shared fixtures. No test in this suite is ever allowed to call a real model."""

from __future__ import annotations

from pathlib import Path

import pytest

from specdrift.config import REPO_ROOT, Settings


@pytest.fixture()
def settings(tmp_path: Path) -> Settings:
    """Real projects and manifests, but scratch directories for anything written."""
    return Settings(
        llm_provider="fake",
        embed_backend="local",
        top_k=3,
        projects_dir=REPO_ROOT / "projects",
        cases_dir=REPO_ROOT / "cases",
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

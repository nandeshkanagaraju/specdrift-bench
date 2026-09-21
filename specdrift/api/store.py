"""Everything the API serves, loaded from disk once and held in memory.

The API never computes a metric. It reads what the CLI already wrote, so a number on
the dashboard and a number in report.html can never disagree.
"""

from __future__ import annotations

import json
from difflib import SequenceMatcher
from pathlib import Path

from specdrift.bench.builder import load_all_manifests, patched_sources
from specdrift.bench.pipeline import load_built
from specdrift.bench.schema import CATEGORY_NAMES, CaseResult, CaseSpec, Verdict
from specdrift.config import Settings
from specdrift.registry import DETECTOR_NAMES
from specdrift.runner import load_verdicts
from specdrift.spec.parser import load_project_rules


class Store:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.reload()

    # ------------------------------------------------------------------ load

    def reload(self) -> None:
        self.cases: list[CaseResult] = load_built(self.settings)
        self.cases_by_id: dict[str, CaseResult] = {c.case_id: c for c in self.cases}

        try:
            self.specs: dict[str, CaseSpec] = {
                spec.id: spec for spec in load_all_manifests(self.settings.cases_dir)
            }
        except (ValueError, OSError):
            self.specs = {}

        self.verdicts: dict[str, list[Verdict]] = {}
        self.metrics: dict[str, dict] = {}
        self.runs: dict[str, dict] = {}

        for name in DETECTOR_NAMES:
            verdicts = load_verdicts(self.settings, name)
            if verdicts:
                self.verdicts[name] = verdicts

            metrics_path = self.settings.detector_dir(name) / "metrics.json"
            if metrics_path.exists():
                self.metrics[name] = json.loads(metrics_path.read_text(encoding="utf-8"))

            run_path = self.settings.detector_dir(name) / "run.json"
            if run_path.exists():
                self.runs[name] = json.loads(run_path.read_text(encoding="utf-8"))

        self.projects: list[str] = sorted({c.project for c in self.cases if c.project})
        self.rules = {
            project: load_project_rules(self.settings.projects_dir / project)
            for project in self.projects
            if (self.settings.projects_dir / project / "spec.md").exists()
        }

        retrieval_path = self.settings.results_dir / "retrieval.json"
        self.retrieval = (
            json.loads(retrieval_path.read_text(encoding="utf-8"))
            if retrieval_path.exists()
            else None
        )

        # case id -> detector -> verdict for the rules that matter, for the table column
        self._case_verdicts: dict[str, dict[str, str]] = {}
        for name, verdicts in self.verdicts.items():
            for verdict in verdicts:
                slot = self._case_verdicts.setdefault(verdict.case_id, {})
                current = slot.get(name)
                if verdict.verdict == "DRIFT" or current is None:
                    if current != "DRIFT":
                        slot[name] = verdict.verdict

        self._outcomes: dict[str, dict[str, dict]] = {}
        for name, metrics in self.metrics.items():
            for row in metrics.get("outcomes", []):
                self._outcomes.setdefault(row["case_id"], {})[name] = row

    # ------------------------------------------------------------- accessors

    @property
    def detectors(self) -> list[str]:
        return [name for name in DETECTOR_NAMES if name in self.verdicts]

    def case_verdicts(self, case_id: str) -> dict[str, str]:
        return self._case_verdicts.get(case_id, {})

    def outcomes(self, case_id: str) -> dict[str, dict]:
        return self._outcomes.get(case_id, {})

    def verdicts_for(self, case_id: str) -> dict[str, list[Verdict]]:
        grouped: dict[str, list[Verdict]] = {}
        for name, verdicts in self.verdicts.items():
            rows = [v for v in verdicts if v.case_id == case_id]
            if rows:
                grouped[name] = rows
        return grouped

    def sources(self, case_id: str) -> tuple[str, str, list[int]]:
        """Before and after text of the file a case patches, plus the changed lines."""
        spec = self.specs.get(case_id)
        if spec is None or not spec.file:
            return "", "", []

        before, after = patched_sources(spec, self.settings.projects_dir)
        return before, after, changed_lines(before, after)

    def project_case_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for case in self.cases:
            counts[case.project] = counts.get(case.project, 0) + 1
        return counts

    def spec_text(self, project: str) -> str:
        path = self.settings.projects_dir / project / "spec.md"
        return path.read_text(encoding="utf-8") if path.exists() else ""

    def category_name(self, category: str | None) -> str:
        return CATEGORY_NAMES.get(category or "", "")


def changed_lines(before: str, after: str) -> list[int]:
    """1-based line numbers in `after` that differ from `before`."""
    if not before or before == after:
        return []

    old, new = before.splitlines(), after.splitlines()
    changed: list[int] = []
    for tag, _, _, j1, j2 in SequenceMatcher(None, old, new).get_opcodes():
        if tag in {"replace", "insert"}:
            changed.extend(range(j1 + 1, j2 + 1))
    return changed


def workspace_for(settings: Settings, case: CaseResult) -> Path | None:
    if case.workspace and Path(case.workspace).exists():
        return Path(case.workspace)
    candidate = settings.work_dir / case.case_id
    return candidate if candidate.exists() else None

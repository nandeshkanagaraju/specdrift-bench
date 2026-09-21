"""Run one detector over every built case and append verdicts to a JSONL file."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from specdrift.bench.schema import CaseResult, Verdict
from specdrift.config import Settings
from specdrift.registry import build_detector


def verdicts_path(settings: Settings, detector: str) -> Path:
    return settings.detector_dir(detector) / "verdicts.jsonl"


def load_verdicts(settings: Settings, detector: str) -> list[Verdict]:
    path = verdicts_path(settings, detector)
    if not path.exists():
        return []
    return [
        Verdict(**json.loads(line))
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def run_detector(
    name: str,
    cases: list[CaseResult],
    settings: Settings,
    run: int = 1,
    progress: bool = True,
    merge: bool = True,
) -> tuple[list[Verdict], dict]:
    """Run one detector over `cases`.

    When `cases` is a subset of the benchmark, the verdicts already on disk for the
    other cases are kept, so running one project does not silently void the rest.
    """
    detector = build_detector(name, settings)
    usable = [case for case in cases if case.status == "valid" and case.workspace]
    progress = progress and sys.stdout.isatty()

    all_verdicts: list[Verdict] = []
    for index, case in enumerate(usable, start=1):
        if progress:
            print(f"  [{index:>3}/{len(usable)}] {case.case_id:<28}", end="\r", flush=True)
        all_verdicts.extend(detector.run_case(case, run=run))

    if progress:
        print(" " * 60, end="\r")

    written = all_verdicts
    if merge:
        touched = {case.case_id for case in usable}
        kept = [v for v in load_verdicts(settings, name) if v.case_id not in touched]
        if kept:
            order = {case.case_id: index for index, case in enumerate(cases)}
            written = sorted(
                kept + all_verdicts,
                key=lambda v: (order.get(v.case_id, 1 << 30), v.case_id, v.rule_id),
            )

    out = verdicts_path(settings, name)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as fh:
        for verdict in written:
            fh.write(verdict.model_dump_json() + "\n")

    cache = getattr(detector, "cache", None)
    stats = {
        "detector": name,
        "model": getattr(detector, "model", "n/a"),
        "cases": len(usable),
        "verdicts": len(written),
        "verdicts_this_run": len(all_verdicts),
        "cache_hits": getattr(cache, "hits", 0),
        "llm_calls": getattr(cache, "misses", 0),
        "run": run,
    }
    (settings.detector_dir(name) / "run.json").write_text(json.dumps(stats, indent=2))
    return all_verdicts, stats

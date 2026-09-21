"""Build and validate every case in the manifests, then write cases/built.jsonl."""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

from specdrift.bench.builder import PatchError, build_case, load_all_manifests
from specdrift.bench.schema import ALL_CATEGORIES, CATEGORY_NAMES, CaseResult, CaseSpec
from specdrift.bench.validator import validate_case
from specdrift.config import Settings


def build_one(case: CaseSpec, settings: Settings) -> CaseResult:
    try:
        workspace = build_case(case, settings.projects_dir, settings.work_dir)
    except PatchError as exc:
        return CaseResult(
            case_id=case.id,
            project=case.project,
            category=case.category,
            label=case.label,
            target_rules=list(case.target_rules),
            gold_symbol=case.gold_symbol,
            file=case.file,
            note=case.note,
            status="invalid",
            error=f"patch failed: {exc}",
        )
    return validate_case(case, workspace)


def build_all(
    settings: Settings,
    project: str | None = None,
    case_id: str | None = None,
    progress: bool = True,
) -> list[CaseResult]:
    """Build the selected cases.

    A filtered build updates only the matching rows of cases/built.jsonl and leaves
    the rest in place, so rebuilding one project never discards the others.
    """
    cases = load_all_manifests(settings.cases_dir)
    if project:
        cases = [case for case in cases if case.project == project]
    if case_id:
        cases = [case for case in cases if case.case_id_matches(case_id)]
    if not cases:
        return []

    progress = progress and sys.stdout.isatty()

    results: list[CaseResult] = []
    for index, case in enumerate(cases, start=1):
        if progress:
            print(f"  [{index:>3}/{len(cases)}] {case.id:<28}", end="\r", flush=True)
        results.append(build_one(case, settings))

    if progress:
        print(" " * 60, end="\r")

    settings.cases_dir.mkdir(parents=True, exist_ok=True)
    merged = results
    if project or case_id:
        fresh = {result.case_id for result in results}
        kept = [row for row in load_built(settings) if row.case_id not in fresh]
        order = {
            case.id: index
            for index, case in enumerate(load_all_manifests(settings.cases_dir))
        }
        merged = sorted(kept + results, key=lambda row: order.get(row.case_id, 1 << 30))

    with settings.built_cases_path.open("w", encoding="utf-8") as fh:
        for result in merged:
            fh.write(result.model_dump_json() + "\n")

    return results


def load_built(settings: Settings) -> list[CaseResult]:
    path = settings.built_cases_path
    if not path.exists():
        return []
    return [
        CaseResult(**json.loads(line))
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def summarise(results: list[CaseResult]) -> str:
    """The table printed after a build: counts, validity, and the escapes-tests rate."""
    by_cat: dict[str, list[CaseResult]] = {cat: [] for cat in ALL_CATEGORIES}
    for result in results:
        if result.category:
            by_cat[result.category].append(result)

    lines = [
        f"{'cat':<4} {'name':<30} {'n':>3} {'valid':>6} {'escapes tests':>14}",
        "-" * 62,
    ]
    for cat in ALL_CATEGORIES:
        rows = by_cat[cat]
        if not rows:
            continue
        valid = [r for r in rows if r.status == "valid"]
        escaped = [r for r in valid if r.escapes_tests]
        rate = f"{len(escaped)}/{len(valid)}" if valid else "-"
        pct = f" ({100 * len(escaped) / len(valid):.0f}%)" if valid else ""
        lines.append(
            f"{cat:<4} {CATEGORY_NAMES[cat]:<30} {len(rows):>3} {len(valid):>6} {rate + pct:>14}"
        )

    total_valid = [r for r in results if r.status == "valid"]
    drift_valid = [r for r in total_valid if r.is_drift]
    drift_escaped = [r for r in drift_valid if r.escapes_tests]
    invalid = [r for r in results if r.status == "invalid"]
    invalid_negatives = [r for r in invalid if r.label == "no_drift"]

    lines += [
        "-" * 62,
        f"{len(results)} cases, {len(total_valid)} valid, {len(invalid)} invalid "
        f"({len(invalid_negatives)} of them negative controls)",
    ]
    if drift_valid:
        pct = 100 * len(drift_escaped) / len(drift_valid)
        lines.append(
            f"drift that still passes the project's own tests: "
            f"{len(drift_escaped)}/{len(drift_valid)} ({pct:.0f}%)"
        )
    if invalid:
        lines.append("")
        lines.append("invalid cases:")
        for result in invalid:
            lines.append(f"  {result.case_id:<28} {result.error}")

    counts = Counter(r.project for r in results)
    lines.append("")
    lines.append("per project: " + ", ".join(f"{k}={v}" for k, v in sorted(counts.items())))
    return "\n".join(lines)

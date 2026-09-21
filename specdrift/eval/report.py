"""Render one page comparing every detector that has been scored."""

from __future__ import annotations

import json
from collections import Counter
from datetime import date
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from specdrift.bench.schema import (
    ALL_CATEGORIES,
    CATEGORY_NAMES,
    DRIFT_CATEGORIES,
    CaseResult,
    Verdict,
)
from specdrift.config import Settings
from specdrift.registry import DETECTOR_NAMES

TEMPLATES = Path(__file__).parent / "templates"


def dataset_summary(cases: list[CaseResult]) -> dict:
    valid = [case for case in cases if case.status == "valid"]
    rows = []
    for cat in ALL_CATEGORIES:
        subset = [case for case in valid if case.category == cat]
        if not subset:
            continue
        escaped = [case for case in subset if case.escapes_tests]
        rows.append(
            {
                "category": cat,
                "name": CATEGORY_NAMES[cat],
                "n": len(subset),
                "escapes": len(escaped),
                "escapes_rate": round(len(escaped) / len(subset), 4),
                "is_drift": cat in DRIFT_CATEGORIES,
            }
        )

    drift = [case for case in valid if case.is_drift]
    escaped_drift = [case for case in drift if case.escapes_tests]
    return {
        "rows": rows,
        "total": len(cases),
        "valid": len(valid),
        "invalid": len(cases) - len(valid),
        "projects": sorted({case.project for case in valid}),
        "drift": len(drift),
        "negatives": len(valid) - len(drift),
        "escapes_tests": len(escaped_drift),
        "escapes_rate": round(len(escaped_drift) / len(drift), 4) if drift else 0.0,
    }


def _load_metrics(settings: Settings, detector: str) -> dict | None:
    path = settings.detector_dir(detector) / "metrics.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _load_run(settings: Settings, detector: str) -> dict:
    path = settings.detector_dir(detector) / "run.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def example_verdicts(
    metrics: dict,
    cases: dict[str, CaseResult],
    verdicts: list[Verdict],
) -> list[dict]:
    """One caught drift, one missed drift and one false alarm, with the model's words."""
    by_case: dict[str, list[Verdict]] = {}
    for verdict in verdicts:
        by_case.setdefault(verdict.case_id, []).append(verdict)

    wanted = [
        ("TP", "caught drift"),
        ("FN", "missed drift"),
        ("FP", "false alarm on a negative control"),
    ]
    examples: list[dict] = []

    for outcome, label in wanted:
        row = next((r for r in metrics["outcomes"] if r["outcome"] == outcome), None)
        if row is None:
            continue
        case = cases.get(row["case_id"])
        if case is None:
            continue

        case_verdicts = by_case.get(case.case_id, [])
        shown = next((v for v in case_verdicts if v.flags_drift), None)
        if shown is None:
            shown = next(
                (v for v in case_verdicts if v.rule_id in case.target_rules),
                case_verdicts[0] if case_verdicts else None,
            )
        if shown is None:
            continue

        examples.append(
            {
                "outcome": outcome,
                "label": label,
                "case_id": case.case_id,
                "category": case.category,
                "category_name": CATEGORY_NAMES.get(case.category or "", ""),
                "note": case.note,
                "attribution": row.get("attribution", ""),
                "rule_id": shown.rule_id,
                "verdict": shown.verdict,
                "confidence": shown.confidence,
                "violated_clause": shown.violated_clause,
                "counterexample": shown.counterexample.model_dump(),
                "retrieved": shown.retrieved_chunks,
                "gold_symbol": case.gold_symbol,
            }
        )

    return examples


def build_report(settings: Settings, cases: list[CaseResult], verdicts_by_detector: dict) -> dict:
    scored = {}
    for name in DETECTOR_NAMES:
        metrics = _load_metrics(settings, name)
        if metrics:
            scored[name] = {"metrics": metrics, "run": _load_run(settings, name)}

    by_id = {case.case_id: case for case in cases}
    comparison = []
    for cat in ALL_CATEGORIES:
        row = {
            "category": cat,
            "name": CATEGORY_NAMES[cat],
            "is_drift": cat in DRIFT_CATEGORIES,
            "by_detector": {},
        }
        for name, payload in scored.items():
            entry = payload["metrics"]["per_category"].get(cat)
            row["by_detector"][name] = entry["value"] if entry else None
            row["n"] = entry["n"] if entry else row.get("n", 0)
        comparison.append(row)

    retrieval_path = settings.results_dir / "retrieval.json"
    retrieval = json.loads(retrieval_path.read_text()) if retrieval_path.exists() else None

    attribution = {
        name: Counter(payload["metrics"]["attribution"]) for name, payload in scored.items()
    }

    examples = {}
    for name, payload in scored.items():
        examples[name] = example_verdicts(
            payload["metrics"], by_id, verdicts_by_detector.get(name, [])
        )

    return {
        "generated": date.today().isoformat(),
        "category_names": CATEGORY_NAMES,
        "dataset": dataset_summary(cases),
        "detectors": scored,
        "comparison": comparison,
        "retrieval": retrieval,
        "attribution": attribution,
        "examples": examples,
    }


def render(context: dict, settings: Settings) -> tuple[Path, Path]:
    env = Environment(
        loader=FileSystemLoader(TEMPLATES),
        autoescape=select_autoescape(["html"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.filters["pct"] = lambda v: "-" if v is None else f"{v * 100:.0f}%"

    settings.results_dir.mkdir(parents=True, exist_ok=True)
    html_path = settings.results_dir / "report.html"
    md_path = settings.results_dir / "report.md"

    html_path.write_text(env.get_template("report.html.jinja").render(**context), encoding="utf-8")
    md_path.write_text(env.get_template("report.md.jinja").render(**context), encoding="utf-8")
    return html_path, md_path

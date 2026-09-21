"""Score a detector's verdicts against the case labels.

The positive class is DRIFT. A drift case counts as caught only when the detector flags
the rule the injection actually targeted, so a lucky flag on an unrelated rule earns
nothing. Every flag on a negative control is a false alarm, weighted exactly as heavily
as a miss.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict

from specdrift.bench.schema import (
    ALL_CATEGORIES,
    CATEGORY_NAMES,
    DRIFT_CATEGORIES,
    NEGATIVE_CATEGORIES,
    CaseResult,
    Verdict,
)
from specdrift.config import Settings
from specdrift.retrieval.retriever import matches_gold


def _safe_div(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


def group_verdicts(verdicts: list[Verdict]) -> dict[str, list[Verdict]]:
    grouped: dict[str, list[Verdict]] = defaultdict(list)
    for verdict in verdicts:
        grouped[verdict.case_id].append(verdict)
    return grouped


def case_outcome(case: CaseResult, verdicts: list[Verdict]) -> dict:
    """Decide TP / FN / FP / TN for one case, and say why a miss happened."""
    flagged = [v for v in verdicts if v.flags_drift]
    uncertain = [v for v in verdicts if v.verdict == "UNCERTAIN"]

    if case.is_drift:
        if case.target_rules:
            on_target = [v for v in flagged if v.rule_id in case.target_rules]
        else:
            # D8 scope creep names no rule: any drift flag on the case counts.
            on_target = flagged

        caught = bool(on_target)
        spurious = [v for v in flagged if v.rule_id not in case.target_rules]

        attribution = ""
        if not caught:
            attribution = _attribute_miss(case, verdicts)

        return {
            "case_id": case.case_id,
            "category": case.category,
            "label": case.label,
            "outcome": "TP" if caught else "FN",
            "flagged_rules": [v.rule_id for v in on_target],
            "spurious_rules": [v.rule_id for v in spurious],
            "attribution": attribution,
            "uncertain": len(uncertain),
            "confidence": max((v.confidence for v in on_target), default=0.0),
        }

    return {
        "case_id": case.case_id,
        "category": case.category,
        "label": case.label,
        "outcome": "FP" if flagged else "TN",
        "flagged_rules": [v.rule_id for v in flagged],
        "spurious_rules": [],
        "attribution": "",
        "uncertain": len(uncertain),
        "confidence": max((v.confidence for v in flagged), default=0.0),
    }


def _attribute_miss(case: CaseResult, verdicts: list[Verdict]) -> str:
    """Was the right code never shown, or shown and misread?

    'n/a' is the honest answer for a detector with no retrieval stage - a whole-file
    prompt cannot fail to retrieve.
    """
    relevant = [v for v in verdicts if not case.target_rules or v.rule_id in case.target_rules]
    if not relevant or not any(v.retrieved_chunks for v in relevant):
        return "n/a"
    if not case.gold_symbol:
        return "reasoning"

    saw_gold = any(
        matches_gold(chunk_id, case.gold_symbol)
        for verdict in relevant
        for chunk_id in verdict.retrieved_chunks
    )
    return "reasoning" if saw_gold else "retrieval"


def score(
    cases: list[CaseResult],
    verdicts: list[Verdict],
    detector: str,
) -> dict:
    grouped = group_verdicts(verdicts)
    usable = [case for case in cases if case.status == "valid"]

    outcomes = [case_outcome(case, grouped.get(case.case_id, [])) for case in usable]
    tally = Counter(row["outcome"] for row in outcomes)
    tp, fn, fp, tn = tally["TP"], tally["FN"], tally["FP"], tally["TN"]

    precision = _safe_div(tp, tp + fp)
    recall = _safe_div(tp, tp + fn)
    f1 = round(2 * precision * recall / (precision + recall), 4) if precision + recall else 0.0

    per_category: dict[str, dict] = {}
    for cat in ALL_CATEGORIES:
        rows = [row for row in outcomes if row["category"] == cat]
        if not rows:
            continue
        counts = Counter(row["outcome"] for row in rows)
        entry = {
            "name": CATEGORY_NAMES[cat],
            "n": len(rows),
            "uncertain": sum(row["uncertain"] for row in rows),
        }
        if cat in DRIFT_CATEGORIES:
            entry["metric"] = "recall"
            entry["value"] = _safe_div(counts["TP"], len(rows))
            entry["caught"] = counts["TP"]
            entry["missed"] = counts["FN"]
        else:
            entry["metric"] = "false alarm rate"
            entry["value"] = _safe_div(counts["FP"], len(rows))
            entry["false_alarms"] = counts["FP"]
            entry["clean"] = counts["TN"]
        per_category[cat] = entry

    negatives = [row for row in outcomes if row["category"] in NEGATIVE_CATEGORIES]
    attribution = Counter(
        row["attribution"] for row in outcomes if row["outcome"] == "FN" and row["attribution"]
    )
    spurious = sum(len(row["spurious_rules"]) for row in outcomes)
    uncertain_total = sum(row["uncertain"] for row in outcomes)

    return {
        "detector": detector,
        "cases_scored": len(usable),
        "counts": {"TP": tp, "FN": fn, "FP": fp, "TN": tn},
        "overall": {
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "false_alarm_rate": _safe_div(fp, len(negatives)),
            "uncertain_rate": _safe_div(uncertain_total, len(verdicts)),
            "spurious_rule_flags": spurious,
        },
        "per_category": per_category,
        "attribution": dict(attribution),
        "outcomes": outcomes,
    }


def format_scores(report: dict) -> str:
    overall, counts = report["overall"], report["counts"]
    header = f"{'cat':<4} {'name':<30} {'n':>3} {'metric':>16} {'value':>7} {'unc':>4}"
    lines = [
        f"detector: {report['detector']}   cases: {report['cases_scored']}",
        "",
        header,
        "-" * len(header),
    ]

    for cat, row in report["per_category"].items():
        lines.append(
            f"{cat:<4} {row['name']:<30} {row['n']:>3} {row['metric']:>16} "
            f"{row['value']:>7.2f} {row['uncertain']:>4}"
        )

    lines += [
        "-" * len(header),
        f"TP {counts['TP']}  FN {counts['FN']}  FP {counts['FP']}  TN {counts['TN']}",
        f"precision {overall['precision']:.2f}   recall {overall['recall']:.2f}   "
        f"F1 {overall['f1']:.2f}   false-alarm rate {overall['false_alarm_rate']:.2f}",
        f"uncertain {overall['uncertain_rate']:.2f} of all verdicts   "
        f"spurious rule flags {overall['spurious_rule_flags']}",
    ]

    if report["attribution"]:
        parts = ", ".join(f"{k}: {v}" for k, v in sorted(report["attribution"].items()))
        lines.append(f"missed drift attributed to -> {parts}")

    return "\n".join(lines)


def write_scores(report: dict, settings: Settings) -> None:
    out_dir = settings.detector_dir(report["detector"])
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "metrics.json").write_text(json.dumps(report, indent=2), encoding="utf-8")

    rows = ["category,name,n,metric,value,uncertain"]
    for cat, row in report["per_category"].items():
        rows.append(
            f"{cat},{row['name']},{row['n']},{row['metric']},{row['value']},{row['uncertain']}"
        )
    (out_dir / "per_category.csv").write_text("\n".join(rows) + "\n", encoding="utf-8")

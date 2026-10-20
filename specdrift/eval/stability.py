"""Repeat-run statistics: how much of a score is the detector, how much is luck.

A single run of ~86 cases cannot say whether a 0.58 recall is 0.58 or 0.45. Two sources
of noise are quantified here:

* run-to-run variance - the LLM is not deterministic, so repeats disagree;
* case-sampling variance - only 6-9 cases per category, so the set itself is a sample.

The bootstrap resamples cases with replacement and pools every run's outcome for each
drawn case, so its interval covers both.
"""

from __future__ import annotations

import random
import statistics
from collections import Counter, defaultdict

from specdrift.bench.schema import DRIFT_CATEGORIES, CaseResult, Verdict
from specdrift.eval.metrics import case_outcome, group_verdicts

METRICS = ("precision", "recall", "f1", "false_alarm_rate")


def _rates(tally: Counter) -> dict[str, float]:
    tp, fn, fp, tn = tally["TP"], tally["FN"], tally["FP"], tally["TN"]
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "false_alarm_rate": fp / (fp + tn) if fp + tn else 0.0,
    }


def _percentile(sorted_values: list[float], q: float) -> float:
    if not sorted_values:
        return 0.0
    index = min(len(sorted_values) - 1, max(0, round(q * (len(sorted_values) - 1))))
    return sorted_values[index]


def _interval(values: list[float], alpha: float = 0.05) -> tuple[float, float]:
    ordered = sorted(values)
    return _percentile(ordered, alpha / 2), _percentile(ordered, 1 - alpha / 2)


def score_runs(
    cases: list[CaseResult],
    verdict_sets: dict[int, list[Verdict]],
    detector: str,
    n_boot: int = 2000,
    seed: int = 0,
) -> dict:
    """Aggregate per-run outcomes into means, run-to-run spread and bootstrap 95% CIs."""
    usable = [case for case in cases if case.status == "valid"]
    runs = sorted(verdict_sets)
    grouped = {run: group_verdicts(verdict_sets[run]) for run in runs}

    # outcomes[case_id] -> one outcome label per run
    outcomes: dict[str, list[str]] = {}
    for case in usable:
        outcomes[case.case_id] = [
            case_outcome(case, grouped[run].get(case.case_id, []))["outcome"] for run in runs
        ]

    per_run: list[dict] = []
    for index, run in enumerate(runs):
        tally = Counter(labels[index] for labels in outcomes.values())
        per_run.append({"run": run, "counts": dict(tally), **{k: round(v, 4) for k, v in _rates(tally).items()}})

    def pooled(case_ids: list[str]) -> Counter:
        tally: Counter = Counter()
        for case_id in case_ids:
            tally.update(outcomes[case_id])
        return tally

    all_ids = [case.case_id for case in usable]
    point = _rates(pooled(all_ids))

    rng = random.Random(seed)
    draws: dict[str, list[float]] = defaultdict(list)
    for _ in range(n_boot):
        sample = [rng.choice(all_ids) for _ in all_ids]
        for key, value in _rates(pooled(sample)).items():
            draws[key].append(value)

    overall = {}
    for key in METRICS:
        per_run_values = [float(row[key]) for row in per_run]
        low, high = _interval(draws[key])
        overall[key] = {
            "mean": round(point[key], 4),
            "run_std": round(statistics.pstdev(per_run_values), 4) if len(per_run_values) > 1 else 0.0,
            "ci95": [round(low, 4), round(high, 4)],
        }

    per_category = {}
    by_category: dict[str, list[str]] = defaultdict(list)
    for case in usable:
        by_category[str(case.category)].append(case.case_id)
    for category, ids in by_category.items():
        hit = "TP" if category in DRIFT_CATEGORIES else "FP"
        metric = "recall" if category in DRIFT_CATEGORIES else "false_alarm_rate"
        values = []
        for _ in range(n_boot):
            sample = [rng.choice(ids) for _ in ids]
            tally = pooled(sample)
            values.append(tally[hit] / sum(tally.values()))
        low, high = _interval(values)
        per_category[category] = {
            "metric": metric,
            "n": len(ids),
            "mean": round(pooled(ids)[hit] / (len(ids) * len(runs)), 4),
            "ci95": [round(low, 4), round(high, 4)],
        }

    return {
        "detector": detector,
        "runs": runs,
        "n_boot": n_boot,
        "cases_scored": len(usable),
        "per_run": per_run,
        "overall": overall,
        "per_category": per_category,
        "flip_rate": _flip_rate(outcomes),
    }


def _flip_rate(outcomes: dict[str, list[str]]) -> float:
    """Share of cases whose outcome is not the same in every run."""
    if not outcomes:
        return 0.0
    unstable = sum(1 for labels in outcomes.values() if len(set(labels)) > 1)
    return round(unstable / len(outcomes), 4)


def format_stability(report: dict) -> str:
    lines = [
        f"detector: {report['detector']}   runs: {len(report['runs'])}   "
        f"cases: {report['cases_scored']}   bootstrap: {report['n_boot']}",
        "",
        f"{'metric':<18} {'mean':>6} {'run sd':>7}   95% CI",
    ]
    for key, row in report["overall"].items():
        low, high = row["ci95"]
        lines.append(f"{key:<18} {row['mean']:>6.2f} {row['run_std']:>7.3f}   [{low:.2f}, {high:.2f}]")
    lines += ["", f"{'cat':<4} {'metric':<17} {'n':>3} {'mean':>6}   95% CI"]
    for cat, row in report["per_category"].items():
        low, high = row["ci95"]
        lines.append(f"{cat:<4} {row['metric']:<17} {row['n']:>3} {row['mean']:>6.2f}   [{low:.2f}, {high:.2f}]")
    lines.append("")
    lines.append(f"cases whose outcome changed between runs: {report['flip_rate']:.0%}")
    if len(report["runs"]) < 2:
        lines.append("only one run: the interval reflects case sampling only; run `specdrift run --repeat 3` for run-to-run spread.")
    return "\n".join(lines)

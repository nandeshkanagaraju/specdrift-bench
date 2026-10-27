"""Compare detector arms on the frozen cases: what `specdrift stability` does not report.

`stability` gives precision, recall, F1 and false-alarm rate with bootstrap intervals. This adds, for each arm:

* strict precision and the UNCERTAIN rate, with the same case-level bootstrap;
* the abstention curve (coverage against accuracy as the confidence threshold rises);
* expected calibration error;
* a paired difference against a baseline arm, which is what hypothesis H1 actually asks.

Pair-level truth. The curve and the calibration error need a truth per (case, rule) verdict:
DRIFT when the case is a drift case and the rule is one the injection targeted, COMPLIANT for every other
rule of every case. This is the same convention strict precision uses (a flag on a non-target rule of a drift
case is charged), and it is an approximation: a non-target rule of a drifted file may really be broken.
D8 cases and reverse-direction verdicts have no per-rule truth and are left out of the curve and the ECE.

Confidence is read as the model's confidence in the verdict it stated. The prompt does not define it more
sharply, so a model that uses it differently will look miscalibrated.
"""

from __future__ import annotations

import random
from collections import Counter, defaultdict
from collections.abc import Callable, Sequence

from specdrift.bench.schema import CaseResult, Verdict
from specdrift.eval.metrics import case_outcome, group_verdicts
from specdrift.eval.stability import _interval, _rates, score_runs

ECE_BINS = 10
ANSWERS = ("DRIFT", "COMPLIANT")      # UNCERTAIN is an abstention


# --- pair-level truth -------------------------------------------------------------------------

def scored_pairs(cases: Sequence[CaseResult], verdict_sets: dict[int, list[Verdict]]) -> list[dict]:
    """One row per forward verdict that has a per-rule truth. `unit` is the bootstrap resampling key."""
    by_id = {case.case_id: case for case in cases if case.status == "valid"}
    pairs: list[dict] = []
    for run, verdicts in sorted(verdict_sets.items()):
        for verdict in verdicts:
            case = by_id.get(verdict.case_id)
            if case is None or verdict.direction != "forward":
                continue
            if case.is_drift and not case.target_rules:
                continue                                     # D8: no per-rule truth
            truth = "DRIFT" if case.is_drift and verdict.rule_id in case.target_rules else "COMPLIANT"
            pairs.append({"unit": case.case_id, "run": run, "truth": truth,
                          "verdict": verdict.verdict, "confidence": float(verdict.confidence)})
    return pairs


def _answered(pairs: Sequence[dict], tau: float = 0.0) -> list[dict]:
    return [p for p in pairs if p["verdict"] in ANSWERS and p["confidence"] >= tau]


def coverage_accuracy_curve(pairs: Sequence[dict], max_points: int = 21) -> list[dict]:
    """Raise the confidence threshold: an answer below it becomes an abstention.

    coverage  = answered / all pairs                       accuracy = correct / answered
    recall    = DRIFT pairs flagged / ALL DRIFT pairs      false_alarm_rate = clean pairs flagged / ALL clean pairs
    Recall and false-alarm rate are against all pairs, so abstaining on a drift pair costs recall and abstaining
    on a clean pair saves a false alarm: the curve shows what each threshold buys.
    """
    total = len(pairs)
    if not total:
        return []
    positives = sum(1 for p in pairs if p["truth"] == "DRIFT")
    negatives = total - positives
    cuts = sorted({0.0} | {round(p["confidence"], 4) for p in pairs if p["verdict"] in ANSWERS})
    if len(cuts) > max_points:
        step = (len(cuts) - 1) / (max_points - 1)
        cuts = [cuts[round(i * step)] for i in range(max_points)]
    curve = []
    for tau in cuts:
        kept = _answered(pairs, tau)
        correct = sum(1 for p in kept if p["verdict"] == p["truth"])
        caught = sum(1 for p in kept if p["truth"] == "DRIFT" and p["verdict"] == "DRIFT")
        alarms = sum(1 for p in kept if p["truth"] == "COMPLIANT" and p["verdict"] == "DRIFT")
        curve.append({
            "threshold": tau,
            "answered": len(kept),
            "coverage": round(len(kept) / total, 4),
            "accuracy": round(correct / len(kept), 4) if kept else None,
            "recall": round(caught / positives, 4) if positives else None,
            "false_alarm_rate": round(alarms / negatives, 4) if negatives else None,
        })
    return curve


def expected_calibration_error(pairs: Sequence[dict], bins: int = ECE_BINS) -> dict:
    """Weighted gap between stated confidence and accuracy over answered (non-UNCERTAIN) pairs."""
    kept = _answered(pairs)
    if not kept:
        return {"ece": None, "answered": 0, "bins": []}
    grouped: dict[int, list[dict]] = defaultdict(list)
    for p in kept:
        grouped[min(bins - 1, int(max(0.0, min(1.0, p["confidence"])) * bins))].append(p)
    ece, table = 0.0, []
    for index in sorted(grouped):
        members = grouped[index]
        accuracy = sum(1 for p in members if p["verdict"] == p["truth"]) / len(members)
        confidence = sum(p["confidence"] for p in members) / len(members)
        ece += len(members) / len(kept) * abs(accuracy - confidence)
        table.append({"low": index / bins, "high": (index + 1) / bins, "n": len(members),
                      "confidence": round(confidence, 4), "accuracy": round(accuracy, 4)})
    return {"ece": round(ece, 4), "answered": len(kept), "bins": table}


# --- bootstrap --------------------------------------------------------------------------------

def bootstrap_ci(units: Sequence[str], stat: Callable[[list[str]], float | None],
                 n_boot: int = 2000, seed: int = 0) -> list[float] | None:
    """95% percentile interval of `stat` over resamples (with replacement) of `units`."""
    if not units:
        return None
    rng = random.Random(seed)
    draws = [v for v in (stat([rng.choice(units) for _ in units]) for _ in range(n_boot)) if v is not None]
    if not draws:
        return None
    low, high = _interval(draws)
    return [round(low, 4), round(high, 4)]


def case_rows(cases: Sequence[CaseResult], verdict_sets: dict[int, list[Verdict]]) -> dict[str, list[dict]]:
    """case_id -> one row per run: the outcome plus the counts strict precision and UNCERTAIN rate need."""
    runs = sorted(verdict_sets)
    grouped = {run: group_verdicts(verdict_sets[run]) for run in runs}
    rows: dict[str, list[dict]] = {}
    for case in cases:
        if case.status != "valid":
            continue
        per_run = []
        for run in runs:
            verdicts = grouped[run].get(case.case_id, [])
            outcome = case_outcome(case, verdicts)
            per_run.append({"outcome": outcome["outcome"], "spurious": len(outcome["spurious_rules"]),
                            "uncertain": outcome["uncertain"], "verdicts": len(verdicts)})
        rows[case.case_id] = per_run
    return rows


def _pool(ids: Sequence[str], rows: dict[str, list[dict]]) -> tuple[Counter, int, int, int]:
    tally: Counter = Counter()
    spurious = uncertain = verdicts = 0
    for case_id in ids:
        for row in rows[case_id]:
            tally[row["outcome"]] += 1
            spurious += row["spurious"]
            uncertain += row["uncertain"]
            verdicts += row["verdicts"]
    return tally, spurious, uncertain, verdicts


def _strict_precision(ids: Sequence[str], rows: dict[str, list[dict]]) -> float:
    tally, spurious, _, _ = _pool(ids, rows)
    denominator = tally["TP"] + tally["FP"] + spurious
    return tally["TP"] / denominator if denominator else 0.0


def _uncertain_rate(ids: Sequence[str], rows: dict[str, list[dict]]) -> float:
    _, _, uncertain, verdicts = _pool(ids, rows)
    return uncertain / verdicts if verdicts else 0.0


def paired_difference(cases: Sequence[CaseResult], arm: dict[int, list[Verdict]], baseline: dict[int, list[Verdict]],
                      n_boot: int = 2000, seed: int = 0) -> dict:
    """arm minus baseline for false-alarm rate and recall, resampling the same cases for both.

    A paired interval is what H1 needs: the two arms are scored on identical cases, so most case difficulty
    cancels, which two separate intervals would not show.
    """
    rows_arm, rows_base = case_rows(cases, arm), case_rows(cases, baseline)
    ids = sorted(set(rows_arm) & set(rows_base))

    def metric(name: str) -> Callable[[list[str]], float]:
        def stat(sample: list[str]) -> float:
            return _rates(_pool(sample, rows_arm)[0])[name] - _rates(_pool(sample, rows_base)[0])[name]
        return stat

    out: dict = {"cases": len(ids)}
    for name in ("false_alarm_rate", "recall"):
        point = metric(name)(ids)
        out[name] = {"difference": round(point, 4), "ci95": bootstrap_ci(ids, metric(name), n_boot, seed)}
    return out


# --- one arm ----------------------------------------------------------------------------------

def arm_report(cases: Sequence[CaseResult], verdict_sets: dict[int, list[Verdict]], name: str,
               n_boot: int = 2000, seed: int = 0) -> dict:
    """Everything the comparison table needs for one arm."""
    if not verdict_sets:
        raise ValueError(f"{name}: no verdicts to score")
    stability = score_runs(list(cases), verdict_sets, name, n_boot=n_boot, seed=seed)
    rows = case_rows(cases, verdict_sets)
    ids = sorted(rows)

    def over_cases(fn: Callable[[Sequence[str], dict[str, list[dict]]], float]) -> Callable[[list[str]], float]:
        return lambda sample: fn(sample, rows)

    extra = {}
    for key, fn in (("strict_precision", _strict_precision), ("uncertain_rate", _uncertain_rate)):
        extra[key] = {
            "mean": round(fn(ids, rows), 4),
            "ci95": bootstrap_ci(ids, over_cases(fn), n_boot, seed),
        }

    pairs = scored_pairs(cases, verdict_sets)
    by_unit: dict[str, list[dict]] = defaultdict(list)
    for p in pairs:
        by_unit[p["unit"]].append(p)

    def ece_of(sample: list[str]) -> float | None:
        return expected_calibration_error([p for unit in sample for p in by_unit[unit]])["ece"]

    calibration = expected_calibration_error(pairs)
    calibration["ece_ci95"] = bootstrap_ci(sorted(by_unit), ece_of, n_boot, seed)

    return {
        "arm": name,
        "runs": stability["runs"],
        "cases_scored": stability["cases_scored"],
        "stability": stability,
        "extra": extra,
        "abstention": {"pairs": len(pairs), "curve": coverage_accuracy_curve(pairs)},
        "calibration": calibration,
    }

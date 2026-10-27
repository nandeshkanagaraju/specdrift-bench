"""Test-2: the unseen `examples/` projects, scored per rule against `examples/expected.json`.

Ground truth is the authors' own claim in expected.json (which rules were drifted), with no oracle test behind
it, and only projects listed there are scored. Truth per rule: DRIFT if listed as drifted, COMPLIANT otherwise.
Only forward (rule to code) verdicts are scored: the "unspecified behaviour" entries are a reverse-direction
finding and are not part of this table. With a handful of projects the intervals are wide; say so when quoting them.

Nothing here is ever used for training, tuning or choosing a threshold.
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Iterable
from pathlib import Path

from specdrift.bench.schema import Verdict
from specdrift.config import REPO_ROOT, Settings
from specdrift.eval.compare import bootstrap_ci, coverage_accuracy_curve, expected_calibration_error
from specdrift.eval.stability import _rates

EXAMPLES_DIR = REPO_ROOT / "examples"
EXPECTED_PATH = EXAMPLES_DIR / "expected.json"


def load_expected(path: Path = EXPECTED_PATH) -> dict[str, set[str]]:
    """project -> the rule ids that are drifted in its code."""
    data = json.loads(path.read_text(encoding="utf-8"))
    return {project: set(entry.get("drift", {})) for project, entry in data.items()}


def unscored_projects(expected: dict[str, set[str]], examples_dir: Path = EXAMPLES_DIR) -> list[str]:
    """Example projects that have a spec but no ground truth, so they cannot be scored."""
    present = [p.name for p in sorted(examples_dir.iterdir()) if (p / "spec.md").is_file()]
    return [name for name in present if name not in expected]


def heldout_path(settings: Settings, detector: str, run: int) -> Path:
    return settings.detector_dir(detector) / f"heldout.run{run}.jsonl"


def available_heldout_runs(settings: Settings, detector: str) -> list[int]:
    runs = []
    for path in settings.detector_dir(detector).glob("heldout.run*.jsonl"):
        suffix = path.name[len("heldout.run"):-len(".jsonl")]
        if suffix.isdigit():
            runs.append(int(suffix))
    return sorted(runs)


def load_heldout(settings: Settings, detector: str, run: int) -> list[Verdict]:
    path = heldout_path(settings, detector, run)
    return [Verdict(**json.loads(line)) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def run_heldout(settings: Settings, run: int, projects: Iterable[str] | None = None,
                examples_dir: Path = EXAMPLES_DIR, detector: str = "specguard") -> tuple[list[Verdict], dict]:
    """Check each expected project with Stage 1 and Stage 2, exactly as the live check does, and store the verdicts.

    `case_id` is rewritten from the live check's constant to the project name so verdicts can be told apart.
    """
    from specdrift.live import check_project

    expected = load_expected(examples_dir / "expected.json")
    chosen = list(projects) if projects else sorted(expected)
    unknown = [name for name in chosen if name not in expected]
    if unknown:
        raise ValueError(f"no ground truth in expected.json for: {', '.join(unknown)}")

    verdicts: list[Verdict] = []
    model = "n/a"
    for name in chosen:
        found, info = check_project(examples_dir / name, settings, run=run)
        model = info["model"]
        verdicts += [v.model_copy(update={"case_id": name}) for v in found]

    out = heldout_path(settings, detector, run)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("".join(v.model_dump_json() + "\n" for v in verdicts), encoding="utf-8")
    return verdicts, {"projects": chosen, "verdicts": len(verdicts), "model": model, "run": run}


def heldout_pairs(expected: dict[str, set[str]], verdict_sets: dict[int, list[Verdict]]) -> list[dict]:
    """One row per (run, project, rule). A drifted rule with no verdict at all counts as an abstention."""
    pairs: list[dict] = []
    for run, verdicts in sorted(verdict_sets.items()):
        seen: dict[tuple[str, str], Verdict] = {}
        for v in verdicts:
            if v.case_id in expected and v.direction == "forward":
                seen[(v.case_id, v.rule_id)] = v
        universe = set(seen) | {(project, rule) for project, rules in expected.items() for rule in rules}
        for project, rule_id in sorted(universe):
            found = seen.get((project, rule_id))
            pairs.append({
                "unit": f"{project}:{rule_id}", "run": run,
                "truth": "DRIFT" if rule_id in expected[project] else "COMPLIANT",
                "verdict": found.verdict if found else "UNCERTAIN",
                "confidence": float(found.confidence) if found else 0.0,
            })
    return pairs


def _tally(pairs: Iterable[dict]) -> Counter:
    tally: Counter = Counter()
    for p in pairs:
        flagged = p["verdict"] == "DRIFT"
        tally[("TP" if flagged else "FN") if p["truth"] == "DRIFT" else ("FP" if flagged else "TN")] += 1
    return tally


def score_heldout(expected: dict[str, set[str]], verdict_sets: dict[int, list[Verdict]], name: str,
                  n_boot: int = 2000, seed: int = 0) -> dict:
    if not verdict_sets:
        raise ValueError(f"{name}: no held-out verdicts to score")
    pairs = heldout_pairs(expected, verdict_sets)
    by_unit: dict[str, list[dict]] = {}
    for p in pairs:
        by_unit.setdefault(p["unit"], []).append(p)
    units = sorted(by_unit)

    def rate(key: str):
        return lambda sample: _rates(_tally(p for u in sample for p in by_unit[u]))[key]

    overall = {key: {"mean": round(rate(key)(units), 4), "ci95": bootstrap_ci(units, rate(key), n_boot, seed)}
               for key in ("recall", "precision", "false_alarm_rate")}
    uncertain = sum(1 for p in pairs if p["verdict"] == "UNCERTAIN") / len(pairs)

    def uncertain_of(sample: list[str]) -> float:
        chosen = [p for u in sample for p in by_unit[u]]
        return sum(1 for p in chosen if p["verdict"] == "UNCERTAIN") / len(chosen)

    per_run = []
    for run in sorted(verdict_sets):
        counts = _tally(p for p in pairs if p["run"] == run)
        per_run.append({"run": run, "counts": dict(counts),
                        **{k: round(v, 4) for k, v in _rates(counts).items()}})
    return {
        "arm": name,
        "runs": sorted(verdict_sets),
        "projects": sorted(expected),
        "rules": len(units),
        "drift_rules": sum(len(r) for r in expected.values()),
        "overall": overall,
        "uncertain_rate": {"mean": round(uncertain, 4), "ci95": bootstrap_ci(units, uncertain_of, n_boot, seed)},
        "per_run": per_run,
        "abstention": {"pairs": len(pairs), "curve": coverage_accuracy_curve(pairs)},
        "calibration": expected_calibration_error(pairs),
    }

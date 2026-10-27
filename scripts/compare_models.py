"""Run every detector arm on the frozen cases and the unseen examples/ projects, then compare them.

    python scripts/compare_models.py run    --arms scripts/compare_arms.example.json --out results_compare            # plan only
    python scripts/compare_models.py run    --arms ... --out results_compare --execute                                # really run
    python scripts/compare_models.py report --arms ... --out results_compare                                          # analysis only

`run` prints the plan unless `--execute` is given, because executing spends API money (openai/anthropic arms) or GPU
time (huggingface arms). Each arm runs `specdrift run --repeat N` over the 86 cases and, for specguard arms,
`specdrift heldout --repeat N` over the examples/ projects, with RESULTS_DIR pointed at `<out>/<arm>` so arms never
overwrite each other or the existing results/. An arm may instead name an existing `results_dir` to reuse (it is not re-run).

`report` reads those results and writes `<out>/comparison.json` and `comparison.md`: per-category recall, precision,
strict precision, false-alarm rate, UNCERTAIN rate with bootstrap 95% CIs (the same resampling `specdrift stability`
uses), the abstention coverage-against-accuracy curve, expected calibration error, a paired difference against the
baseline arm, and the test-2 table. Nothing here trains or tunes on the frozen cases.

An arm file never holds a secret. API keys stay in .env, which `specdrift` reads itself; only the settings in
ALLOWED_ENV may be overridden per arm.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

ALLOWED_ENV = {"LLM_PROVIDER", "LLM_MODEL", "LLM_ADAPTER", "LLM_BASE_URL", "LLM_MAX_TOKENS",
               "EMBED_BACKEND", "EMBED_MODEL", "TOP_K"}
DETECTORS = ("specguard", "keyword", "wholefile")
NAME_RE = re.compile(r"^[A-Za-z0-9._-]+$")
PLACEHOLDER = "<<"


class ArmError(ValueError):
    pass


def load_arms(path: Path) -> tuple[list[dict], str]:
    """Validated arms and the baseline's name."""
    data = json.loads(path.read_text(encoding="utf-8"))
    arms, seen = [], set()
    for raw in data.get("arms", []):
        name = raw.get("name", "")
        if not NAME_RE.match(name):
            raise ArmError(f"arm name {name!r} must match {NAME_RE.pattern}")
        if name in seen:
            raise ArmError(f"duplicate arm {name!r}")
        seen.add(name)
        detector = raw.get("detector", "specguard")
        if detector not in DETECTORS:
            raise ArmError(f"{name}: detector must be one of {DETECTORS}")
        env = {str(k): str(v) for k, v in raw.get("env", {}).items()}
        forbidden = sorted(set(env) - ALLOWED_ENV)
        if forbidden:
            raise ArmError(f"{name}: may not set {', '.join(forbidden)} (secrets stay in .env; allowed: "
                           f"{', '.join(sorted(ALLOWED_ENV))})")
        runs = raw.get("runs")
        if runs is not None and (not isinstance(runs, int) or isinstance(runs, bool) or runs < 1):
            raise ArmError(f"{name}: runs must be a whole number of at least 1")
        arms.append({"name": name, "detector": detector, "env": env, "results_dir": raw.get("results_dir", ""),
                     "runs": runs})
    baseline = data.get("baseline", arms[0]["name"] if arms else "")
    if arms and baseline not in seen:
        raise ArmError(f"baseline {baseline!r} is not one of the arms")
    return arms, baseline


def pending_placeholders(arm: dict) -> list[str]:
    return sorted(k for k, v in arm["env"].items() if PLACEHOLDER in v)


def arm_results_dir(arm: dict, out: Path) -> Path:
    if arm["results_dir"]:
        path = Path(arm["results_dir"])
        return path if path.is_absolute() else REPO_ROOT / path
    return out / arm["name"]


def commands_for(arm: dict, runs: int, heldout: bool = True) -> list[list[str]]:
    base = [sys.executable, "-m", "specdrift.cli"]
    commands = [base + ["run", "--detector", arm["detector"], "--repeat", str(runs)]]
    if heldout and arm["detector"] == "specguard":
        commands.append(base + ["heldout", "--repeat", str(runs)])
    return commands


def env_for(arm: dict, out: Path) -> dict[str, str]:
    """The parent environment plus the arm's whitelisted overrides. Nothing secret is added or printed."""
    env = dict(os.environ)
    env.update(arm["env"])
    env["RESULTS_DIR"] = str(arm_results_dir(arm, out))
    return env


def plan(arms: list[dict], out: Path, runs: int, heldout: bool = True) -> list[dict]:
    steps = []
    for arm in arms:
        if arm["results_dir"]:
            steps.append({"arm": arm["name"], "skip": f"reuses existing results in {arm['results_dir']}"})
        elif pending_placeholders(arm):
            steps.append({"arm": arm["name"], "skip": f"unfinished placeholder in {', '.join(pending_placeholders(arm))}"})
        else:
            # An arm may fix its own run count: greedy decoding of a local model is deterministic, so repeating it
            # only burns GPU hours on identical answers.
            steps.append({"arm": arm["name"], "env": arm["env"], "results": str(arm_results_dir(arm, out)),
                          "commands": commands_for(arm, arm["runs"] or runs, heldout)})
    return steps


# --- report -----------------------------------------------------------------------------------

def fmt(mean, ci=None) -> str:
    if mean is None:
        return "n/a"
    text = f"{mean:.2f}"
    return f"{text} [{ci[0]:.2f}, {ci[1]:.2f}]" if ci else text


def build_comparison(cases, expected, arm_data: dict[str, dict], baseline: str, n_boot: int = 2000, seed: int = 0) -> dict:
    """arm_data[name] = {"detector", "fake", "sets": {run: verdicts}, "heldout": {run: verdicts}}."""
    from specdrift.eval.compare import arm_report, paired_difference
    from specdrift.eval.heldout import score_heldout

    result: dict = {"baseline": baseline, "arms": {}, "paired": {}, "heldout": {}, "notes": []}
    for name, data in arm_data.items():
        report = arm_report(cases, data["sets"], name, n_boot=n_boot, seed=seed)
        report["fake"] = data["fake"]
        report["detector"] = data["detector"]
        result["arms"][name] = report
        if data["heldout"]:
            held = score_heldout(expected, data["heldout"], name, n_boot=n_boot, seed=seed)
            held["fake"] = data["fake"]
            result["heldout"][name] = held
        if data.get("planned_runs") == 1:
            result["notes"].append(f"{name}: 1 run by design (greedy decoding is deterministic); the CI covers case sampling "
                                   "only, not training-seed variation")
        elif len(data["sets"]) < 3:
            result["notes"].append(f"{name}: {len(data['sets'])} run(s) of the 86 cases; the plan is 3, so run-to-run spread is thin")
    if baseline in arm_data:
        for name, data in arm_data.items():
            if name != baseline:
                result["paired"][name] = paired_difference(cases, data["sets"], arm_data[baseline]["sets"],
                                                           n_boot=n_boot, seed=seed)
    else:
        result["notes"].append(f"baseline {baseline!r} has no results, so no paired differences were computed")
    return result


def paired_reading(difference: dict) -> str:
    """A plain statement of what the interval says; deliberately not a verdict on H1."""
    low, high = difference["ci95"] or (None, None)
    if low is None:
        return "undefined"
    if high < 0:
        return "lower (interval excludes 0)"
    if low > 0:
        return "higher (interval excludes 0)"
    return "no detectable difference (interval includes 0)"


def render_markdown(comparison: dict) -> str:
    arms, base = comparison["arms"], comparison["baseline"]
    label = {n: f"{n}{' (FAKE offline stand-in)' if a['fake'] else ''}" for n, a in arms.items()}
    lines = ["# Detector comparison", "",
             "Mean over runs with bootstrap 95% CI over cases (pooled across runs). DRIFT is the positive class.", "",
             "## 86 frozen cases", "",
             "| arm | runs | recall | precision | strict precision | false-alarm rate | UNCERTAIN rate | ECE |",
             "|---|---:|---|---|---|---|---|---|"]
    for name, a in arms.items():
        o, e = a["stability"]["overall"], a["extra"]
        lines.append(f"| {label[name]} | {len(a['runs'])} | {fmt(o['recall']['mean'], o['recall']['ci95'])} "
                     f"| {fmt(o['precision']['mean'], o['precision']['ci95'])} "
                     f"| {fmt(e['strict_precision']['mean'], e['strict_precision']['ci95'])} "
                     f"| {fmt(o['false_alarm_rate']['mean'], o['false_alarm_rate']['ci95'])} "
                     f"| {fmt(e['uncertain_rate']['mean'], e['uncertain_rate']['ci95'])} "
                     f"| {fmt(a['calibration']['ece'], a['calibration'].get('ece_ci95'))} |")

    if comparison["paired"]:
        lines += ["", f"## Paired difference against `{base}` (arm minus baseline, same cases)", "",
                  "| arm | false-alarm rate | reading | recall | reading |", "|---|---|---|---|---|"]
        for name, d in comparison["paired"].items():
            fa, rc = d["false_alarm_rate"], d["recall"]
            lines.append(f"| {label[name]} | {fa['difference']:+.2f} {fa['ci95'] or ''} | {paired_reading(fa)} "
                         f"| {rc['difference']:+.2f} {rc['ci95'] or ''} | {paired_reading(rc)} |")
        lines += ["", "H1 asks for a lower false-alarm rate at equal or better recall. These rows state what each interval "
                      "shows; they are not a significance test of H1.", ""]

    categories = sorted({c for a in arms.values() for c in a["stability"]["per_category"]})
    lines += ["", "## Per category (drift: recall, control: false-alarm rate)", "",
              "| category | n | " + " | ".join(label[n] for n in arms) + " |", "|---|---:|" + "---|" * len(arms)]
    for cat in categories:
        first = next(a["stability"]["per_category"][cat] for a in arms.values() if cat in a["stability"]["per_category"])
        cells = [fmt(a["stability"]["per_category"][cat]["mean"], a["stability"]["per_category"][cat]["ci95"])
                 if cat in a["stability"]["per_category"] else "n/a" for a in arms.values()]
        lines.append(f"| {cat} ({first['metric']}) | {first['n']} | " + " | ".join(cells) + " |")

    lines += ["", "## Abstention: coverage against accuracy", "",
              "Raise the confidence threshold and an answer below it becomes an abstention. Per (case, rule) pair; "
              "recall and false-alarm rate are against all pairs. Full curves are in comparison.json.", ""]
    for name, a in arms.items():
        curve = a["abstention"]["curve"]
        picked = [curve[round(i * (len(curve) - 1) / 5)] for i in range(6)] if len(curve) > 6 else curve
        lines += [f"**{label[name]}** ({a['abstention']['pairs']} pairs)", "",
                  "| threshold | coverage | accuracy | recall | false-alarm rate |", "|---:|---:|---:|---:|---:|"]
        lines += [f"| {r['threshold']:.2f} | {r['coverage']:.2f} | {fmt(r['accuracy'])} | {fmt(r['recall'])} "
                  f"| {fmt(r['false_alarm_rate'])} |" for r in picked]
        lines.append("")

    if comparison["heldout"]:
        lines += ["## Unseen projects (test-2), per rule", "",
                  "| arm | runs | recall | precision | false-alarm rate | UNCERTAIN rate | ECE |", "|---|---:|---|---|---|---|---|"]
        for name, h in comparison["heldout"].items():
            o = h["overall"]
            lines.append(f"| {label[name]} | {len(h['runs'])} | {fmt(o['recall']['mean'], o['recall']['ci95'])} "
                         f"| {fmt(o['precision']['mean'], o['precision']['ci95'])} "
                         f"| {fmt(o['false_alarm_rate']['mean'], o['false_alarm_rate']['ci95'])} "
                         f"| {fmt(h['uncertain_rate']['mean'], h['uncertain_rate']['ci95'])} "
                         f"| {fmt(h['calibration']['ece'])} |")
        any_h = next(iter(comparison["heldout"].values()))
        lines += ["", f"Scored projects: {', '.join(any_h['projects'])} ({any_h['rules']} rules, {any_h['drift_rules']} drifted)."]

    lines += ["", "## Read this before quoting a number", "",
              "- The curve and ECE use a per-pair truth (DRIFT only for the rules an injection targeted); a non-target rule of "
              "a drifted file may really be broken, which makes those numbers slightly pessimistic. D8 and reverse verdicts are left out.",
              "- Confidence is taken to be confidence in the stated verdict; the prompt does not define it further.",
              "- Test-2 ground truth is the authors' claim in examples/expected.json with no oracle test, covers 3 of the 4 projects, "
              "and has few rules, so its intervals are wide.",
              "- HumanEval, MBPP and QuixBugs are likely in the pretraining data of the Qwen base models (training-data-spec, section 4)."]
    lines += [f"- {note}" for note in comparison["notes"]]
    return "\n".join(lines) + "\n"


def load_arm_data(arm: dict, out: Path) -> dict | None:
    """Verdicts of every stored run for one arm, or None when it has not been run."""
    from specdrift.config import Settings
    from specdrift.eval.heldout import available_heldout_runs, load_heldout
    from specdrift.runner import available_runs, load_verdicts

    settings = Settings(results_dir=arm_results_dir(arm, out))
    runs = available_runs(settings, arm["detector"])
    if not runs:
        return None
    stats = settings.detector_dir(arm["detector"]) / "run.json"
    model = json.loads(stats.read_text(encoding="utf-8")).get("model", "") if stats.exists() else ""
    held_runs = available_heldout_runs(settings, arm["detector"]) if arm["detector"] == "specguard" else []
    return {
        "detector": arm["detector"],
        "planned_runs": arm.get("runs"),
        "fake": model == "fake",
        "sets": {run: load_verdicts(settings, arm["detector"], run) for run in runs},
        "heldout": {run: load_heldout(settings, arm["detector"], run) for run in held_runs},
    }


def cmd_run(args) -> int:
    arms, _ = load_arms(Path(args.arms))
    if args.arm:
        missing = sorted(set(args.arm) - {a["name"] for a in arms})
        if missing:
            print(f"no such arm: {', '.join(missing)}", file=sys.stderr)
            return 1
        arms = [a for a in arms if a["name"] in args.arm]
    out = Path(args.out)
    steps = plan(arms, out, args.runs, not args.skip_heldout)

    for step in steps:
        if "skip" in step:
            print(f"- {step['arm']}: skipped, {step['skip']}")
            continue
        overrides = ", ".join(f"{k}={v}" for k, v in step["env"].items()) or "none"
        print(f"- {step['arm']}: overrides {overrides}; results -> {step['results']}")
        for command in step["commands"]:
            print("    " + " ".join(command[2:]))
    if not args.execute:
        print("\nplan only. Add --execute to run it (spends API money for openai/anthropic arms, GPU time for huggingface arms).")
        return 0

    if not (REPO_ROOT / "cases" / "built.jsonl").exists():
        print("no built cases; run `specdrift build` first", file=sys.stderr)
        return 1
    by_name = {a["name"]: a for a in arms}
    for step in steps:
        if "skip" in step:
            continue
        for command in step["commands"]:
            code = subprocess.run(command, cwd=REPO_ROOT, env=env_for(by_name[step["arm"]], out)).returncode
            if code != 0:
                print(f"{step['arm']}: `{' '.join(command[2:])}` exited {code}; stopping", file=sys.stderr)
                return code
    return 0


def cmd_report(args) -> int:
    from specdrift.bench.pipeline import load_built
    from specdrift.config import Settings
    from specdrift.eval.heldout import load_expected

    arms, baseline = load_arms(Path(args.arms))
    out = Path(args.out)
    cases = load_built(Settings())
    if not cases:
        print("no built cases; run `specdrift build` first", file=sys.stderr)
        return 1
    data, absent = {}, []
    for arm in arms:
        loaded = load_arm_data(arm, out)
        (data.__setitem__(arm["name"], loaded) if loaded else absent.append(arm["name"]))
    if not data:
        print("no arm has results yet; run `compare_models.py run --execute` first", file=sys.stderr)
        return 1

    comparison = build_comparison(cases, load_expected(), data, baseline, args.boot, args.seed)
    if absent:
        comparison["notes"].append(f"no results yet for: {', '.join(absent)}")
    out.mkdir(parents=True, exist_ok=True)
    (out / "comparison.json").write_text(json.dumps(comparison, indent=1), encoding="utf-8")
    (out / "comparison.md").write_text(render_markdown(comparison), encoding="utf-8")
    print(f"wrote {out / 'comparison.md'} and comparison.json ({len(data)} arm(s); no results for: {', '.join(absent) or 'none'})")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="plan (default) or execute every arm")
    run.add_argument("--arms", required=True)
    run.add_argument("--out", required=True)
    run.add_argument("--runs", type=int, default=3)
    run.add_argument("--arm", action="append", default=[], help="Only this arm (repeatable).")
    run.add_argument("--skip-heldout", action="store_true")
    run.add_argument("--execute", action="store_true")
    run.set_defaults(fn=cmd_run)
    report = sub.add_parser("report", help="score what is on disk and write comparison.md/json")
    report.add_argument("--arms", required=True)
    report.add_argument("--out", required=True)
    report.add_argument("--boot", type=int, default=2000)
    report.add_argument("--seed", type=int, default=0)
    report.set_defaults(fn=cmd_report)
    args = parser.parse_args(argv)
    try:
        return args.fn(args)
    except ArmError as exc:
        print(f"arms file: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())

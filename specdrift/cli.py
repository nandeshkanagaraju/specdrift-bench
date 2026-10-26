"""specdrift - build the benchmark, run detectors over it, score them, report."""

from __future__ import annotations

import typer

from specdrift.config import get_settings

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="SpecDrift-Bench: measure how reliably a detector notices specification drift.",
)


@app.callback()
def main() -> None:
    """SpecDrift-Bench command line."""


@app.command()
def build(
    project: str = typer.Option(None, help="Build only this project's cases."),
    case: str = typer.Option(None, help="Build only cases whose id contains this."),
) -> None:
    """Materialise every case, validate it, and write cases/built.jsonl."""
    from specdrift.bench.pipeline import build_all, summarise

    settings = get_settings()
    typer.echo("building cases...")
    results = build_all(settings, project=project, case_id=case)
    if not results:
        typer.echo("no cases matched")
        raise typer.Exit(code=1)
    typer.echo(summarise(results))

    invalid_negatives = [r for r in results if r.status == "invalid" and r.label == "no_drift"]
    if invalid_negatives:
        raise typer.Exit(code=1)


@app.command()
def run(
    detector: str = typer.Option("specguard", help="specguard | keyword | wholefile"),
    project: str = typer.Option(None, help="Only this project's cases."),
    limit: int = typer.Option(0, help="Stop after this many cases (0 = all)."),
    run_index: int = typer.Option(1, "--run", help="Run number; >1 bypasses the cache."),
    repeat: int = typer.Option(1, "--repeat", min=1, help="Run this many consecutive runs from --run."),
) -> None:
    """Run a detector over every built case and write its verdicts."""
    import time

    from specdrift.bench.pipeline import load_built
    from specdrift.runner import run_detector

    settings = get_settings()
    cases = load_built(settings)
    if not cases:
        typer.echo("no built cases; run `specdrift build` first")
        raise typer.Exit(code=1)

    if project:
        cases = [case for case in cases if case.project == project]
    if limit:
        cases = cases[:limit]

    if detector in {"specguard", "wholefile"} and settings.llm_provider == "fake":
        typer.secho(
            "note: LLM_PROVIDER=fake - the offline stand-in is answering, not a model. "
            "Set LLM_PROVIDER and LLM_API_KEY in .env for model results.",
            fg=typer.colors.YELLOW,
        )

    if repeat > 1 and run_index + repeat - 1 > 1:
        typer.echo("note: runs after #1 bypass the cache, so each one makes fresh LLM calls.")

    for current in range(run_index, run_index + repeat):
        started = time.perf_counter()
        typer.echo(f"running {detector} (run {current}) over {len(cases)} cases...")
        _, stats = run_detector(detector, cases, settings, run=current)
        elapsed = time.perf_counter() - started

        typer.echo(
            f"{stats['verdicts']} verdicts from {stats['cases']} cases  |  "
            f"model={stats['model']}  LLM calls={stats['llm_calls']}  "
            f"cache hits={stats['cache_hits']}  |  {elapsed:.1f}s"
        )


@app.command()
def oracles() -> None:
    """Check every escaping drift case against its oracle test (pass pristine, fail drifted)."""
    import json
    from collections import Counter

    from specdrift.bench.oracle import check_oracle, needs_oracle
    from specdrift.bench.pipeline import load_built

    settings = get_settings()
    cases = [case for case in load_built(settings) if needs_oracle(case)]
    if not cases:
        typer.echo("no escaping drift cases; run `specdrift build` first")
        raise typer.Exit(code=1)

    report = {case.case_id: check_oracle(case, settings) for case in cases}
    for case_id, row in report.items():
        typer.echo(f"{case_id:<22} {row['status']:<20} {row['detail'][:70]}")

    tally = Counter(row["status"] for row in report.values())
    typer.echo("")
    typer.echo("  ".join(f"{status} {count}" for status, count in sorted(tally.items())))

    out = settings.results_dir / "oracles.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    if set(tally) - {"confirmed", "waived"}:
        raise typer.Exit(code=1)


@app.command()
def stability(
    detector: str = typer.Option("specguard", help="Detector to analyse."),
    boot: int = typer.Option(2000, help="Bootstrap resamples."),
) -> None:
    """Mean, run-to-run spread and bootstrap 95% CIs over every stored run."""
    import json

    from specdrift.bench.pipeline import load_built
    from specdrift.eval.stability import format_stability, score_runs
    from specdrift.runner import available_runs, load_verdicts

    settings = get_settings()
    cases = load_built(settings)
    if not cases:
        typer.echo("no built cases; run `specdrift build` first")
        raise typer.Exit(code=1)

    runs = available_runs(settings, detector)
    if not runs:
        typer.echo(f"no verdicts for {detector}; run `specdrift run --detector {detector}` first")
        raise typer.Exit(code=1)

    verdict_sets = {run: load_verdicts(settings, detector, run) for run in runs}
    report = score_runs(cases, verdict_sets, detector, n_boot=boot)
    out = settings.detector_dir(detector) / "stability.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    typer.echo(format_stability(report))


@app.command()
def score(
    detector: str = typer.Option("specguard", help="Detector to score, or 'all'."),
) -> None:
    """Join verdicts with labels and write metrics.json plus per_category.csv."""
    from specdrift.bench.pipeline import load_built
    from specdrift.eval.metrics import format_scores, write_scores
    from specdrift.eval.metrics import score as score_detector
    from specdrift.registry import DETECTOR_NAMES
    from specdrift.runner import load_verdicts

    settings = get_settings()
    cases = load_built(settings)
    if not cases:
        typer.echo("no built cases; run `specdrift build` first")
        raise typer.Exit(code=1)

    names = DETECTOR_NAMES if detector == "all" else (detector,)
    for name in names:
        verdicts = load_verdicts(settings, name)
        if not verdicts:
            typer.echo(f"no verdicts for {name}; run `specdrift run --detector {name}` first")
            continue
        report = score_detector(cases, verdicts, name)
        write_scores(report, settings)
        typer.echo(format_scores(report))
        typer.echo("")


@app.command()
def report() -> None:
    """Render results/report.html and results/report.md for every scored detector."""
    from specdrift.bench.pipeline import load_built
    from specdrift.eval.report import build_report, render
    from specdrift.registry import DETECTOR_NAMES
    from specdrift.runner import load_verdicts

    settings = get_settings()
    cases = load_built(settings)
    if not cases:
        typer.echo("no built cases; run `specdrift build` first")
        raise typer.Exit(code=1)

    verdicts = {name: load_verdicts(settings, name) for name in DETECTOR_NAMES}
    context = build_report(settings, cases, verdicts)
    if not context["detectors"]:
        typer.echo("nothing scored yet; run `specdrift score --detector all` first")
        raise typer.Exit(code=1)

    html_path, md_path = render(context, settings)
    typer.echo(f"wrote {html_path}")
    typer.echo(f"wrote {md_path}")


@app.command()
def check(
    project_dir: str = typer.Argument(..., help="A directory holding spec.md and src/."),
    diff_from: str = typer.Option(None, "--diff-from", help="Only check files changed since this git ref."),
) -> None:
    """Check a project against its own spec now. Exits 1 if any rule has drifted."""
    from pathlib import Path as _Path

    from specdrift.live import check_project, rule_texts

    settings = get_settings()
    target = _Path(project_dir).resolve()
    if not (target / "spec.md").exists():
        typer.secho(f"no spec.md in {target}", fg=typer.colors.RED)
        raise typer.Exit(code=2)

    verdicts, summary = check_project(target, settings, diff_from)
    texts = rule_texts(target)

    colours = {
        "DRIFT": typer.colors.RED,
        "COMPLIANT": typer.colors.GREEN,
        "UNCERTAIN": typer.colors.YELLOW,
    }

    typer.echo(f"{target.name}: {summary['rules']} rules, {summary['chunks']} chunks, "
               f"model={summary['model']}")
    if summary["scope_note"]:
        typer.secho(f"  {summary['scope_note']}", fg=typer.colors.BRIGHT_BLACK)
    typer.echo("")
    typer.echo(f"{'rule':<6} {'verdict':<11} {'conf':>5}  {'evidence':<34} rule text")
    typer.echo("-" * 100)

    for verdict in verdicts:
        where = ""
        if verdict.evidence.file:
            where = f"{verdict.evidence.file}:{verdict.evidence.start_line}-{verdict.evidence.end_line}"
        elif verdict.retrieved_chunks:
            where = verdict.retrieved_chunks[0]
        text = texts.get(verdict.rule_id, "")
        typer.echo(
            f"{verdict.rule_id:<6} "
            + typer.style(f"{verdict.verdict:<11}", fg=colours[verdict.verdict])
            + f" {verdict.confidence:>5.2f}  {where[:34]:<34} {text[:44]}"
        )

    counts = summary["counts"]
    typer.echo("")
    banner = {
        "PASS": (typer.colors.GREEN, "PASS - every rule is implemented as written"),
        "DRIFT": (typer.colors.RED, f"DRIFT - {counts['DRIFT']} rule(s) no longer match the spec"),
        "NEEDS_HUMAN": (typer.colors.YELLOW, f"NEEDS HUMAN - {counts['UNCERTAIN']} rule(s) could not be decided"),
    }[summary["status"]]
    typer.secho(banner[1], fg=banner[0], bold=True)

    if counts["DRIFT"]:
        raise typer.Exit(code=1)


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", help="Interface to bind."),
    port: int = typer.Option(8000, help="Port to bind."),
    reload: bool = typer.Option(False, help="Reload on code changes (development)."),
) -> None:
    """Serve the dashboard API, and the built web app when web/dist exists."""
    import uvicorn

    uvicorn.run("specdrift.api.app:app", host=host, port=port, reload=reload)


@app.command("retrieval-eval")
def retrieval_eval(
    json_out: bool = typer.Option(False, "--json", help="Print the raw report instead."),
) -> None:
    """Stage 1 only: Recall@1/3/5 of the gold chunk for every drift case."""
    import json as _json

    from specdrift.bench.pipeline import load_built
    from specdrift.retrieval.evaluate import evaluate_retrieval, format_retrieval_report

    settings = get_settings()
    results = load_built(settings)
    if not results:
        typer.echo("no built cases; run `specdrift build` first")
        raise typer.Exit(code=1)

    report = evaluate_retrieval(results, settings)
    settings.results_dir.mkdir(parents=True, exist_ok=True)
    (settings.results_dir / "retrieval.json").write_text(_json.dumps(report, indent=2))

    typer.echo(_json.dumps(report, indent=2) if json_out else format_retrieval_report(report))


def _leak_paths(settings):
    from specdrift.config import REPO_ROOT

    return settings.cases_dir, settings.projects_dir, REPO_ROOT / "examples", REPO_ROOT / "data" / "test_manifest.json"


@app.command("data-freeze")
def data_freeze(
    force: bool = typer.Option(False, "--force", help="Overwrite a manifest that no longer matches."),
) -> None:
    """Freeze the test set (86 cases, host projects, examples/) into data/test_manifest.json."""
    from specdrift.data.leakage import ManifestMismatch, collect_test_material, freeze

    cases_dir, projects_dir, examples_dir, manifest = _leak_paths(get_settings())
    material = collect_test_material(cases_dir, projects_dir, examples_dir)
    try:
        frozen = freeze(material, manifest, force=force)
    except ManifestMismatch as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=1) from exc
    typer.echo(
        f"frozen {len(frozen['cases'])} cases, {len(frozen['projects'])} projects, "
        f"{len(frozen['chunk_hashes'])} chunks, {len(frozen['rules'])} rules"
    )
    typer.echo(f"fingerprint {frozen['fingerprint']}")


@app.command("data-check")
def data_check(
    data: list[str] = typer.Argument(..., help="Training JSONL file(s), e.g. data/stage_a.jsonl."),
    max_ngram: float = typer.Option(0.9, help="Fail if a test chunk is this covered by training n-grams."),
    report_path: str = typer.Option("", "--report", help="Also write the full report as JSON."),
) -> None:
    """Fail if any training example overlaps the frozen test set. Run before every training upload."""
    import json as _json
    from pathlib import Path

    from specdrift.data.leakage import (
        ManifestMismatch,
        collect_test_material,
        format_report,
        load_examples,
        run_checks,
        verify_frozen,
    )

    cases_dir, projects_dir, examples_dir, manifest = _leak_paths(get_settings())
    material = collect_test_material(cases_dir, projects_dir, examples_dir)
    try:
        frozen = verify_frozen(material, manifest)
    except ManifestMismatch as exc:
        typer.echo(f"cannot check: {exc}")
        raise typer.Exit(code=1) from exc

    examples = load_examples(Path(p) for p in data)
    report = run_checks(examples, material, ngram_fail=max_ngram)
    typer.echo(format_report(report, frozen))
    if report_path:
        Path(report_path).write_text(_json.dumps(report.as_dict(), indent=1))
    if not report.ok:
        raise typer.Exit(code=1)


@app.command("data-inject")
def data_inject(
    project: str = typer.Argument(..., help="A Python project with src/ and tests/ that passes its own tests."),
    name: str = typer.Option("", help="Short project name for mutant ids (default: the directory name)."),
    out: str = typer.Option("", help="Output JSONL (default: data/mutants/<name>.jsonl)."),
    subdir: str = typer.Option("src", help="Where the source lives inside the project."),
    file: list[str] = typer.Option([], "--file", help="Only mutate files whose path ends with this (repeatable)."),
    focus_rules: str = typer.Option("", "--focus-rules", help="Rules JSON (prompt A's answer): mutate only the "
                                    "lines its rules cite, with every operator and no sampling cap."),
    benign: bool = typer.Option(False, "--benign", help="Generate N2 refactors and N3 decoys (no drift) instead."),
    per_operator: int = typer.Option(6, help="At most this many mutants per operator."),
    seed: int = typer.Option(17, help="Seed; the same seed gives the same mutants."),
    timeout: float = typer.Option(60.0, help="Seconds allowed per test run."),
    sandbox: str = typer.Option("auto", help="auto | require | off. Third-party tests need `require`."),
) -> None:
    """Inject drift into a project and label each mutant by running its tests (Stage B, part 1)."""
    from pathlib import Path

    from specdrift.config import REPO_ROOT
    from specdrift.data.inject import ProjectBroken, inject_project, write_mutants

    if sandbox not in ("auto", "require", "off"):
        typer.echo("--sandbox must be auto, require or off")
        raise typer.Exit(code=1)
    settings = get_settings()
    root = Path(project).expanduser()
    label = name or root.resolve().name
    target = Path(out) if out else Path("data/mutants") / f"{label}.jsonl"
    focus: dict[str, list[str]] | None = None
    if focus_rules:
        import json as _json

        focus = {}
        for item in _json.loads(Path(focus_rules).read_text(encoding="utf-8")).get("rules", []):
            ev = item.get("evidence") or {}
            focus.setdefault(str(ev.get("file", "")), []).append(str(ev.get("quote", "")))
    try:
        mutants, stats = inject_project(
            root, label, subdir=subdir, only=tuple(file), focus=focus, benign=benign, per_operator=per_operator, seed=seed, timeout=timeout,
            sandbox=sandbox,  # type: ignore[arg-type]
            protected_roots=[settings.projects_dir, REPO_ROOT / "examples"],
        )
    except (ValueError, ProjectBroken, RuntimeError) as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=1) from exc
    write_mutants(mutants, stats, target if target.is_absolute() else REPO_ROOT / target)
    typer.echo(f"{stats['mutants']} mutants  {stats['by_status']}")
    typer.echo(f"killed by category  {stats['killed_by_category']}")
    if not stats["sandboxed"]:
        typer.secho("warning: tests ran WITHOUT a sandbox (network and writes were not blocked)", fg=typer.colors.YELLOW)


@app.command("data-assemble")
def data_assemble(
    project: str = typer.Argument(..., help="Project with spec.md, src/ and the oracle tests."),
    mutants: str = typer.Option(..., help="JSONL written by `specdrift data-inject` for this project."),
    rule_map: str = typer.Option("", help="rules.yaml (default: <project>/rules.yaml)."),
    subdir: str = typer.Option("src", help="Where the library source lives (e.g. `voluptuous` for a flat layout)."),
    name: str = typer.Option("", help="Project name (default: the directory name)."),
    split: str = typer.Option("train", help="train | val. A whole project goes to one split."),
    out: str = typer.Option("", help="Output JSONL (default: data/stage_b_<name>.jsonl)."),
    seed: int = typer.Option(17),
    top_k: int = typer.Option(3, help="Chunks Stage 1 retrieves per rule."),
    gold_view: float = typer.Option(0.2, help="Share of examples that show only the gold chunk."),
    abstain: float = typer.Option(0.1, help="Share of examples that also get an UNCERTAIN twin."),
    gold_on_miss: bool = typer.Option(True, "--gold-on-miss/--no-gold-on-miss",
                                      help="When retrieval misses a violated rule's code, also emit a DRIFT example "
                                           "that shows it."),
    timeout: float = typer.Option(60.0),
    sandbox: str = typer.Option("auto", help="auto | require | off."),
) -> None:
    """Turn mutants into labelled training examples, judged by per-rule oracle tests (Stage B, part 2)."""
    import json as _json
    from pathlib import Path

    from specdrift.config import REPO_ROOT
    from specdrift.data.assemble import assemble_project
    from specdrift.data.inject import Mutant

    if split not in ("train", "val") or sandbox not in ("auto", "require", "off"):
        typer.echo("--split must be train or val; --sandbox must be auto, require or off")
        raise typer.Exit(code=1)
    settings = get_settings()
    root = Path(project).expanduser()
    label = name or root.resolve().name
    try:
        rows = [Mutant.model_validate_json(line) for line in Path(mutants).read_text().splitlines() if line.strip()]
    except (OSError, ValueError) as exc:
        typer.echo(f"cannot read the mutants file {mutants}: {exc}")
        raise typer.Exit(code=1) from exc
    try:
        examples, summary = assemble_project(
            root, label, rows, Path(rule_map) if rule_map else root / "rules.yaml", subdir=subdir, split=split, seed=seed,
            top_k=top_k, gold_view=gold_view, abstain=abstain, gold_on_miss=gold_on_miss, timeout=timeout,
            sandbox=sandbox,  # type: ignore[arg-type]
            protected_roots=[settings.projects_dir, REPO_ROOT / "examples"],
        )
    except (ValueError, RuntimeError, FileNotFoundError) as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=1) from exc
    target = Path(out) if out else Path("data") / f"stage_b_{label}.jsonl"
    target = target if target.is_absolute() else REPO_ROOT / target
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("".join(e.model_dump_json() + "\n" for e in examples), encoding="utf-8")
    target.with_suffix(".stats.json").write_text(_json.dumps(summary, indent=2) + "\n")
    typer.echo(f"{summary['examples']} examples written to {target}")
    for key, count in summary["counts"].items():
        typer.echo(f"  {key:<40}{count}")
    for rule_id, reason in summary["rules_excluded"].items():
        typer.echo(f"  rule {rule_id} excluded: {reason}")
    if summary["oracles_that_kill_nothing"]:
        typer.secho(f"  oracles that failed on no mutant: {', '.join(summary['oracles_that_kill_nothing'])}",
                    fg=typer.colors.YELLOW)
    if summary["rejected_by_validator"]:
        typer.secho(f"  {len(summary['rejected_by_validator'])} example(s) rejected by the validator", fg=typer.colors.YELLOW)


@app.command("data-rulegen-prompt")
def data_rulegen_prompt(
    project: str = typer.Argument(..., help="Project directory with the library source."),
    out: str = typer.Option(..., help="Write the user prompt here; the system prompt goes beside it (.system.txt)."),
    name: str = typer.Option("", help="Library name (default: the directory name)."),
    subdir: str = typer.Option("src", help="Where the library source lives."),
) -> None:
    """Build prompt A (rule extraction) for a project. Makes no model call."""
    from pathlib import Path

    from specdrift.data.rulegen import RULE_PROMPT_VERSION, build_rule_prompt

    root = Path(project).expanduser()
    system, user = build_rule_prompt(root, name or root.resolve().name, subdir)
    target = Path(out)
    target.write_text(user, encoding="utf-8")
    target.with_suffix(".system.txt").write_text(system, encoding="utf-8")
    typer.echo(f"prompt {RULE_PROMPT_VERSION}: {len(user):,} characters (about {len(user) // 4:,} tokens) -> {target}")


@app.command("data-rulegen-render")
def data_rulegen_render(
    project: str = typer.Argument(...),
    rules_json: str = typer.Option(..., "--rules", help="The model's JSON answer to prompt A."),
    name: str = typer.Option("", help="Library name (default: the directory name)."),
    subdir: str = typer.Option("src"),
) -> None:
    """Lint the extracted rules, then write spec.md and rules.yaml for the ones that survive."""
    from pathlib import Path

    from specdrift.data.rulegen import lint_rules, parse_rules_json, write_rules

    root = Path(project).expanduser()
    try:
        rules = parse_rules_json(Path(rules_json).read_text(encoding="utf-8"))
    except (ValueError, OSError) as exc:
        typer.echo(f"cannot read the rules: {exc}")
        raise typer.Exit(code=1) from exc
    result = lint_rules(rules, root, subdir)
    typer.echo(f"{len(rules)} rules from the model: {len(result.kept)} kept, {len(result.dropped)} dropped")
    for rule, reason in result.dropped:
        typer.echo(f"  dropped: {reason}  |  {str(rule.get('text', ''))[:90]}")
    for rule, reason in result.warnings:
        typer.secho(f"  warning: {reason}  |  {str(rule.get('text', ''))[:90]}", fg=typer.colors.YELLOW)
    if not result.usable:
        typer.echo("too few rules survive; this repo is rejected")
        raise typer.Exit(code=1)
    ids = write_rules(root, result.kept, name or root.resolve().name)
    typer.echo(f"wrote spec.md and rules.yaml with {', '.join(ids)}; oracles go in oracles/test_rNN.py")


@app.command("data-oracle-prompt")
def data_oracle_prompt(
    project: str = typer.Argument(...),
    rule: str = typer.Option(..., help="Rule id, e.g. R03."),
    out: str = typer.Option(..., help="Write the user prompt here; the system prompt goes beside it (.system.txt)."),
    subdir: str = typer.Option("src"),
) -> None:
    """Build prompt B (write one oracle) for one rule. Makes no model call."""
    from pathlib import Path

    import yaml

    from specdrift.data.rulegen import build_oracle_prompt
    from specdrift.spec.parser import load_project_rules

    root = Path(project).expanduser()
    rules = {r.id: r for r in load_project_rules(root)}
    mapping = yaml.safe_load((root / "rules.yaml").read_text(encoding="utf-8"))
    if rule not in rules or rule not in mapping:
        typer.echo(f"{rule} is not in spec.md and rules.yaml")
        raise typer.Exit(code=1)
    system, user = build_oracle_prompt(root, rule, rules[rule].text, mapping[rule]["symbols"], subdir)
    Path(out).write_text(user, encoding="utf-8")
    Path(out).with_suffix(".system.txt").write_text(system, encoding="utf-8")
    typer.echo(f"{len(user):,} characters -> {out}")


@app.command("data-oracle-check")
def data_oracle_check(
    project: str = typer.Argument(...),
    subdir: str = typer.Option("src"),
) -> None:
    """Static gate on every oracle named in rules.yaml (no code is run)."""
    from pathlib import Path

    import yaml

    from specdrift.data.rulegen import check_oracle_source, library_names

    root = Path(project).expanduser()
    mapping = yaml.safe_load((root / "rules.yaml").read_text(encoding="utf-8")) or {}
    library = library_names(root, subdir)
    failed = 0
    for rule_id, entry in mapping.items():
        for rel in entry["oracle"]:
            path = root / rel
            problems = check_oracle_source(path.read_text(encoding="utf-8"), library) if path.is_file() else ["missing"]
            failed += bool(problems)
            typer.echo(f"{'FAIL' if problems else 'ok  '} {rule_id} {rel}" + "".join(f"\n       {p}" for p in problems))
    if failed:
        raise typer.Exit(code=1)


@app.command("data-mix")
def data_mix(
    inputs: list[str] = typer.Argument(..., help="Training JSONL files to mix (Stage A and Stage B)."),
    out: str = typer.Option("data/mix/latest", help="Directory for train.jsonl, val.jsonl and mix.json."),
    seed: int = typer.Option(17),
    paper_share: float = typer.Option(0.3, help="Share of the mix taken from Stage A (0 = none, for the H3 ablation)."),
    max_per_rule: int = typer.Option(6, help="At most this many examples per (project, rule, label)."),
    max_group_share: float = typer.Option(0.6, help="No project (or Stage A dataset) may supply more than this share "
                                                    "of a label; the mix shrinks to honour it."),
    val_fraction: float = typer.Option(0.2, help="Share of Stage B projects held out for validation."),
    val_project: list[str] = typer.Option([], "--val-project", help="Hold this Stage B project out (repeatable)."),
    exclude_source: list[str] = typer.Option([], "--exclude-source", help="paper | synth | hardneg (repeatable)."),
    exclude_operator: list[str] = typer.Option([], "--exclude-operator", help="Drop examples made by this mutation or "
                                               "refactor operator (repeatable), e.g. to hold a family out."),
    drift: float = typer.Option(0.35, help="Target share of DRIFT."),
    uncertain: float = typer.Option(0.10, help="Target share of UNCERTAIN; COMPLIANT takes the rest."),
    total: int = typer.Option(0, help="Cap the size of each split (0 = as large as the pools allow)."),
) -> None:
    """Balance the pools into train and validation files, check them against the frozen test set, then write."""
    import json as _json
    from pathlib import Path

    from specdrift.config import REPO_ROOT
    from specdrift.data.leakage import (
        ManifestMismatch,
        collect_test_material,
        load_examples,
        run_checks,
        verify_frozen,
    )
    from specdrift.data.mix import MixConfig, mix, write_mix

    if not 0 < drift < 1 or not 0 <= uncertain < 1 or drift + uncertain >= 1:
        typer.echo("--drift and --uncertain must leave room for COMPLIANT")
        raise typer.Exit(code=1)
    paths = [Path(p).expanduser() for p in inputs]
    try:
        cfg = MixConfig(
            seed=seed, shares={"DRIFT": drift, "COMPLIANT": round(1 - drift - uncertain, 6), "UNCERTAIN": uncertain},
            paper_share=paper_share, max_per_rule=max_per_rule, max_group_share=max_group_share,
            val_fraction=val_fraction,
            val_projects=tuple(val_project), exclude_sources=tuple(exclude_source),
            exclude_operators=tuple(exclude_operator), total=total)
        examples = load_examples(paths)
        mixed, summary = mix(examples, cfg)
    except (ValueError, OSError) as exc:
        typer.echo(f"cannot mix: {exc}")
        raise typer.Exit(code=1) from exc

    settings = get_settings()
    material = collect_test_material(settings.cases_dir, settings.projects_dir, REPO_ROOT / "examples")
    try:
        verify_frozen(material, REPO_ROOT / "data" / "test_manifest.json")
    except ManifestMismatch as exc:
        typer.echo(f"cannot check for leakage, nothing written: {exc}")
        raise typer.Exit(code=1) from exc
    report = run_checks(mixed["train"] + mixed["val"], material)
    if not report.ok:
        typer.echo(f"the mix overlaps the frozen test set ({len(report.findings)} violation(s)); nothing written")
        for finding in report.findings[:10]:
            typer.echo(f"  [{finding.check}] {finding.example_id}: {finding.detail}")
        raise typer.Exit(code=1)

    target = Path(out)
    write_mix(mixed, summary, target if target.is_absolute() else REPO_ROOT / target, paths)
    for split, info in summary["splits"].items():
        shares = ", ".join(f"{k} {v:.0%}" for k, v in sorted(info["label_shares"].items()))
        typer.echo(f"{split:<6}{info['examples']:>6} examples   {shares}   limited by: {info['binding_label']}")
    typer.echo(f"validation projects: {summary['val_projects'] or 'none (Stage A only)'}")
    typer.echo(f"leakage check: clean. wrote {target}/train.jsonl, val.jsonl, mix.json")
    if summary["skipped"]:
        typer.echo(f"skipped on the way in: {_json.dumps(summary['skipped'])}")


@app.command("data-sft")
def data_sft(
    mix_dir: str = typer.Argument(..., help="A directory written by `data-mix` (train.jsonl, val.jsonl)."),
    out: str = typer.Option("", help="Where to write train.jsonl, val.jsonl and sft.json (default: <mix_dir>/sft)."),
) -> None:
    """Export a mix as exact prompt/completion records for fine-tuning (docs/training-data-spec.md, section 9)."""
    import json as _json
    from pathlib import Path

    from specdrift.config import REPO_ROOT
    from specdrift.data.leakage import (
        ManifestMismatch,
        collect_test_material,
        load_examples,
        run_checks,
        verify_frozen,
    )
    from specdrift.data.sft import export, summarise, write_sft

    source = Path(mix_dir).expanduser()
    source = source if source.is_absolute() else REPO_ROOT / source
    try:
        pools = {split: load_examples([source / f"{split}.jsonl"]) for split in ("train", "val")}
    except (ValueError, OSError) as exc:
        typer.echo(f"cannot read the mix: {exc}")
        raise typer.Exit(code=1) from exc

    settings = get_settings()
    material = collect_test_material(settings.cases_dir, settings.projects_dir, REPO_ROOT / "examples")
    try:
        verify_frozen(material, REPO_ROOT / "data" / "test_manifest.json")
    except ManifestMismatch as exc:
        typer.echo(f"cannot check for leakage, nothing written: {exc}")
        raise typer.Exit(code=1) from exc
    report = run_checks(pools["train"] + pools["val"], material)
    if not report.ok:
        typer.echo(f"the mix overlaps the frozen test set ({len(report.findings)} violation(s)); nothing written")
        raise typer.Exit(code=1)

    target = Path(out).expanduser() if out else source / "sft"
    target = target if target.is_absolute() else REPO_ROOT / target
    summary: dict = {}
    for split, examples in pools.items():
        records, refused = export(examples)
        write_sft(records, target / f"{split}.jsonl")
        summary[split] = summarise(records) | {"refused": len(refused)}
        typer.echo(f"{split:<6}{len(records):>6} records   {summary[split]['labels']}   refused: {len(refused)}")
        for example_id, reason in refused[:5]:
            typer.echo(f"  refused {example_id}: {reason}")
    (target / "sft.json").write_text(_json.dumps(summary, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    typer.echo(f"wrote {target}")
    if any(info["refused"] for info in summary.values()):
        raise typer.Exit(code=1)


@app.command("data-stage-a")
def data_stage_a(
    src: str = typer.Option(..., help="Checkout of the Jin & Chen repo (has dataset/humaneval/...)."),
    out: str = typer.Option("data/stage_a.jsonl", help="Where to write the training examples."),
    execute: bool = typer.Option(True, "--execute/--no-execute", help="Run each task's tests to verify labels."),
    limit: int = typer.Option(0, help="Per dataset, stop after this many tasks (0 = all)."),
) -> None:
    """Build Stage A training examples from the paper's paired data (docs/training-data-spec.md)."""
    from pathlib import Path

    from specdrift.config import REPO_ROOT
    from specdrift.data.stage_a import convert

    source = Path(src).expanduser()
    if not (source / "dataset").is_dir():
        typer.echo(f"{source} has no dataset/ directory")
        raise typer.Exit(code=1)
    target = Path(out)
    stats = convert(source, target if target.is_absolute() else REPO_ROOT / target, execute=execute, limit=limit)
    typer.echo(f"tasks   {dict(stats.tasks)}")
    typer.echo(f"written {dict(sorted(stats.written.items()))}")
    for reason, count in stats.dropped.most_common():
        typer.echo(f"dropped {count:>4}  {reason}")


if __name__ == "__main__":
    app()

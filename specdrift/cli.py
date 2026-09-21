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

    started = time.perf_counter()
    typer.echo(f"running {detector} over {len(cases)} cases...")
    _, stats = run_detector(detector, cases, settings, run=run_index)
    elapsed = time.perf_counter() - started

    typer.echo(
        f"{stats['verdicts']} verdicts from {stats['cases']} cases  |  "
        f"model={stats['model']}  LLM calls={stats['llm_calls']}  "
        f"cache hits={stats['cache_hits']}  |  {elapsed:.1f}s"
    )


@app.command()
def score(
    detector: str = typer.Option("specguard", help="Detector to score, or 'all'."),
) -> None:
    """Join verdicts with labels and write metrics.json plus per_category.csv."""
    from specdrift.bench.pipeline import load_built
    from specdrift.eval.metrics import format_scores, score as score_detector, write_scores
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


if __name__ == "__main__":
    app()

"""Live mode: check a working directory against its own spec, right now."""

from __future__ import annotations

import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

from specdrift.bench.schema import CaseResult, Verdict
from specdrift.config import Settings
from specdrift.verify.engine import SpecGuard

# (event name, payload) -- payload is a plain dict, or a Verdict for "verdict".
Progress = Callable[[str, Any], None]


def changed_files(project_dir: Path, ref: str) -> list[str] | None:
    """Paths changed since a git ref, or None when that cannot be determined."""
    try:
        proc = subprocess.run(
            ["git", "diff", "--name-only", ref, "--", "."],
            cwd=project_dir,
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None

    if proc.returncode != 0:
        return None
    return [line.strip() for line in proc.stdout.splitlines() if line.strip().endswith(".py")]


def check_project(
    project_dir: Path,
    settings: Settings,
    diff_from: str | None = None,
    progress: Progress | None = None,
) -> tuple[list[Verdict], dict]:
    """Check a workspace rule by rule.

    `progress` is called as the run happens, so a caller streaming to a UI can show
    each stage finishing and each rule resolving instead of one silent wait. It is
    optional: the CLI and the tests pass nothing and the behaviour is unchanged.
    """
    emit = progress or (lambda event, payload: None)

    # The steps are emitted separately, rather than through SpecGuard.analyse, so a
    # caller streaming to a UI can time and name each one. The work is identical.
    emit("stage", {"stage": "setup", "state": "running"})
    detector = SpecGuard(settings)
    emit(
        "stage",
        {
            "stage": "setup",
            "state": "done",
            "detail": f"{detector.model} \u00b7 {settings.embed_backend} embedder",
        },
    )

    emit("stage", {"stage": "spec", "state": "running"})
    from specdrift.spec.parser import load_project_rules

    rules = load_project_rules(project_dir)
    emit("stage", {"stage": "spec", "state": "done", "detail": f"{len(rules)} numbered rules"})

    emit("stage", {"stage": "chunk", "state": "running"})
    from specdrift.code.chunker import chunk_workspace

    chunks = chunk_workspace(project_dir)
    n_files = len({chunk.file for chunk in chunks})
    emit(
        "stage",
        {"stage": "chunk", "state": "done", "detail": f"{len(chunks)} chunks from {n_files} files"},
    )

    scope_note = ""
    if diff_from:
        changed = changed_files(project_dir, diff_from)
        if changed is None:
            scope_note = f"could not diff against {diff_from}; checking everything"
        elif not changed:
            scope_note = f"no Python files changed since {diff_from}; checking everything"
        else:
            relative = {
                path.split("/", 1)[-1] if path.startswith(f"{project_dir.name}/") else path
                for path in changed
            }
            narrowed = [c for c in chunks if c.file in relative or c.file in changed]
            if narrowed:
                chunks = narrowed
                scope_note = f"{len(relative)} file(s) changed since {diff_from}"

    from specdrift.retrieval.retriever import add_constant_context, retrieve

    emit("stage", {"stage": "rank", "state": "running"})
    ranked = retrieve(rules, chunks, detector.embedder, k=settings.top_k)
    by_id = {chunk.id: chunk for chunk in chunks}
    emit(
        "stage",
        {
            "stage": "rank",
            "state": "done",
            "detail": f"top {settings.top_k} of {len(chunks)} chunks per rule",
        },
    )

    emit("stage", {"stage": "verify", "state": "running", "total": len(rules)})
    verdicts: list[Verdict] = []
    for rule in rules:
        emit("rule_start", {"rule_id": rule.id, "text": rule.text})

        top = [by_id[hit.chunk_id] for hit in ranked[rule.id] if hit.chunk_id in by_id]
        retrieved = len(top)
        top = add_constant_context(top, chunks)

        from specdrift.verify.verifier import verify_rule

        verdict = verify_rule(rule, top, detector.llm, detector.cache, "live", detector.name)
        verdicts.append(verdict)
        emit("verdict", verdict)
        emit(
            "rule_detail",
            {
                "rule_id": rule.id,
                "retrieved": retrieved,
                "constant_context": len(top) - retrieved,
            },
        )

    emit(
        "stage",
        {"stage": "verify", "state": "done", "detail": f"{len(rules)} of {len(rules)} checked"},
    )

    downgraded = sum(1 for v in verdicts if v.downgraded)
    accepted = sum(1 for v in verdicts if v.verdict == "DRIFT")
    emit("stage", {"stage": "gate", "state": "running"})
    emit(
        "stage",
        {
            "stage": "gate",
            "state": "done",
            "detail": f"{accepted} drift accepted, {downgraded} downgraded for want of proof",
        },
    )

    counts = {
        "DRIFT": sum(1 for v in verdicts if v.verdict == "DRIFT"),
        "COMPLIANT": sum(1 for v in verdicts if v.verdict == "COMPLIANT"),
        "UNCERTAIN": sum(1 for v in verdicts if v.verdict == "UNCERTAIN"),
    }
    status = "DRIFT" if counts["DRIFT"] else ("NEEDS_HUMAN" if counts["UNCERTAIN"] else "PASS")

    return verdicts, {
        "status": status,
        "counts": counts,
        "rules": len(rules),
        "chunks": len(chunks),
        "model": detector.model,
        "scope_note": scope_note,
    }


def rule_texts(project_dir: Path) -> dict[str, str]:
    from specdrift.spec.parser import load_project_rules

    return {rule.id: rule.text for rule in load_project_rules(project_dir)}


def sweep_cases(settings: Settings) -> list[CaseResult]:
    """One representative drift case per category D1..D9.

    Picked by sorting on case id and taking the first valid case of each category, so
    the same nine cases come back every run and nobody can accuse the demo of having
    hand-picked its wins.
    """
    from specdrift.bench.pipeline import load_built
    from specdrift.bench.schema import DRIFT_CATEGORIES

    chosen: dict[str, CaseResult] = {}
    for case in sorted(load_built(settings), key=lambda c: c.case_id):
        if case.status != "valid" or not case.is_drift or case.category is None:
            continue
        chosen.setdefault(case.category, case)

    return [chosen[category] for category in DRIFT_CATEGORIES if category in chosen]


def run_sweep(
    cases: list[CaseResult],
    settings: Settings,
    progress: Progress | None = None,
) -> list[dict]:
    """Check each case for the rule its injection targeted, category by category.

    Stage 1 ranks against the full rule set, exactly as the scored pipeline does, so
    the retrieval a rule gets here is the retrieval it gets there. Only verification is
    narrowed to the target rules, which is what makes nine categories affordable in one
    click. A D8 case names no rule -- nothing authorises the added behaviour -- so for
    those every rule is verified and any drift flag counts.
    """
    from specdrift.retrieval.retriever import add_constant_context, retrieve
    from specdrift.verify.verifier import verify_rule

    emit = progress or (lambda event, payload: None)
    detector = SpecGuard(settings)          # built once and reused across all nine
    out: list[dict] = []

    for case in cases:
        workspace = Path(case.workspace) if case.workspace else settings.work_dir / case.case_id
        emit("case_start", {"case_id": case.case_id, "category": case.category})

        rules, chunks = detector.analyse(workspace)
        ranked = retrieve(rules, chunks, detector.embedder, k=settings.top_k)
        by_id = {chunk.id: chunk for chunk in chunks}

        wanted = set(case.target_rules) or {rule.id for rule in rules}
        flagged: list[str] = []
        checked = 0

        for rule in rules:
            if rule.id not in wanted:
                continue
            top = [by_id[hit.chunk_id] for hit in ranked[rule.id] if hit.chunk_id in by_id]
            top = add_constant_context(top, chunks)
            verdict = verify_rule(
                rule, top, detector.llm, detector.cache, case.case_id, detector.name
            )
            checked += 1
            if verdict.verdict == "DRIFT":
                flagged.append(rule.id)

        row = {
            "case_id": case.case_id,
            "category": case.category,
            "project": case.project,
            "caught": bool(flagged),
            "flagged_rules": flagged,
            "target_rules": case.target_rules,
            "rules_checked": checked,
            "escapes_tests": case.escapes_tests,
        }
        out.append(row)
        emit("case_result", row)

    return out

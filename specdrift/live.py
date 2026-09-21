"""Live mode: check a working directory against its own spec, right now."""

from __future__ import annotations

import subprocess
from pathlib import Path

from specdrift.bench.schema import Verdict
from specdrift.config import Settings
from specdrift.verify.engine import SpecGuard


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
) -> tuple[list[Verdict], dict]:
    detector = SpecGuard(settings)
    rules, chunks = detector.analyse(project_dir)

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

    ranked = retrieve(rules, chunks, detector.embedder, k=settings.top_k)
    by_id = {chunk.id: chunk for chunk in chunks}

    verdicts: list[Verdict] = []
    for rule in rules:
        top = [by_id[hit.chunk_id] for hit in ranked[rule.id] if hit.chunk_id in by_id]
        top = add_constant_context(top, chunks)
        from specdrift.verify.verifier import verify_rule

        verdicts.append(
            verify_rule(rule, top, detector.llm, detector.cache, "live", detector.name)
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

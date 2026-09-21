"""Recall@k for Stage 1, measured against the gold symbol in each case manifest."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from specdrift.bench.schema import ALL_CATEGORIES, CATEGORY_NAMES, CaseResult
from specdrift.code.chunker import chunk_workspace
from specdrift.config import Settings
from specdrift.retrieval.embedder import build_embedder
from specdrift.retrieval.retriever import recall_at_k, retrieve
from specdrift.spec.parser import load_project_rules, rules_by_id

KS = (1, 3, 5)


def evaluate_retrieval(
    results: list[CaseResult],
    settings: Settings,
    ks: tuple[int, ...] = KS,
) -> dict:
    """For every drift case with a gold symbol, was that chunk in the top k?"""
    embedder = build_embedder(settings.embed_backend, settings.embed_model, settings.cache_dir)
    max_k = max(ks)

    overall: dict[int, list[bool]] = {k: [] for k in ks}
    per_category: dict[str, dict[int, list[bool]]] = defaultdict(
        lambda: {k: [] for k in ks}
    )
    misses: list[tuple[str, str, str]] = []

    for result in results:
        if result.status != "valid" or not result.is_drift or not result.gold_symbol:
            continue
        if not result.target_rules or not result.workspace:
            continue

        workspace = Path(result.workspace)
        if not workspace.exists():
            continue

        chunks = chunk_workspace(workspace)
        rules = load_project_rules(workspace)
        by_id = rules_by_id(rules)
        wanted = [by_id[rid] for rid in result.target_rules if rid in by_id]
        if not wanted:
            continue

        ranked = retrieve(wanted, chunks, embedder, k=max_k)
        for rule in wanted:
            hits = ranked[rule.id]
            for k in ks:
                found = recall_at_k(hits, result.gold_symbol, k)
                overall[k].append(found)
                if result.category:
                    per_category[result.category][k].append(found)
            if not recall_at_k(hits, result.gold_symbol, max_k):
                misses.append((result.case_id, rule.id, result.gold_symbol))

    def rate(flags: list[bool]) -> float:
        return round(sum(flags) / len(flags), 4) if flags else 0.0

    return {
        "embedder": embedder.name,
        "n_rule_queries": len(overall[ks[0]]),
        "overall": {f"recall@{k}": rate(overall[k]) for k in ks},
        "per_category": {
            cat: {
                "n": len(per_category[cat][ks[0]]),
                **{f"recall@{k}": rate(per_category[cat][k]) for k in ks},
            }
            for cat in ALL_CATEGORIES
            if cat in per_category
        },
        "misses": [
            {"case_id": case, "rule_id": rule, "gold_symbol": gold}
            for case, rule, gold in misses
        ],
    }


def format_retrieval_report(report: dict, ks: tuple[int, ...] = KS) -> str:
    header = f"{'cat':<4} {'name':<30} {'n':>3} " + " ".join(f"{'R@' + str(k):>6}" for k in ks)
    lines = [f"embedder: {report['embedder']}", "", header, "-" * len(header)]

    for cat, row in report["per_category"].items():
        cells = " ".join(f"{row[f'recall@{k}']:>6.2f}" for k in ks)
        lines.append(f"{cat:<4} {CATEGORY_NAMES[cat]:<30} {row['n']:>3} {cells}")

    overall = report["overall"]
    cells = " ".join(f"{overall[f'recall@{k}']:>6.2f}" for k in ks)
    lines += [
        "-" * len(header),
        f"{'all':<4} {'':<30} {report['n_rule_queries']:>3} {cells}",
    ]

    if report["misses"]:
        lines += ["", f"{len(report['misses'])} rule queries missed the gold chunk:"]
        for miss in report["misses"][:15]:
            lines.append(f"  {miss['case_id']:<24} {miss['rule_id']:<5} wanted {miss['gold_symbol']}")
        if len(report["misses"]) > 15:
            lines.append(f"  ... and {len(report['misses']) - 15} more")

    return "\n".join(lines)

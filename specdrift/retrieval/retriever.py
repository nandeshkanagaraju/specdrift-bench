"""Stage 1 - rank code chunks against one rule by cosine similarity."""

from __future__ import annotations

import re
from dataclasses import dataclass

import numpy as np

from specdrift.bench.schema import Chunk, Rule
from specdrift.retrieval.embedder import Embedder


@dataclass(frozen=True)
class Hit:
    chunk_id: str
    score: float


def chunk_document(chunk: Chunk) -> str:
    """What gets embedded for a chunk: where it lives, what it is called, what it does."""
    location = chunk.file.replace("/", " ").replace(".py", "")
    return f"{location} {chunk.qualname}\n{chunk.source}"


def rule_document(rule: Rule) -> str:
    return f"{rule.section} {rule.text}" if rule.section else rule.text


def retrieve(
    rules: list[Rule],
    chunks: list[Chunk],
    embedder: Embedder,
    k: int = 3,
) -> dict[str, list[Hit]]:
    """Return the top-k chunks for every rule. Ties are broken by chunk id."""
    if not rules or not chunks:
        return {rule.id: [] for rule in rules}

    chunk_docs = [chunk_document(chunk) for chunk in chunks]
    rule_docs = [rule_document(rule) for rule in rules]

    embedder.fit(chunk_docs + rule_docs)
    chunk_vectors = embedder.encode(chunk_docs)
    rule_vectors = embedder.encode(rule_docs)

    # Both sides are L2 normalised, so the dot product is the cosine similarity.
    similarity = rule_vectors @ chunk_vectors.T

    ranked: dict[str, list[Hit]] = {}
    for row, rule in enumerate(rules):
        scores = similarity[row]
        # Sort by score descending, then chunk id ascending, so runs are reproducible.
        order = sorted(
            range(len(chunks)),
            key=lambda index: (-float(scores[index]), chunks[index].id),
        )
        ranked[rule.id] = [
            Hit(chunk_id=chunks[index].id, score=round(float(scores[index]), 6))
            for index in order[:k]
        ]

    return ranked


def chunks_by_id(chunks: list[Chunk]) -> dict[str, Chunk]:
    return {chunk.id: chunk for chunk in chunks}


def matches_gold(chunk_id: str, gold_symbol: str) -> bool:
    """A hit counts as gold when its qualified name is the one the manifest named."""
    if not gold_symbol:
        return False
    return chunk_id.split("::", 1)[-1] == gold_symbol


def recall_at_k(hits: list[Hit], gold_symbol: str, k: int) -> bool:
    return any(matches_gold(hit.chunk_id, gold_symbol) for hit in hits[:k])


def as_array(values: list[float]) -> np.ndarray:
    return np.asarray(values, dtype=np.float32)


_CONSTANT_RE = re.compile(r"\b[A-Z][A-Z0-9_]{2,}\b")


def add_constant_context(
    top: list[Chunk],
    all_chunks: list[Chunk],
    max_extra: int = 2,
) -> list[Chunk]:
    """Append the module chunk that defines a constant the retrieved code relies on.

    Without this, a rule like "the loan period MUST be 14 days" is judged against
    ``day + LOAN_PERIOD_DAYS`` with the value of LOAN_PERIOD_DAYS nowhere in view, and
    a detector that says DRIFT is not wrong so much as under-informed. Resolving the
    constant is part of showing the right code, so it belongs in Stage 1.
    """
    if not top:
        return top

    present = {chunk.id for chunk in top}
    modules = {
        chunk.file: chunk
        for chunk in all_chunks
        if chunk.qualname == "<module>" and chunk.id not in present
    }
    if not modules:
        return top

    extra: list[Chunk] = []
    for chunk in top:
        module = modules.get(chunk.file)
        if module is None or module in extra:
            continue
        referenced = set(_CONSTANT_RE.findall(chunk.source))
        defined = {
            name
            for name in _CONSTANT_RE.findall(module.source)
            if re.search(rf"^{name}\s*[:=]", module.source, re.MULTILINE)
        }
        if referenced & defined:
            extra.append(module)
        if len(extra) >= max_extra:
            break

    return top + extra

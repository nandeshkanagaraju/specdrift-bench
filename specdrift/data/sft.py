"""Turn a mix into the exact prompt/completion text the fine-tuned model is trained on.

The prompt is what `verify/prompts.py` builds at serve time (`SYSTEM_PROMPT` plus
`build_user_prompt`), never a re-implementation of it. The completion is the target as compact
JSON with the keys in the order the system prompt lists them. A record is refused if its own
completion, read back through the production parser and evidence bar, does not give the verdict
it is labelled with: that would teach the model something the scorer rejects.

Three files per split, so metadata can never leak into what the model sees:

* ``<split>.chat.jsonl``  {"example_id", "messages": [system, user, assistant]}
* ``<split>.jsonl``       {"example_id", "system", "prompt", "completion"}   (plain text)
* ``<split>.index.jsonl`` {"example_id", "split", "project_id", "source", "label", "category", ...}

LOSS MUST BE COMPUTED ON THE COMPLETION (the assistant message) ONLY.
"""

from __future__ import annotations

import json
import statistics
from collections import Counter
from pathlib import Path

from specdrift.data.schema import Target, TrainingExample
from specdrift.data.validate import CHARS_PER_TOKEN, MAX_TOKENS
from specdrift.verify.prompts import PROMPT_VERSION, SYSTEM_PROMPT, build_user_prompt
from specdrift.verify.verifier import parse_response, to_verdict

KEY_ORDER = ("verdict", "confidence", "violated_clause", "evidence", "counterexample")
LOSS_NOTE = "Compute loss on the completion (assistant message) only; the prompt tokens are context."
TOKEN_METHOD = (
    f"estimate: characters / {CHARS_PER_TOKEN} over system + user + completion; no tokenizer was available "
    "offline, and the chat template adds roughly 10 to 20 tokens per example on top"
)


def completion_text(target: Target) -> str:
    """The model's answer, as the JSON the system prompt asks for."""
    data = target.model_dump(mode="json")
    ordered = {key: data[key] for key in KEY_ORDER}
    return json.dumps(ordered, ensure_ascii=False, separators=(", ", ": "))


def check_round_trip(example: TrainingExample, completion: str) -> str | None:
    """Return a reason if the production parser would not read this completion as its label."""
    payload = parse_response(completion)
    if payload is None:
        return "completion is not parseable JSON"
    verdict = to_verdict(payload, example.example_id, example.rule.id, "sft")
    if verdict.downgraded:
        return "a DRIFT target would be downgraded by the evidence bar"
    if verdict.verdict != example.label:
        return f"parsed as {verdict.verdict}, labelled {example.label}"
    return None


def user_prompt(example: TrainingExample) -> str:
    return build_user_prompt(example.rule, example.chunks)


def estimate_tokens(example: TrainingExample, completion: str) -> int:
    chars = len(SYSTEM_PROMPT) + len(user_prompt(example)) + len(completion)
    return int(chars / CHARS_PER_TOKEN) + 1


def to_records(example: TrainingExample) -> tuple[dict, dict, dict]:
    """(chat record, plain record, index record) for one example."""
    completion = completion_text(example.target)
    user = user_prompt(example)
    chat = {
        "example_id": example.example_id,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user},
            {"role": "assistant", "content": completion},
        ],
    }
    plain = {"example_id": example.example_id, "system": SYSTEM_PROMPT, "prompt": user, "completion": completion}
    index = {
        "example_id": example.example_id,
        "split": example.split,
        "project_id": example.project_id,
        "source": example.source,
        "label": example.label,
        "category": example.category,
        "operator": example.provenance.notes.get("operator", ""),
        "prompt_version": PROMPT_VERSION,
        "approx_tokens": estimate_tokens(example, completion),
    }
    return chat, plain, index


def export(examples: list[TrainingExample]) -> tuple[list[tuple[dict, dict, dict]], list[tuple[str, str]]]:
    """Records for every example that round-trips, and (example_id, reason) for the rest."""
    kept: list[tuple[dict, dict, dict]] = []
    refused: list[tuple[str, str]] = []
    for example in examples:
        reason = check_round_trip(example, completion_text(example.target))
        if reason:
            refused.append((example.example_id, reason))
        else:
            kept.append(to_records(example))
    return kept, refused


def _write(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")


def write_sft(kept: list[tuple[dict, dict, dict]], directory: Path, split: str) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    _write(directory / f"{split}.chat.jsonl", [c for c, _, _ in kept])
    _write(directory / f"{split}.jsonl", [p for _, p, _ in kept])
    _write(directory / f"{split}.index.jsonl", [i for _, _, i in kept])


def summarise(kept: list[tuple[dict, dict, dict]], refused: int) -> dict:
    index = [i for _, _, i in kept]
    tokens = sorted(i["approx_tokens"] for i in index)
    over = sum(1 for t in tokens if t > MAX_TOKENS)
    return {
        "examples": len(index),
        "refused": refused,
        "labels": dict(Counter(i["label"] for i in index)),
        "categories": dict(sorted(Counter(i["category"] for i in index).items())),
        "sources": dict(Counter(i["source"] for i in index)),
        "approx_tokens": {
            "mean": round(statistics.fmean(tokens), 1) if tokens else 0,
            "median": tokens[len(tokens) // 2] if tokens else 0,
            "p95": tokens[int(len(tokens) * 0.95)] if tokens else 0,
            "max": tokens[-1] if tokens else 0,
        },
        "over_limit": {"limit": MAX_TOKENS, "count": over, "share": round(over / len(tokens), 4) if tokens else 0},
    }

"""Turn a mix into the exact prompt/completion text the fine-tuned model is trained on.

The prompt is what `verify/prompts.py` builds at serve time (`SYSTEM_PROMPT` plus
`build_user_prompt`), so training and inference cannot drift apart. The completion is the
target as compact JSON with the keys in the order the system prompt lists them. A record is
refused if its own completion, read back through the production parser, does not give the
verdict it is labelled with: that would teach the model something the scorer rejects.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from specdrift.data.schema import Target, TrainingExample
from specdrift.verify.prompts import PROMPT_VERSION, SYSTEM_PROMPT, build_user_prompt
from specdrift.verify.verifier import parse_response, to_verdict

KEY_ORDER = ("verdict", "confidence", "violated_clause", "evidence", "counterexample")


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


def to_record(example: TrainingExample) -> dict:
    """One JSONL record: chat-style prompt and completion, plus what an audit needs."""
    completion = completion_text(example.target)
    return {
        "example_id": example.example_id,
        "split": example.split,
        "project_id": example.project_id,
        "source": example.source,
        "label": example.label,
        "category": example.category,
        "prompt_version": PROMPT_VERSION,
        "prompt": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": build_user_prompt(example.rule, example.chunks)},
        ],
        "completion": [{"role": "assistant", "content": completion}],
    }


def export(examples: list[TrainingExample]) -> tuple[list[dict], list[tuple[str, str]]]:
    """Records for every example that round-trips, and (example_id, reason) for the rest."""
    records: list[dict] = []
    refused: list[tuple[str, str]] = []
    for example in examples:
        reason = check_round_trip(example, completion_text(example.target))
        if reason:
            refused.append((example.example_id, reason))
        else:
            records.append(to_record(example))
    return records, refused


def write_sft(records: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records), encoding="utf-8")


def summarise(records: list[dict]) -> dict:
    return {
        "examples": len(records),
        "labels": dict(Counter(r["label"] for r in records)),
        "prompt_version": PROMPT_VERSION,
    }

"""The invariants every training example must satisfy (docs/training-data-spec.md, section 8)."""

from __future__ import annotations

import json
import re

from specdrift.data.schema import TrainingExample
from specdrift.verify.prompts import SYSTEM_PROMPT, build_user_prompt

# Raised from 1,536 to 2,048 after iniconfig and tomli (142 examples of 1,540 to 2,650 tokens were being discarded), then to
# 3,072 after flashtext and xmltodict: their 130-170 line core functions (`extract_keywords`, `replace_keywords`, `parse`,
# `_emit`) give examples of about 3,000 tokens, so a lower cap removed exactly the algorithmic rules. 3,072 recovers 121 of
# the 196 examples lost at 2,048. It is sized for a 1.5B QLoRA run on a T4 with gradient checkpointing; a 7B run must pass a
# smaller --max-len and will drop the long ones at train time.
MAX_TOKENS = 3072
CHARS_PER_TOKEN = 3.5       # a rough, deliberately pessimistic estimate; no tokenizer is needed here
_SECRET_RE = re.compile(r"sk-[A-Za-z0-9_-]{20,}|AKIA[0-9A-Z]{16}|-----BEGIN [A-Z ]*PRIVATE KEY-----")


def shown_end(chunk) -> int:
    """The last line number the prompt shows for this chunk (`render_chunk` counts from start_line)."""
    return chunk.start_line + len(chunk.source.splitlines()) - 1


def approx_tokens(example: TrainingExample) -> int:
    prompt = SYSTEM_PROMPT + build_user_prompt(example.rule, example.chunks)
    target = json.dumps(example.target.model_dump())
    return int((len(prompt) + len(target)) / CHARS_PER_TOKEN)


def problems(example: TrainingExample) -> list[str]:
    """Everything wrong with one example; an empty list means it may be trained on."""
    found: list[str] = []
    target = example.target

    if example.label != target.verdict:
        found.append(f"label {example.label} does not match target verdict {target.verdict}")
    if example.label != "UNCERTAIN" and not example.chunks:
        found.append("no code is shown")
    for chunk in example.chunks:
        lines, span = len(chunk.source.splitlines()), chunk.end_line - chunk.start_line + 1
        # The chunker trims trailing blank lines, which leaves the numbering intact. Only the module chunk has
        # interior gaps: it joins the top-level statements and drops what lies between them.
        trimmed = 0 <= span - lines <= 2
        if lines > span or not (trimmed or (chunk.qualname == "<module>" and lines < span)):
            found.append(f"chunk {chunk.id} spans {span} lines but holds {lines}")

    clause, evidence, cx = target.violated_clause, target.evidence, target.counterexample
    if target.verdict == "DRIFT":
        if not clause:
            found.append("DRIFT without a violated clause")
        elif clause not in example.rule.text:
            found.append("violated clause is not a verbatim part of the rule")
        if not cx.input or not (cx.expected or cx.actual):
            found.append("DRIFT without a usable counterexample")
        inside = [
            c for c in example.chunks
            if c.file == evidence.file and c.start_line <= evidence.start_line <= evidence.end_line <= shown_end(c)
        ]
        if evidence.start_line < 1 or not inside:
            found.append("evidence lines are not inside any shown chunk")
    elif clause or evidence.file or evidence.start_line or cx.input or cx.expected or cx.actual:
        found.append(f"{target.verdict} must carry no clause, evidence or counterexample")

    if approx_tokens(example) > MAX_TOKENS:
        found.append(f"about {approx_tokens(example)} tokens, over the {MAX_TOKENS} limit")
    blob = example.rule.text + "".join(c.source for c in example.chunks)
    if _SECRET_RE.search(blob):
        found.append("looks like it contains a secret")
    return found

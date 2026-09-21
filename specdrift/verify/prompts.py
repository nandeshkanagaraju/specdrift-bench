"""The Stage 2 prompt. Bump PROMPT_VERSION whenever the wording changes.

The wording follows three findings from Jin & Chen (ASE 2026) on false rejection in
conformance judgement:

* asking the model to propose a fix raised false rejection sharply, so it never does;
* most false rejections were unsupported "logic error" claims, so a DRIFT verdict must
  quote the clause it breaks and give a concrete counterexample;
* a possible risk is not a violation, and is stated as such.
"""

from __future__ import annotations

from specdrift.bench.schema import Chunk, Rule

PROMPT_VERSION = "v1"

SYSTEM_PROMPT = """You check whether code implements ONE specification rule. You do not \
review style, performance, or anything the rule does not state. Do not suggest fixes.

Decide:
- DRIFT only if you can quote the exact rule clause violated AND give a concrete input
  where the code's behaviour differs from what the rule requires.
- COMPLIANT if the code implements the rule, even if it could be written differently.
- UNCERTAIN if the excerpts do not contain enough to decide.

A possible risk is not a violation. Comments and docstrings are claims, not behaviour;
judge only executable code.

Return JSON only, with exactly these keys:
{"verdict": "COMPLIANT" | "DRIFT" | "UNCERTAIN",
 "confidence": 0.0-1.0,
 "violated_clause": "",
 "evidence": {"file": "", "start_line": 0, "end_line": 0},
 "counterexample": {"input": "", "expected": "", "actual": ""}}"""


def render_chunk(chunk: Chunk) -> str:
    """Show a chunk with its real line numbers, so evidence spans can be checked."""
    numbered = "\n".join(
        f"{line_no:>4} | {line}"
        for line_no, line in enumerate(chunk.source.splitlines(), start=chunk.start_line)
    )
    return f"--- {chunk.file} ({chunk.qualname}) ---\n{numbered}"


def build_user_prompt(rule: Rule, chunks: list[Chunk]) -> str:
    body = "\n\n".join(render_chunk(chunk) for chunk in chunks) or "(no code retrieved)"
    return (
        f"RULE {rule.id}: {rule.text}\n\n"
        f"CODE (only these excerpts are relevant):\n{body}\n"
    )

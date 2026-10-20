"""Ablation: hide the rule ids that the host projects carry in their own comments.

The host projects annotate code with the rule it implements (a ``# R12`` comment, or an ``R09 -`` docstring prefix).
Real code does not, and the annotation hands a retriever and a model the answer. This
module makes a copy of a case's workspace with those ids removed while keeping the
explanatory words, so a detector can be scored with and without the hint. The originals
are never touched: case patches match the annotated text exactly.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

from specdrift.bench.schema import CaseResult
from specdrift.config import Settings

_ID = r"R\d{2}"
_IDS = rf"{_ID}(?:\s*(?:/|,\s*and|,|and|to)\s*{_ID})*"

# Order matters: whole-comment ids go first, then prefixes and prose references.
_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(rf"[ \t]+#\s*{_IDS}[ \t]*$", re.M), ""),                   # X = 3   # R06
    (re.compile(rf"\s*Enforces\s+{_IDS}(?:\s+on\s+[^.\n]*)?\.", re.M), ""),  # Enforces R04 to R12.
    (re.compile(rf"{_IDS}\s+[-–—]\s+"), ""),                      # R04/R05 - add ...
    (re.compile(rf"\s+from\s+{_IDS}"), ""),                                 # fee from R13
    (re.compile(rf"\b{_IDS}\b"), ""),                                       # anything left
]

LEFTOVER = re.compile(rf"\b{_ID}\b")


def strip_rule_ids(text: str) -> str:
    for pattern, replacement in _PATTERNS:
        text = pattern.sub(replacement, text)
    # An emptied comment or docstring is noise, so tidy what the removal left behind.
    text = re.sub(r'""" +', '"""', text)
    text = re.sub(r"^([ \t]*)#[ \t]*$", "", text, flags=re.M)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text


def stripped_workspace(case: CaseResult, settings: Settings) -> CaseResult:
    """Return `case` pointing at a copy of its workspace with rule ids removed from src/."""
    source = Path(case.workspace)
    target = settings.work_dir / "stripped" / case.case_id
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(source, target, ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache"))

    src = target / "src"
    for path in (src if src.exists() else target).rglob("*.py"):
        path.write_text(strip_rule_ids(path.read_text(encoding="utf-8")), encoding="utf-8")
    return case.model_copy(update={"workspace": str(target)})

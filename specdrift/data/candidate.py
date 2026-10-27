"""One proposed edit to a source file, shared by the drift and the benign generators."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Candidate:
    category: str
    operator: str
    line: int                     # 1-based first line of the edit
    end_line: int
    new_lines: list[str]          # replacement for lines[line-1:end_line]
    description: str

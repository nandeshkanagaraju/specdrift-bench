"""Every data structure that crosses a module boundary lives here."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

Category = Literal[
    "D1", "D2", "D3", "D4", "D5", "D6", "D7", "D8", "D9",  # drift
    "N1", "N2", "N3",                                        # negative controls
]
Label = Literal["drift", "no_drift"]
VerdictValue = Literal["COMPLIANT", "DRIFT", "UNCERTAIN"]

DRIFT_CATEGORIES: tuple[str, ...] = ("D1", "D2", "D3", "D4", "D5", "D6", "D7", "D8", "D9")
NEGATIVE_CATEGORIES: tuple[str, ...] = ("N1", "N2", "N3")
ALL_CATEGORIES: tuple[str, ...] = DRIFT_CATEGORIES + NEGATIVE_CATEGORIES

CATEGORY_NAMES: dict[str, str] = {
    "D1": "Boundary shift",
    "D2": "Value / constant drift",
    "D3": "Omitted check",
    "D4": "Weakened condition",
    "D5": "Sequence violation",
    "D6": "Error-handling drift",
    "D7": "Comment decoy",
    "D8": "Unauthorised scope creep",
    "D9": "Output contract drift",
    "N1": "Unchanged code",
    "N2": "Semantics-preserving refactor",
    "N3": "Benign decoy",
}


class Rule(BaseModel):
    """One atomic, numbered requirement parsed out of a project's spec.md."""

    id: str
    text: str
    section: str = ""


class Chunk(BaseModel):
    """A retrievable unit of source: a function, a method, or a class header."""

    id: str                 # "<relative path>::<qualname>"
    file: str
    qualname: str
    start_line: int
    end_line: int
    source: str


class CaseSpec(BaseModel):
    """One benchmark case: a patch to apply to a host project, plus its label."""

    id: str
    project: str
    category: Category
    label: Label
    target_rules: list[str] = Field(default_factory=list)
    file: str = ""
    find: str = ""
    replace: str = ""
    gold_symbol: str = ""
    note: str = ""

    @field_validator("target_rules", mode="before")
    @classmethod
    def _none_to_empty(cls, v: object) -> object:
        return [] if v is None else v

    @field_validator("find", "replace", mode="before")
    @classmethod
    def _join_lines(cls, v: object) -> object:
        """A patch may be written as a list of lines.

        YAML block scalars strip the common leading indentation, which would silently
        break an exact match against indented Python. A list of quoted lines keeps
        every space the author typed.
        """
        if isinstance(v, list):
            return "\n".join("" if line is None else str(line) for line in v)
        return "" if v is None else v

    @property
    def is_drift(self) -> bool:
        return self.label == "drift"

    def case_id_matches(self, needle: str) -> bool:
        """Exact id, or a substring so `--case D7-01` is enough to name one case."""
        return self.id == needle or needle in self.id


class CaseResult(BaseModel):
    """What the builder and validator learned about one case."""

    case_id: str
    project: str = ""
    category: Category | None = None
    label: Label | None = None
    target_rules: list[str] = Field(default_factory=list)
    gold_symbol: str = ""
    file: str = ""
    note: str = ""
    status: Literal["valid", "invalid"] = "valid"
    escapes_tests: bool | None = None   # did the project's own suite still pass?
    error: str = ""
    workspace: str = ""

    @property
    def is_drift(self) -> bool:
        return self.label == "drift"


class Evidence(BaseModel):
    file: str = ""
    start_line: int = 0
    end_line: int = 0


class Counterexample(BaseModel):
    input: str = ""
    expected: str = ""
    actual: str = ""


class Verdict(BaseModel):
    """One detector's answer for one (case, rule) pair."""

    case_id: str
    rule_id: str
    detector: str
    verdict: VerdictValue
    confidence: float = 0.0
    violated_clause: str = ""
    evidence: Evidence = Field(default_factory=Evidence)
    counterexample: Counterexample = Field(default_factory=Counterexample)
    retrieved_chunks: list[str] = Field(default_factory=list)
    run: int = 1
    latency_ms: int = 0
    cache_hit: bool = False
    parse_error: bool = False

    @property
    def flags_drift(self) -> bool:
        return self.verdict == "DRIFT"

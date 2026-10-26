"""One supervised training example. The field names follow docs/training-data-spec.md."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from specdrift.bench.schema import Chunk, Counterexample, Evidence, Rule, VerdictValue


class Target(BaseModel):
    """What the model must emit; the same keys the Stage 2 prompt asks for."""

    verdict: VerdictValue
    confidence: float = 0.0
    violated_clause: str = ""
    evidence: Evidence = Field(default_factory=Evidence)
    counterexample: Counterexample = Field(default_factory=Counterexample)


class Provenance(BaseModel):
    label_method: Literal["execution", "test_suite", "injected_known", "human", "paper_pairing"]
    generator: str
    oracle_test: str | None = None
    gen_model: str | None = None
    seed: int | None = None
    # Free-form facts a later audit may need (bug_type, counterexample_method, ...).
    notes: dict[str, str] = Field(default_factory=dict)


class TrainingExample(BaseModel):
    example_id: str
    source: Literal["paper", "synth", "hardneg"]
    split: Literal["train", "val"]
    project_id: str
    rule: Rule
    chunks: list[Chunk]
    label: VerdictValue
    category: str
    target: Target
    provenance: Provenance

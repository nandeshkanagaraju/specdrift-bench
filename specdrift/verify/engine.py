"""SpecGuard: the detector under test. Stage 1 retrieval feeds Stage 2 verification."""

from __future__ import annotations

from pathlib import Path

from specdrift.bench.schema import CaseResult, Chunk, Rule, Verdict
from specdrift.cache import ResponseCache
from specdrift.code.chunker import chunk_workspace
from specdrift.config import Settings
from specdrift.retrieval.embedder import build_embedder
from specdrift.retrieval.retriever import add_constant_context, retrieve
from specdrift.spec.parser import load_project_rules
from specdrift.verify.llm import Completer, build_llm
from specdrift.verify.verifier import verify_rule

NAME = "specguard"


class SpecGuard:
    """Chunk the workspace, rank chunks per rule, then verify each rule against its top-k."""

    name = NAME

    def __init__(self, settings: Settings, llm: Completer | None = None) -> None:
        self.settings = settings
        self.llm = llm or build_llm(settings)
        self.embedder = build_embedder(
            settings.embed_backend, settings.embed_model, settings.cache_dir
        )
        self.cache = ResponseCache(settings.cache_dir, namespace="verify")

    @property
    def model(self) -> str:
        return getattr(self.llm, "model", "unknown")

    def analyse(self, workspace: Path) -> tuple[list[Rule], list[Chunk]]:
        return load_project_rules(workspace), chunk_workspace(workspace)

    def check_workspace(
        self,
        workspace: Path,
        case_id: str = "live",
        run: int = 1,
    ) -> list[Verdict]:
        rules, chunks = self.analyse(workspace)
        ranked = retrieve(rules, chunks, self.embedder, k=self.settings.top_k)
        by_id = {chunk.id: chunk for chunk in chunks}

        verdicts: list[Verdict] = []
        for rule in rules:
            top = [by_id[hit.chunk_id] for hit in ranked[rule.id] if hit.chunk_id in by_id]
            top = add_constant_context(top, chunks)
            verdicts.append(
                verify_rule(rule, top, self.llm, self.cache, case_id, self.name, run)
            )
        return verdicts

    def run_case(self, case: CaseResult, run: int = 1) -> list[Verdict]:
        return self.check_workspace(Path(case.workspace), case.case_id, run)

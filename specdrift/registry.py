"""Every detector is scored by identical code, so they share one interface."""

from __future__ import annotations

from typing import Protocol

from specdrift.bench.schema import CaseResult, Verdict
from specdrift.config import Settings


class Detector(Protocol):
    name: str

    def run_case(self, case: CaseResult, run: int = 1) -> list[Verdict]: ...


def build_detector(name: str, settings: Settings) -> Detector:
    if name == "specguard":
        from specdrift.verify.engine import SpecGuard

        return SpecGuard(settings)
    if name == "keyword":
        from specdrift.baselines.keyword import KeywordDetector

        return KeywordDetector(settings)
    if name == "wholefile":
        from specdrift.baselines.wholefile import WholeFileDetector

        return WholeFileDetector(settings)
    raise ValueError(f"unknown detector {name!r}")


DETECTOR_NAMES = ("specguard", "keyword", "wholefile")

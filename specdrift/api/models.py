"""Response shapes for the web API. The UI is typed against exactly these."""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator

from specdrift.bench.schema import Verdict


class CategoryCount(BaseModel):
    category: str
    name: str
    n: int
    escapes: int
    escapes_rate: float
    is_drift: bool


class DetectorInfo(BaseModel):
    name: str
    model: str = "n/a"
    llm_calls: int = 0
    cache_hits: int = 0
    scored: bool = False
    precision: float = 0.0
    recall: float = 0.0
    f1: float = 0.0
    false_alarm_rate: float = 0.0
    uncertain_rate: float = 0.0


class Summary(BaseModel):
    generated: str
    projects: list[str]
    total_cases: int
    valid_cases: int
    invalid_cases: int
    drift_cases: int
    negative_cases: int
    escapes_tests: int
    escapes_rate: float
    categories: list[CategoryCount]
    detectors: list[DetectorInfo]


class CategoryMetric(BaseModel):
    category: str
    name: str
    n: int
    metric: str
    value: float
    uncertain: int
    is_drift: bool


class DetectorMetrics(BaseModel):
    detector: str
    model: str = "n/a"
    cases_scored: int
    counts: dict[str, int]
    overall: dict[str, float]
    per_category: list[CategoryMetric]
    attribution: dict[str, int]


class MetricsResponse(BaseModel):
    detectors: list[DetectorMetrics]
    retrieval: dict | None = None


class CaseRow(BaseModel):
    id: str
    project: str
    category: str
    category_name: str
    label: str
    target_rules: list[str]
    gold_symbol: str
    file: str
    note: str
    status: str
    escapes_tests: bool | None
    verdicts: dict[str, str] = Field(default_factory=dict)


class CaseList(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[CaseRow]


class RuleOut(BaseModel):
    id: str
    text: str
    section: str = ""


class RetrievedChunk(BaseModel):
    chunk_id: str
    qualname: str
    file: str
    start_line: int
    end_line: int
    score: float
    is_gold: bool


class CaseDetail(BaseModel):
    case: CaseRow
    rules: list[RuleOut]
    before_source: str
    after_source: str
    changed_lines: list[int]
    verdicts: dict[str, list[Verdict]]
    retrieved: dict[str, list[RetrievedChunk]]
    outcomes: dict[str, dict]


class ProjectOut(BaseModel):
    name: str
    rule_count: int
    case_count: int
    spec: str
    rules: list[RuleOut]


class SourceFile(BaseModel):
    """One Python file of a host project, as the detector sees it."""

    path: str
    lines: int
    source: str


class UploadFileIn(BaseModel):
    path: str
    source: str


class UploadIn(BaseModel):
    """A project typed or pasted in the browser: one spec, one or more Python files."""

    name: str = "upload"
    spec: str = ""
    files: list[UploadFileIn]


class UploadFileOut(BaseModel):
    path: str
    lines: int
    source: str


class UploadOut(BaseModel):
    id: str
    name: str
    rules: list[RuleOut]
    files: list[UploadFileOut]
    warnings: list[str]
    spec_path: str = ""


class CheckRequest(BaseModel):
    """One of the built-in projects, or a workspace created by POST /api/uploads."""

    project: str | None = None
    case_id: str | None = None
    upload_id: str | None = None

    @model_validator(mode="after")
    def _one_target(self) -> CheckRequest:
        if self.upload_id and self.project:
            raise ValueError("provide a project or an upload_id, not both")
        if self.upload_id and self.case_id:
            raise ValueError("an uploaded project has no drift cases to inject")
        if not self.upload_id and not self.project:
            raise ValueError("provide a project or an upload_id")
        return self

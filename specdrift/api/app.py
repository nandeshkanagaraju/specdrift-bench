"""FastAPI app: JSON for the dashboard, Server-Sent Events for the live check."""

from __future__ import annotations

import asyncio
import json
from datetime import date
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from specdrift.api.models import (
    CaseDetail,
    CaseList,
    CaseRow,
    CategoryCount,
    CategoryMetric,
    CheckRequest,
    DetectorInfo,
    DetectorMetrics,
    MetricsResponse,
    ProjectOut,
    RetrievedChunk,
    RuleOut,
    SourceFile,
    Summary,
    UploadFileOut,
    UploadIn,
    UploadOut,
)
from specdrift.api.store import Store, workspace_for
from specdrift.bench.schema import (
    ALL_CATEGORIES,
    CATEGORY_NAMES,
    DRIFT_CATEGORIES,
    CaseResult,
)
from specdrift.config import REPO_ROOT, Settings, get_settings

WEB_DIST = REPO_ROOT / "web" / "dist"


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(title="SpecDrift-Bench", version="0.1.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    store = Store(settings)
    app.state.store = store
    app.state.settings = settings

    # ------------------------------------------------------------- summary

    @app.get("/api/summary", response_model=Summary)
    def summary() -> Summary:
        valid = [c for c in store.cases if c.status == "valid"]
        drift = [c for c in valid if c.is_drift]
        escaped = [c for c in drift if c.escapes_tests]

        categories = []
        for cat in ALL_CATEGORIES:
            rows = [c for c in valid if c.category == cat]
            if not rows:
                continue
            got = [c for c in rows if c.escapes_tests]
            categories.append(
                CategoryCount(
                    category=cat,
                    name=CATEGORY_NAMES[cat],
                    n=len(rows),
                    escapes=len(got),
                    escapes_rate=round(len(got) / len(rows), 4),
                    is_drift=cat in DRIFT_CATEGORIES,
                )
            )

        detectors = []
        for name in store.detectors:
            run = store.runs.get(name, {})
            metrics = store.metrics.get(name)
            overall = (metrics or {}).get("overall", {})
            detectors.append(
                DetectorInfo(
                    name=name,
                    model=run.get("model", "n/a"),
                    llm_calls=run.get("llm_calls", 0),
                    cache_hits=run.get("cache_hits", 0),
                    scored=metrics is not None,
                    precision=overall.get("precision", 0.0),
                    recall=overall.get("recall", 0.0),
                    f1=overall.get("f1", 0.0),
                    false_alarm_rate=overall.get("false_alarm_rate", 0.0),
                    uncertain_rate=overall.get("uncertain_rate", 0.0),
                )
            )

        return Summary(
            generated=date.today().isoformat(),
            projects=store.projects,
            total_cases=len(store.cases),
            valid_cases=len(valid),
            invalid_cases=len(store.cases) - len(valid),
            drift_cases=len(drift),
            negative_cases=len(valid) - len(drift),
            escapes_tests=len(escaped),
            escapes_rate=round(len(escaped) / len(drift), 4) if drift else 0.0,
            categories=categories,
            detectors=detectors,
        )

    # ------------------------------------------------------------- metrics

    @app.get("/api/metrics", response_model=MetricsResponse)
    def metrics(detector: str | None = Query(None)) -> MetricsResponse:
        names = [detector] if detector else store.detectors
        out: list[DetectorMetrics] = []

        for name in names:
            payload = store.metrics.get(name)
            if payload is None:
                continue
            per_category = [
                CategoryMetric(
                    category=cat,
                    name=row["name"],
                    n=row["n"],
                    metric=row["metric"],
                    value=row["value"],
                    uncertain=row["uncertain"],
                    is_drift=cat in DRIFT_CATEGORIES,
                )
                for cat, row in payload["per_category"].items()
            ]
            out.append(
                DetectorMetrics(
                    detector=name,
                    model=store.runs.get(name, {}).get("model", "n/a"),
                    cases_scored=payload["cases_scored"],
                    counts=payload["counts"],
                    overall=payload["overall"],
                    per_category=per_category,
                    attribution=payload.get("attribution", {}),
                )
            )

        if detector and not out:
            raise HTTPException(404, f"no metrics for detector {detector!r}")

        return MetricsResponse(detectors=out, retrieval=store.retrieval)

    # --------------------------------------------------------------- cases

    def to_row(case: CaseResult) -> CaseRow:
        return CaseRow(
            id=case.case_id,
            project=case.project,
            category=case.category or "",
            category_name=store.category_name(case.category),
            label=case.label or "",
            target_rules=case.target_rules,
            gold_symbol=case.gold_symbol,
            file=case.file,
            note=case.note,
            status=case.status,
            escapes_tests=case.escapes_tests,
            verdicts=store.case_verdicts(case.case_id),
        )

    @app.get("/api/cases", response_model=CaseList)
    def cases(
        project: str | None = None,
        category: str | None = None,
        label: str | None = None,
        escapes_tests: bool | None = None,
        q: str | None = None,
        page: int = Query(1, ge=1),
        page_size: int = Query(200, ge=1, le=1000),
    ) -> CaseList:
        rows = store.cases
        if project:
            rows = [c for c in rows if c.project == project]
        if category:
            rows = [c for c in rows if c.category == category]
        if label:
            rows = [c for c in rows if c.label == label]
        if escapes_tests is not None:
            rows = [c for c in rows if bool(c.escapes_tests) == escapes_tests]
        if q:
            needle = q.lower()
            rows = [
                c for c in rows
                if needle in c.case_id.lower()
                or needle in (c.note or "").lower()
                or needle in (c.gold_symbol or "").lower()
                or any(needle in rule.lower() for rule in c.target_rules)
            ]

        start = (page - 1) * page_size
        return CaseList(
            total=len(rows),
            page=page,
            page_size=page_size,
            items=[to_row(case) for case in rows[start : start + page_size]],
        )

    @app.get("/api/cases/{case_id}", response_model=CaseDetail)
    def case_detail(case_id: str) -> CaseDetail:
        case = store.cases_by_id.get(case_id)
        if case is None:
            raise HTTPException(404, f"unknown case {case_id!r}")

        before, after, changed = store.sources(case_id)
        all_rules = store.rules.get(case.project, [])
        targets = [r for r in all_rules if r.id in case.target_rules] or all_rules[:1]

        return CaseDetail(
            case=to_row(case),
            rules=[RuleOut(id=r.id, text=r.text, section=r.section) for r in targets],
            before_source=before,
            after_source=after,
            changed_lines=changed,
            verdicts=store.verdicts_for(case_id),
            retrieved=_retrieved_for(case),
            outcomes=store.outcomes(case_id),
        )

    def _retrieved_for(case: CaseResult) -> dict[str, list[RetrievedChunk]]:
        """Re-rank the case's own workspace so the UI can show scores and the gold marker."""
        workspace = workspace_for(settings, case)
        if workspace is None or not case.target_rules:
            return {}

        from specdrift.code.chunker import chunk_workspace
        from specdrift.retrieval.embedder import build_embedder
        from specdrift.retrieval.retriever import matches_gold, retrieve
        from specdrift.spec.parser import load_project_rules, rules_by_id

        chunks = chunk_workspace(workspace)
        by_id = {c.id: c for c in chunks}
        lookup = rules_by_id(load_project_rules(workspace))
        wanted = [lookup[rid] for rid in case.target_rules if rid in lookup]
        if not wanted:
            return {}

        embedder = build_embedder(settings.embed_backend, settings.embed_model, settings.cache_dir)
        ranked = retrieve(wanted, chunks, embedder, k=max(settings.top_k, 5))

        out: dict[str, list[RetrievedChunk]] = {}
        for rule in wanted:
            rows = []
            for hit in ranked[rule.id]:
                chunk = by_id.get(hit.chunk_id)
                if chunk is None:
                    continue
                rows.append(
                    RetrievedChunk(
                        chunk_id=chunk.id,
                        qualname=chunk.qualname,
                        file=chunk.file,
                        start_line=chunk.start_line,
                        end_line=chunk.end_line,
                        score=hit.score,
                        is_gold=matches_gold(chunk.id, case.gold_symbol),
                    )
                )
            out[rule.id] = rows
        return out

    # ------------------------------------------------------------ projects

    @app.get("/api/projects", response_model=list[ProjectOut])
    def projects() -> list[ProjectOut]:
        counts = store.project_case_counts()
        return [
            ProjectOut(
                name=name,
                rule_count=len(store.rules.get(name, [])),
                case_count=counts.get(name, 0),
                spec=store.spec_text(name),
                rules=[
                    RuleOut(id=r.id, text=r.text, section=r.section)
                    for r in store.rules.get(name, [])
                ],
            )
            for name in store.projects
        ]

    @app.get("/api/projects/{name}/code", response_model=list[SourceFile])
    def project_code(name: str) -> list[SourceFile]:
        """The project's own Python sources — the second input, shown as the UI's input panel."""
        root = settings.projects_dir / name
        if not (root / "spec.md").exists():
            raise HTTPException(404, f"unknown project {name!r}")

        # The chunker reads root/src, so show exactly that and nothing else: the
        # project's own tests are not part of what the detector ever sees.
        base = root / "src" if (root / "src").exists() else root
        files = sorted(p for p in base.rglob("*.py") if "__pycache__" not in p.parts)
        out = []
        for path in files:
            text = path.read_text(encoding="utf-8")
            out.append(
                SourceFile(
                    path=str(path.relative_to(root)),
                    lines=text.count("\n") + 1,
                    source=text,
                )
            )
        return out

    # --------------------------------------------------------------- uploads

    def _upload_out(record) -> UploadOut:
        return UploadOut(
            id=record.id,
            name=record.name,
            rules=[RuleOut(id=rule.id, text=rule.text, section=rule.section) for rule in record.rules],
            files=[
                UploadFileOut(path=item.path, lines=item.lines, source=item.source)
                for item in record.files
            ],
            warnings=record.warnings,
            spec_path=record.spec_path,
        )

    @app.post("/api/uploads", response_model=UploadOut)
    def create_upload(body: UploadIn) -> UploadOut:
        """Save a pasted spec and Python files, then return the rules the checker will use."""
        from specdrift.intake import IntakeError, materialize_files

        try:
            record = materialize_files(
                settings,
                body.name,
                body.spec,
                [(item.path, item.source) for item in body.files],
            )
        except IntakeError as exc:
            raise HTTPException(422, str(exc)) from exc
        return _upload_out(record)

    @app.post("/api/uploads/archive", response_model=UploadOut)
    async def create_upload_archive(request: Request, name: str = Query("upload")) -> UploadOut:
        """Save a zip (``spec.md`` plus ``.py`` files) sent as the raw request body."""
        from specdrift.intake import MAX_TOTAL_BYTES, IntakeError, materialize_zip

        data = await request.body()
        if len(data) > MAX_TOTAL_BYTES:
            raise HTTPException(413, "The archive is larger than 1.5 MB.")
        try:
            record = materialize_zip(settings, name, data)
        except IntakeError as exc:
            raise HTTPException(422, str(exc)) from exc
        return _upload_out(record)

    @app.get("/api/uploads/{upload_id}", response_model=UploadOut)
    def get_upload(upload_id: str) -> UploadOut:
        from specdrift.intake import load_upload

        record = load_upload(settings, upload_id)
        if record is None:
            raise HTTPException(404, f"unknown upload {upload_id!r}")
        return _upload_out(record)

    # --------------------------------------------------------------- check

    @app.post("/api/check")
    async def check(request: CheckRequest) -> StreamingResponse:
        target = _resolve_check_target(request)

        async def stream():
            from specdrift.bench.schema import Verdict
            from specdrift.live import check_project

            loop = asyncio.get_running_loop()
            queue: asyncio.Queue = asyncio.Queue()
            done = object()

            def on_progress(event: str, payload) -> None:
                """Called from the worker thread; hand the event to the event loop."""
                if isinstance(payload, Verdict):
                    payload = json.loads(payload.model_dump_json())
                loop.call_soon_threadsafe(queue.put_nowait, (event, payload))

            def work():
                try:
                    return check_project(target, settings, None, on_progress)
                finally:
                    loop.call_soon_threadsafe(queue.put_nowait, done)

            future = loop.run_in_executor(None, work)
            yield _sse(
                "start",
                {
                    "project": request.project,
                    "case_id": request.case_id,
                    "upload_id": request.upload_id,
                },
            )

            while True:
                item = await queue.get()
                if item is done:
                    break
                event, payload = item
                yield _sse(event, payload)
                if event == "verdict":
                    # Cached answers come back instantly, which makes a 14-rule run
                    # finish before anyone can watch it. Pace the reveal so each check
                    # is visibly its own step. An uncached model call is slower than
                    # this anyway, so it costs a real run nothing.
                    await asyncio.sleep(0.28)

            _, summary_payload = await future
            yield _sse("summary", summary_payload)

        return StreamingResponse(
            stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    # ---------------------------------------------------------------- sweep

    @app.post("/api/sweep")
    async def sweep() -> StreamingResponse:
        """Check one representative case of every drift category, category by category."""
        from specdrift.live import run_sweep, sweep_cases

        cases = sweep_cases(settings)
        by_id = {case.case_id: case for case in cases}

        def describe(case_id: str) -> dict:
            """The planted change, as one line before and one line after."""
            case = by_id[case_id]
            before_src, after_src, changed = store.sources(case_id)
            before_lines, after_lines = before_src.split("\n"), after_src.split("\n")

            head = 0
            while (
                head < len(before_lines)
                and head < len(after_lines)
                and before_lines[head] == after_lines[head]
            ):
                head += 1
            tail = 0
            while (
                tail < len(before_lines) - head
                and tail < len(after_lines) - head
                and before_lines[-1 - tail] == after_lines[-1 - tail]
            ):
                tail += 1

            removed = [line.strip() for line in before_lines[head : len(before_lines) - tail]]
            added = [line.strip() for line in after_lines[head : len(after_lines) - tail]]

            return {
                "case_id": case_id,
                "category": case.category,
                "category_name": store.category_name(case.category),
                "project": case.project,
                "note": case.note,
                "file": case.file,
                "target_rules": case.target_rules,
                "escapes_tests": case.escapes_tests,
                "before": " ".join(removed)[:120],
                "after": " ".join(added)[:120],
                "line": changed[0] if changed else 0,
            }

        async def stream():
            loop = asyncio.get_running_loop()
            queue: asyncio.Queue = asyncio.Queue()
            done = object()

            def on_progress(event: str, payload) -> None:
                if event == "case_start":
                    payload = describe(payload["case_id"])
                loop.call_soon_threadsafe(queue.put_nowait, (event, payload))

            def work():
                try:
                    return run_sweep(cases, settings, on_progress)
                finally:
                    loop.call_soon_threadsafe(queue.put_nowait, done)

            future = loop.run_in_executor(None, work)
            yield _sse(
                "sweep_start",
                {"total": len(cases), "categories": [c.category for c in cases]},
            )

            while True:
                item = await queue.get()
                if item is done:
                    break
                event, payload = item
                yield _sse(event, payload)
                # Paced so each category reads as its own step rather than a blur;
                # cached answers make the real work almost instantaneous.
                await asyncio.sleep(0.75 if event == "case_result" else 0.35)

            rows = await future
            yield _sse(
                "sweep_summary",
                {"total": len(rows), "caught": sum(1 for r in rows if r["caught"])},
            )

        return StreamingResponse(
            stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    def _resolve_check_target(request: CheckRequest) -> Path:
        if request.upload_id:
            from specdrift.intake import upload_root

            root = upload_root(settings, request.upload_id)
            if root is None:
                raise HTTPException(404, f"unknown upload {request.upload_id!r}")
            return root

        if request.case_id:
            case = store.cases_by_id.get(request.case_id)
            if case is None:
                raise HTTPException(404, f"unknown case {request.case_id!r}")
            workspace = workspace_for(settings, case)
            if workspace is None:
                raise HTTPException(409, "case workspace is missing; run `specdrift build`")
            return workspace

        target = settings.projects_dir / (request.project or "")
        if not (target / "spec.md").exists():
            raise HTTPException(404, f"unknown project {request.project!r}")
        return target

    # -------------------------------------------------------------- reload

    @app.post("/api/reload")
    def reload_store() -> dict:
        store.reload()
        return {
            "cases": len(store.cases),
            "detectors": store.detectors,
            "scored": sorted(store.metrics),
        }

    if WEB_DIST.exists():
        app.mount("/", SPAStaticFiles(directory=WEB_DIST, html=True), name="web")

    return app


class SPAStaticFiles(StaticFiles):
    """Serve the built app, falling back to index.html for client-side routes.

    Without this, opening /explorer directly or reloading on /cases/<id> would 404:
    those paths exist only in the router, never on disk.
    """

    async def get_response(self, path: str, scope):
        try:
            response = await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            if exc.status_code != 404:
                raise
            return await super().get_response("index.html", scope)

        if response.status_code == 404:
            return await super().get_response("index.html", scope)
        return response


def _sse(event: str, payload: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(payload)}\n\n"


app = create_app()

from __future__ import annotations

from typing import Annotated, Any, Literal, Optional

from fastapi import APIRouter, Path, Query, Request, Response
from pydantic import BaseModel, Field

from .. import APP_VERSION
from ..core.engine.base import ENGINE_VERSION
from ..core.schema.spec import SpecValidationError
from ..services import reporting
from ..services.analysis_service import analyze_summary
from ..services.batch_service import MAX_BATCH_ITEMS
from ..services.experiment_service import EXPERIMENT_NAME_MAX, ConflictError, NotFoundError
from ..services.session_service import MAX_STEP_BATCH


router = APIRouter(prefix="/api")

# 分页/事件数量上限（R59）：不校验时 SQLite 的 `LIMIT -1` 是「无上限」，
# `events_limit=0` 的切片 `[-0:]` 反而会返回全部事件。所有列表端点统一用这里的边界。
MAX_PAGE_SIZE = 1000
MAX_EVENTS_LIMIT = 500
# 批单项状态（R88）：筛选参数用 Literal，未知状态由 FastAPI 直接 422，不落到 SQL
BatchItemStatus = Literal[
    "pending", "running", "completed", "failed", "cancelled", "step_limit", "wall_timeout"
]
# 实验状态（R91）：由 run 结果同步而来，created 表示尚未运行
ExperimentStatus = Literal[
    "created", "running", "completed", "failed", "cancelled", "step_limit", "wall_timeout"
]
# 批量状态（R92）：创建后 queued，orchestrator 启动后 running，终态三种
BatchStatus = Literal["queued", "running", "completed", "failed", "cancelled"]
# R64：offset 不设上限时，`offset=999999999999999999999` 会让 Python 大整数进 SQLite，
# 触发 OverflowError → 500。路径 id 同理（用 RowId 约束）。
MAX_OFFSET = 1_000_000_000
RowId = Annotated[int, Path(ge=1, le=2**63 - 1)]


class CreateExperimentBody(BaseModel):
    name: str = Field(min_length=1, max_length=EXPERIMENT_NAME_MAX)
    spec: dict[str, Any]


class RunBody(BaseModel):
    wait: bool = False


class CloneBody(BaseModel):
    name: Optional[str] = None
    spec_overrides: Optional[dict[str, Any]] = None


class TagsBody(BaseModel):
    tags: list[str]


def _service(request: Request):
    return request.app.state.service


@router.get("/health")
def health(request: Request) -> dict[str, Any]:
    from .. import APP_VERSION
    from ..core.engine.base import ENGINE_VERSION

    return {"status": "ok", "app_version": APP_VERSION, "engine_version": ENGINE_VERSION}


# --------------------------------------------------------------------- models
@router.get("/models")
def list_models(request: Request) -> dict[str, Any]:
    return {"models": _service(request).list_models()}


@router.get("/models/{model_id}")
def get_model(model_id: str, request: Request, version: str | None = None) -> dict[str, Any]:
    """默认返回最新版本；`?version=` 可取指定版本（版本号按数字组分比较）。"""
    matches = _service(request).model_versions(model_id)
    if not matches:
        raise NotFoundError(f"model {model_id} not found")
    if version is None:
        return matches[-1]
    for m in matches:
        if m["version"] == version:
            return m
    raise NotFoundError(
        f"model {model_id} has no version {version!r}; available: {[m['version'] for m in matches]}"
    )


@router.post("/models/{model_id}/validate")
def validate_model_spec(model_id: str, request: Request, body: dict[str, Any]) -> dict[str, Any]:
    body = dict(body)
    body.setdefault("model_id", model_id)
    service = _service(request)
    try:
        return service.validate_spec_only(body)
    except SpecValidationError as exc:
        return {"valid": False, "errors": exc.errors, "normalized_spec": None}


# ---------------------------------------------------------------- experiments
@router.post("/experiments", status_code=201)
def create_experiment(request: Request, body: CreateExperimentBody) -> dict[str, Any]:
    return _service(request).create_experiment(body.name, body.spec)


@router.get("/experiments")
def list_experiments(
    request: Request,
    limit: int = Query(50, ge=1, le=MAX_PAGE_SIZE),
    offset: int = Query(0, ge=0, le=MAX_OFFSET),
    model_id: Optional[str] = None,
    tag: Optional[str] = None,
    status: ExperimentStatus | None = None,
) -> dict[str, Any]:
    return _service(request).list_experiments(limit, offset, model_id, tag, status)


@router.get("/experiments/{exp_id}")
def get_experiment(exp_id: RowId, request: Request) -> dict[str, Any]:
    return _service(request).get_experiment(exp_id)


@router.delete("/experiments/{exp_id}", status_code=204)
def delete_experiment(exp_id: RowId, request: Request) -> None:
    _service(request).delete_experiment(exp_id)


@router.post("/experiments/{exp_id}/clone")
def clone_experiment(exp_id: RowId, request: Request, body: CloneBody | None = None) -> dict[str, Any]:
    body = body or CloneBody()
    return _service(request).clone_experiment(exp_id, body.name, body.spec_overrides)


@router.put("/experiments/{exp_id}/tags")
def set_tags(exp_id: RowId, request: Request, body: TagsBody) -> dict[str, Any]:
    return _service(request).set_tags(exp_id, body.tags)


@router.post("/experiments/{exp_id}/run")
def run_experiment(exp_id: RowId, request: Request, body: RunBody | None = None) -> dict[str, Any]:
    body = body or RunBody()
    return _service(request).run_experiment(exp_id, wait=body.wait)


@router.get("/experiments/{exp_id}/result")
def get_result(exp_id: RowId, request: Request) -> dict[str, Any]:
    return _service(request).get_result(exp_id)


@router.post("/experiments/{exp_id}/cancel")
def cancel_experiment(exp_id: RowId, request: Request) -> dict[str, Any]:
    return _service(request).cancel_experiment(exp_id)


@router.post("/experiments/{exp_id}/rerun")
def rerun_experiment(exp_id: RowId, request: Request) -> dict[str, Any]:
    return _service(request).rerun_experiment(exp_id)


@router.get("/experiments/{exp_id}/report")
def get_experiment_report(
    exp_id: RowId, request: Request, format: Literal["markdown", "json"] = "markdown"
) -> Any:
    service = _service(request)
    result = service.get_result(exp_id)
    report = reporting.build_experiment_report(result, APP_VERSION, ENGINE_VERSION)
    if format == "json":
        return report
    md = reporting.render_report_markdown(report)
    return Response(
        content=md,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="worldlab-report-{exp_id}.md"'},
    )


# ----------------------------------------------------------------------- runs
@router.get("/runs/{run_id}")
def get_run(
    run_id: RowId, request: Request, events_limit: int = Query(50, ge=0, le=MAX_EVENTS_LIMIT)
) -> dict[str, Any]:
    return _service(request).get_run(run_id, events_limit)


@router.get("/runs/{run_id}/events")
def get_run_events(
    run_id: RowId,
    request: Request,
    limit: int = Query(100, ge=1, le=MAX_PAGE_SIZE),
    offset: int = Query(0, ge=0, le=MAX_OFFSET),
) -> dict[str, Any]:
    return _service(request).get_run_events(run_id, limit, offset)


# -------------------------------------------------------------------- sessions
class CreateSessionBody(BaseModel):
    spec: dict[str, Any]


class StepBody(BaseModel):
    n: int = Field(default=1, ge=1, le=1_000_000)


class RestoreBody(BaseModel):
    checkpoint: dict[str, Any]


@router.get("/sessions")
def list_sessions(request: Request) -> dict[str, Any]:
    return {"sessions": _service(request).sessions.list_sessions()}


@router.post("/sessions", status_code=201)
def create_session(request: Request, body: CreateSessionBody) -> dict[str, Any]:
    return _service(request).sessions.create(body.spec)


@router.get("/sessions/{session_id}")
def get_session(
    session_id: str, request: Request, events_limit: int = Query(50, ge=0, le=MAX_EVENTS_LIMIT)
) -> dict[str, Any]:
    return _service(request).sessions.state(session_id, events_limit)


@router.delete("/sessions/{session_id}", status_code=204)
def delete_session(session_id: str, request: Request) -> None:
    _service(request).sessions.delete(session_id)


@router.post("/sessions/{session_id}/step")
def step_session(session_id: str, request: Request, body: StepBody | None = None) -> dict[str, Any]:
    body = body or StepBody()
    return _service(request).sessions.step(session_id, body.n)


@router.post("/sessions/{session_id}/run")
def run_session(session_id: str, request: Request) -> dict[str, Any]:
    return _service(request).sessions.run(session_id)


@router.post("/sessions/{session_id}/pause")
def pause_session(session_id: str, request: Request) -> dict[str, Any]:
    return _service(request).sessions.pause(session_id)


@router.post("/sessions/{session_id}/resume")
def resume_session(session_id: str, request: Request) -> dict[str, Any]:
    return _service(request).sessions.resume(session_id)


@router.post("/sessions/{session_id}/reset")
def reset_session(session_id: str, request: Request) -> dict[str, Any]:
    return _service(request).sessions.reset(session_id)


@router.post("/sessions/{session_id}/checkpoint")
def checkpoint_session(session_id: str, request: Request) -> dict[str, Any]:
    return _service(request).sessions.checkpoint(session_id)


@router.post("/sessions/{session_id}/restore")
def restore_session(session_id: str, request: Request, body: RestoreBody) -> dict[str, Any]:
    return _service(request).sessions.restore(session_id, body.checkpoint)


# -------------------------------------------------------------------- batches
class CreateBatchBody(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    spec: dict[str, Any]
    grid: dict[str, list[Any]]
    repeats: int = Field(default=1, ge=1, le=100)
    seed_strategy: Literal["fixed", "per_repeat_increment", "unique"] = "fixed"
    max_retries: int = Field(default=0, ge=0, le=10)
    concurrency: int = Field(default=2, ge=1, le=64)
    per_run_wall_seconds: float = Field(default=60.0, gt=0)


def _field_bound(model_field: str, kind: str, fallback: int) -> int:
    """Read a pydantic constraint (ge/le/max_length…) off CreateBatchBody so the
    frontend consumes the server's own rules instead of a second hardcoded copy."""
    for meta in CreateBatchBody.model_fields[model_field].metadata:
        value = getattr(meta, kind, None)
        if value is not None:
            return int(value)
    return fallback


@router.get("/limits")
def get_limits(request: Request) -> dict[str, Any]:
    settings = _service(request).settings
    return {
        "batch": {
            "max_items": MAX_BATCH_ITEMS,
            "name_max_length": _field_bound("name", "max_length", 200),
            "repeats_min": _field_bound("repeats", "ge", 1),
            "repeats_max": _field_bound("repeats", "le", 100),
            "max_retries_min": _field_bound("max_retries", "ge", 0),
            "max_retries_max": _field_bound("max_retries", "le", 10),
            "concurrency_min": _field_bound("concurrency", "ge", 1),
            "concurrency_max": _field_bound("concurrency", "le", 64),
        },
        "engine": {
            "max_wall_seconds": settings.max_wall_seconds,
            "max_workers": settings.max_workers,
            "default_max_steps": settings.default_max_steps,
        },
        # R47：会话单次 step(n) 的上限此前只在后端校验，前端只能等 422；
        # 与校验共用常量，前端据此做 input max 与提交前拦截。
        "session": {"max_step_batch": MAX_STEP_BATCH},
        # R59：列表分页与事件数量的边界（同一个常量供校验与契约使用）
        "pagination": {"max_limit": MAX_PAGE_SIZE, "max_events": MAX_EVENTS_LIMIT, "max_offset": MAX_OFFSET},
        "experiment": {"name_max_length": EXPERIMENT_NAME_MAX},
    }


def _batches(request: Request):
    return request.app.state.batches


@router.post("/batches", status_code=201)
def create_batch(request: Request, body: CreateBatchBody) -> dict[str, Any]:
    return _batches(request).create(
        body.name,
        body.spec,
        body.grid,
        body.repeats,
        body.seed_strategy,
        body.max_retries,
        body.concurrency,
        body.per_run_wall_seconds,
    )


@router.get("/batches")
def list_batches(
    request: Request,
    limit: int = Query(50, ge=1, le=MAX_PAGE_SIZE),
    offset: int = Query(0, ge=0, le=MAX_OFFSET),
    model_id: Optional[str] = None,
    status: BatchStatus | None = None,
) -> dict[str, Any]:
    return _batches(request).list_batches(limit, offset, model_id, status)


@router.get("/batches/{batch_id}")
def get_batch(batch_id: RowId, request: Request) -> dict[str, Any]:
    return _batches(request).get_batch(batch_id)


@router.get("/batches/{batch_id}/findings")
def batch_findings(batch_id: RowId, request: Request) -> dict[str, Any]:
    batch = _batches(request).get_batch(batch_id, include_summary=True)
    return analyze_summary(batch.get("summary", {}), batch.get("grid", {}))


@router.get("/batches/{batch_id}/report")
def batch_report(
    batch_id: RowId, request: Request, format: Literal["markdown", "json"] = "markdown"
) -> Any:
    batch = _batches(request).get_batch(batch_id, include_summary=True)
    findings = analyze_summary(batch.get("summary", {}), batch.get("grid", {}))
    report = reporting.build_batch_report(batch, findings, APP_VERSION, ENGINE_VERSION)
    if format == "json":
        return report
    return Response(
        content=reporting.render_batch_report_markdown(report),
        media_type="text/markdown; charset=utf-8",
    )


@router.get("/batches/{batch_id}/items")
def list_batch_items(
    batch_id: RowId,
    request: Request,
    limit: int = Query(200, ge=1, le=MAX_PAGE_SIZE),
    offset: int = Query(0, ge=0, le=MAX_OFFSET),
    status: BatchItemStatus | None = None,
) -> dict[str, Any]:
    return _batches(request).list_items(batch_id, limit, offset, status)


@router.post("/batches/{batch_id}/cancel")
def cancel_batch(batch_id: RowId, request: Request) -> dict[str, Any]:
    return _batches(request).cancel(batch_id)


@router.post("/batches/{batch_id}/retry")
def retry_failed_items(batch_id: RowId, request: Request) -> dict[str, Any]:
    return _batches(request).retry_failed(batch_id)


@router.delete("/batches/{batch_id}", status_code=204)
def delete_batch(batch_id: RowId, request: Request) -> None:
    _batches(request).delete(batch_id)


@router.get("/batches/{batch_id}/export.csv")
def export_batch_csv(batch_id: RowId, request: Request) -> Response:
    batches = _batches(request)
    batch = batches.get_batch(batch_id, include_summary=False)
    items: list[dict[str, Any]] = []
    offset = 0
    page = 500
    while True:
        res = batches.list_items(batch_id, page, offset)
        items.extend(res["items"])
        if len(items) >= res["total"] or not res["items"]:
            break
        offset += page
    csv_text = reporting.render_batch_items_csv(batch, items)
    return Response(
        content=csv_text,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="worldlab-batch-{batch_id}.csv"'},
    )

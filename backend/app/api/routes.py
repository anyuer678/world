from __future__ import annotations

from typing import Any, Literal, Optional

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from ..core.schema.spec import SpecValidationError
from ..services.experiment_service import ConflictError, NotFoundError


router = APIRouter(prefix="/api")


class CreateExperimentBody(BaseModel):
    name: str = Field(min_length=1, max_length=200)
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
def get_model(model_id: str, request: Request) -> dict[str, Any]:
    models = _service(request).list_models()
    for m in models:
        if m["model_id"] == model_id:
            return m
    raise NotFoundError(f"model {model_id} not found")


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
    limit: int = 50,
    offset: int = 0,
    model_id: Optional[str] = None,
    tag: Optional[str] = None,
) -> dict[str, Any]:
    return _service(request).list_experiments(limit, offset, model_id, tag)


@router.get("/experiments/{exp_id}")
def get_experiment(exp_id: int, request: Request) -> dict[str, Any]:
    return _service(request).get_experiment(exp_id)


@router.delete("/experiments/{exp_id}", status_code=204)
def delete_experiment(exp_id: int, request: Request) -> None:
    _service(request).delete_experiment(exp_id)


@router.post("/experiments/{exp_id}/clone")
def clone_experiment(exp_id: int, request: Request, body: CloneBody | None = None) -> dict[str, Any]:
    body = body or CloneBody()
    return _service(request).clone_experiment(exp_id, body.name, body.spec_overrides)


@router.put("/experiments/{exp_id}/tags")
def set_tags(exp_id: int, request: Request, body: TagsBody) -> dict[str, Any]:
    return _service(request).set_tags(exp_id, body.tags)


@router.post("/experiments/{exp_id}/run")
def run_experiment(exp_id: int, request: Request, body: RunBody | None = None) -> dict[str, Any]:
    body = body or RunBody()
    return _service(request).run_experiment(exp_id, wait=body.wait)


@router.get("/experiments/{exp_id}/result")
def get_result(exp_id: int, request: Request) -> dict[str, Any]:
    return _service(request).get_result(exp_id)


@router.post("/experiments/{exp_id}/cancel")
def cancel_experiment(exp_id: int, request: Request) -> dict[str, Any]:
    return _service(request).cancel_experiment(exp_id)


@router.post("/experiments/{exp_id}/rerun")
def rerun_experiment(exp_id: int, request: Request) -> dict[str, Any]:
    return _service(request).rerun_experiment(exp_id)


# ----------------------------------------------------------------------- runs
@router.get("/runs/{run_id}")
def get_run(run_id: int, request: Request, events_limit: int = 50) -> dict[str, Any]:
    return _service(request).get_run(run_id, events_limit)


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
def get_session(session_id: str, request: Request, events_limit: int = 50) -> dict[str, Any]:
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
def list_batches(request: Request, limit: int = 50, offset: int = 0) -> dict[str, Any]:
    return _batches(request).list_batches(limit, offset)


@router.get("/batches/{batch_id}")
def get_batch(batch_id: int, request: Request) -> dict[str, Any]:
    return _batches(request).get_batch(batch_id)


@router.get("/batches/{batch_id}/items")
def list_batch_items(
    batch_id: int, request: Request, limit: int = 200, offset: int = 0
) -> dict[str, Any]:
    return _batches(request).list_items(batch_id, limit, offset)


@router.post("/batches/{batch_id}/cancel")
def cancel_batch(batch_id: int, request: Request) -> dict[str, Any]:
    return _batches(request).cancel(batch_id)

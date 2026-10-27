from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from . import APP_VERSION
from .config import Settings, default_settings
from .core.engine.base import ENGINE_VERSION
from .core.schema.spec import SpecValidationError
from .services.batch_service import BatchService
from .services.experiment_service import ConflictError, ExperimentService, NotFoundError
from .services.session_service import SessionService

import app.models  # noqa: F401 - register built-in model plugins
from .core.registry import registry


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or default_settings
    service = ExperimentService(settings, registry)
    sessions = SessionService(settings, registry)
    batches = BatchService(settings, registry)
    service.sessions = sessions

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        yield
        sessions.shutdown()
        batches.shutdown()
        service.shutdown()

    app = FastAPI(title="WorldLab", version=APP_VERSION, lifespan=lifespan)
    app.state.service = service
    app.state.sessions = sessions
    app.state.batches = batches

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    from .api.routes import router

    app.include_router(router)

    @app.exception_handler(NotFoundError)
    async def _not_found(_: Request, exc: NotFoundError):
        return JSONResponse(status_code=404, content={"detail": {"code": "not_found", "message": str(exc)}})

    @app.exception_handler(ConflictError)
    async def _conflict(_: Request, exc: ConflictError):
        return JSONResponse(status_code=409, content={"detail": {"code": "conflict", "message": str(exc)}})

    @app.exception_handler(SpecValidationError)
    async def _spec_invalid(_: Request, exc: SpecValidationError):
        return JSONResponse(
            status_code=422,
            content={"detail": {"code": "spec_invalid", "message": "spec validation failed", "errors": exc.errors}},
        )

    return app


app = create_app()


def main() -> None:
    import uvicorn

    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=False)


if __name__ == "__main__":
    main()

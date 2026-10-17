from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

import starshine_geo

from .execution import ExecutionBoundaryError, PreflightRejectedError, execute_inline_workflow
from .limits import (
    RequestBodyLimitMiddleware,
    RequestLimitError,
    enforce_inline_preflight_limits,
    execution_limits,
    inline_preflight_limits,
)
from .models import InlineExecutionRequest, InlinePreflightRequest, WorkflowRequest

API_VERSION = 1


def _workflow_error_response(
    exc: starshine_geo.WorkflowValidationError,
) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={
            "error": "workflow_validation",
            "diagnostic": exc.diagnostic.as_dict(),
        },
    )


def _validation_error_response(exc: starshine_geo.ValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={
            "error": "validation",
            "message": str(exc),
        },
    )


def create_app() -> FastAPI:
    """Create the Starshine HTTP adapter using only public starshine_geo APIs."""
    app = FastAPI(
        title="Starshine Server",
        version=starshine_geo.__version__,
        description=(
            "Bounded HTTP adapter for the auditable Starshine Geo workflow core. "
            "The current execution surface requires canonical Preflight and runs the Core "
            "in a supervised child process."
        ),
        docs_url="/api/docs",
        redoc_url=None,
        openapi_url="/api/openapi.json",
    )
    app.add_middleware(RequestBodyLimitMiddleware)

    @app.exception_handler(starshine_geo.WorkflowValidationError)
    async def workflow_validation_error_handler(
        request: Request,
        exc: starshine_geo.WorkflowValidationError,
    ) -> JSONResponse:
        del request
        return _workflow_error_response(exc)

    @app.exception_handler(starshine_geo.ValidationError)
    async def validation_error_handler(
        request: Request,
        exc: starshine_geo.ValidationError,
    ) -> JSONResponse:
        del request
        return _validation_error_response(exc)

    @app.exception_handler(PreflightRejectedError)
    async def preflight_rejected_error_handler(
        request: Request,
        exc: PreflightRejectedError,
    ) -> JSONResponse:
        del request
        return JSONResponse(
            status_code=422,
            content={
                "error": "preflight_failed",
                "message": str(exc),
                "preflight": exc.report,
            },
        )

    @app.exception_handler(ExecutionBoundaryError)
    async def execution_boundary_error_handler(
        request: Request,
        exc: ExecutionBoundaryError,
    ) -> JSONResponse:
        del request
        return JSONResponse(status_code=exc.status_code, content=exc.as_dict())

    @app.exception_handler(RequestLimitError)
    async def request_limit_error_handler(
        request: Request,
        exc: RequestLimitError,
    ) -> JSONResponse:
        del request
        return JSONResponse(status_code=413, content=exc.as_dict())

    @app.get("/healthz")
    def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "service": "starshine-server",
            "api_version": API_VERSION,
            "core_version": starshine_geo.__version__,
        }

    @app.get("/api/v1/operators")
    def operators() -> dict[str, Any]:
        return starshine_geo.operator_catalog()

    @app.get("/api/v1/limits")
    def limits() -> dict[str, Any]:
        return {
            "inline_preflight": inline_preflight_limits(),
            "inline_execution": execution_limits(),
            "workflow_execution_enabled": True,
        }

    @app.post("/api/v1/workflows/validate")
    def validate(request: WorkflowRequest) -> dict[str, Any]:
        starshine_geo.validate_workflow(request.workflow, request.layer_names)
        return {
            "valid": True,
            "workflow_version": request.workflow["version"],
        }

    @app.post("/api/v1/workflows/plan")
    def plan(request: WorkflowRequest) -> dict[str, Any]:
        return starshine_geo.plan_workflow(request.workflow, request.layer_names)

    @app.post("/api/v1/workflows/preflight")
    def preflight(request: InlinePreflightRequest) -> dict[str, Any]:
        enforce_inline_preflight_limits(request.workflow, request.layers)
        return starshine_geo.preflight_workflow_inputs(request.workflow, request.layers)

    @app.post("/api/v1/workflows/execute")
    def execute(request: InlineExecutionRequest) -> dict[str, Any]:
        return execute_inline_workflow(
            request.workflow,
            request.layers,
            output_layer=request.output_layer,
        )

    return app


__all__ = ["API_VERSION", "create_app"]

from __future__ import annotations

from typing import Any

import starshine_geo
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

API_VERSION = 1


class WorkflowRequest(BaseModel):
    """Transport-only envelope for data-free Workflow review endpoints."""

    model_config = ConfigDict(extra="forbid")

    workflow: dict[str, Any]
    layer_names: list[str] = Field(default_factory=list)


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


def create_app() -> FastAPI:
    """Create the Starshine HTTP adapter using only public starshine_geo APIs."""
    app = FastAPI(
        title="Starshine Server",
        version=starshine_geo.__version__,
        description=(
            "Thin HTTP adapter for the auditable Starshine Geo workflow core. "
            "The 0.8A surface is intentionally data-free and read-only."
        ),
        docs_url="/api/docs",
        redoc_url=None,
        openapi_url="/api/openapi.json",
    )

    @app.exception_handler(starshine_geo.WorkflowValidationError)
    async def workflow_validation_error_handler(
        request: Request,
        exc: starshine_geo.WorkflowValidationError,
    ) -> JSONResponse:
        del request
        return _workflow_error_response(exc)

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

    return app


__all__ = ["API_VERSION", "WorkflowRequest", "create_app"]

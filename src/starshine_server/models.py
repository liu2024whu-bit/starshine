from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class WorkflowRequest(BaseModel):
    """Transport-only envelope for data-free Workflow review endpoints."""

    model_config = ConfigDict(extra="forbid")

    workflow: dict[str, Any]
    layer_names: list[str] = Field(default_factory=list)


class InlinePreflightRequest(BaseModel):
    """Bounded in-memory inputs for canonical Core Preflight."""

    model_config = ConfigDict(extra="forbid")

    workflow: dict[str, Any]
    layers: dict[str, dict[str, Any]] = Field(min_length=1)


__all__ = ["InlinePreflightRequest", "WorkflowRequest"]

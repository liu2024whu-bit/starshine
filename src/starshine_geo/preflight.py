from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ._preflight_model import WORKFLOW_PREFLIGHT_VERSION, WorkflowPreflight
from ._preflight_report import build_workflow_preflight_report
from ._preflight_render import (
    render_workflow_preflight_markdown as _render_workflow_preflight_markdown,
)
from .geojson import FeatureCollection


def preflight_workflow_inputs(
    workflow: dict[str, Any],
    layers: Mapping[str, FeatureCollection],
) -> WorkflowPreflight:
    """Check loaded external layers against planner-derived workflow contracts.

    Structural validation, ordering, defaults, and input provenance come from the canonical planner
    through ``build_workflow_contract``. This function validates and inspects external collections
    but never executes a spatial operator or creates produced layers.
    """
    return build_workflow_preflight_report(workflow, layers)


def render_workflow_preflight_markdown(report: WorkflowPreflight) -> str:
    """Render a deterministic Markdown summary of actual workflow input checks."""
    return _render_workflow_preflight_markdown(report)


__all__ = [
    "WORKFLOW_PREFLIGHT_VERSION",
    "WorkflowPreflight",
    "preflight_workflow_inputs",
    "render_workflow_preflight_markdown",
]

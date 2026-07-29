from __future__ import annotations

from typing import Any

WORKFLOW_PREFLIGHT_VERSION = 1
WorkflowPreflight = dict[str, Any]

REMAINING_CHECKS = (
    "CRS equivalence involving a layer produced by an earlier step remains deferred to execution.",
    "Produced-layer geometry and property contracts can only be checked after their producer runs.",
    (
        "Spatial relationships, distances, ambiguity outcomes, and empty results require "
        "operator execution."
    ),
    "Output feature counts and post-execution manifest digests require running the workflow.",
)

__all__ = ["REMAINING_CHECKS", "WORKFLOW_PREFLIGHT_VERSION", "WorkflowPreflight"]

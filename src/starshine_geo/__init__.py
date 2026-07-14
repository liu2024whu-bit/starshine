"""Public geospatial workflow core for Starshine."""

from ._version import __version__
from .errors import WorkflowDiagnostic, WorkflowValidationError
from .geopackage import list_geopackage_layers, read_geopackage, write_geopackage
from .inspection import inspect_feature_collection
from .manifest import build_manifest, digest_json
from .operator_registry import OPERATOR_REGISTRY, operator_catalog
from .planning import WORKFLOW_PLAN_VERSION, plan_workflow
from .operators import (
    buffer_features,
    clip_features,
    dissolve_features,
    reproject_features,
    summarize_points_within,
    validate_feature_collection,
)
from .workflow import run_workflow, validate_workflow

__all__ = [
    "WorkflowDiagnostic",
    "WorkflowValidationError",
    "OPERATOR_REGISTRY",
    "WORKFLOW_PLAN_VERSION",
    "__version__",
    "buffer_features",
    "clip_features",
    "build_manifest",
    "digest_json",
    "dissolve_features",
    "inspect_feature_collection",
    "operator_catalog",
    "plan_workflow",
    "list_geopackage_layers",
    "read_geopackage",
    "reproject_features",
    "run_workflow",
    "summarize_points_within",
    "validate_feature_collection",
    "validate_workflow",
    "write_geopackage",
]

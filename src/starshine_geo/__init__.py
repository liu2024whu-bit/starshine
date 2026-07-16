"""Public geospatial workflow core for Starshine."""

from ._version import __version__
from .errors import WorkflowDiagnostic, WorkflowValidationError
from .graph import (
    WORKFLOW_GRAPH_VERSION,
    build_workflow_graph,
    render_workflow_mermaid,
)
from .geopackage import list_geopackage_layers, read_geopackage, write_geopackage
from .inspection import inspect_feature_collection
from .manifest import build_manifest, digest_json
from .metrics import calculate_geometry_metrics
from .operator_registry import OPERATOR_REGISTRY, operator_catalog
from .planning import WORKFLOW_PLAN_VERSION, plan_workflow
from .operators import (
    buffer_features,
    clip_features,
    dissolve_features,
    join_points_to_polygons,
    nearest_features,
    reproject_features,
    summarize_points_within,
    validate_feature_collection,
)
from .workflow import run_workflow, validate_workflow

__all__ = [
    "WorkflowDiagnostic",
    "WorkflowValidationError",
    "OPERATOR_REGISTRY",
    "WORKFLOW_GRAPH_VERSION",
    "WORKFLOW_PLAN_VERSION",
    "__version__",
    "buffer_features",
    "clip_features",
    "calculate_geometry_metrics",
    "build_manifest",
    "build_workflow_graph",
    "digest_json",
    "dissolve_features",
    "join_points_to_polygons",
    "nearest_features",
    "inspect_feature_collection",
    "operator_catalog",
    "plan_workflow",
    "list_geopackage_layers",
    "read_geopackage",
    "render_workflow_mermaid",
    "reproject_features",
    "run_workflow",
    "summarize_points_within",
    "validate_feature_collection",
    "validate_workflow",
    "write_geopackage",
]

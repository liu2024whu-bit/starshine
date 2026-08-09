"""Public geospatial workflow core for Starshine."""

from ._version import __version__
from .contracts import (
    WORKFLOW_CONTRACT_VERSION,
    build_workflow_contract,
    render_workflow_contract_markdown,
)
from .errors import WorkflowDiagnostic, WorkflowValidationError
from .explain import (
    WORKFLOW_EXPLANATION_VERSION,
    explain_workflow,
    render_workflow_explanation_markdown,
)
from .geopackage import list_geopackage_layers, read_geopackage, write_geopackage
from .geometry_quality import (
    GEOMETRY_QUALITY_REPORT_VERSION,
    assess_geometry_quality,
    render_geometry_quality_markdown,
)
from .graph import (
    WORKFLOW_GRAPH_VERSION,
    build_workflow_graph,
    render_workflow_mermaid,
)
from .inspection import inspect_feature_collection
from .manifest import build_manifest, digest_json
from .metrics import calculate_geometry_metrics
from .operator_registry import OPERATOR_REGISTRY, operator_catalog
from .operators import (
    buffer_features,
    clip_features,
    dissolve_features,
    intersect_features,
    join_points_to_polygons,
    nearest_features,
    reproject_features,
    summarize_points_within,
    validate_feature_collection,
)
from .planning import WORKFLOW_PLAN_VERSION, plan_workflow
from .preflight import (
    WORKFLOW_PREFLIGHT_VERSION,
    preflight_workflow_inputs,
    render_workflow_preflight_markdown,
)
from .preflight_sarif import (
    SARIF_SCHEMA_URI,
    SARIF_VERSION,
    build_workflow_preflight_sarif,
)
from .workflow import run_workflow, validate_workflow

__all__ = [
    "GEOMETRY_QUALITY_REPORT_VERSION",
    "OPERATOR_REGISTRY",
    "SARIF_SCHEMA_URI",
    "SARIF_VERSION",
    "WORKFLOW_CONTRACT_VERSION",
    "WORKFLOW_EXPLANATION_VERSION",
    "WORKFLOW_GRAPH_VERSION",
    "WORKFLOW_PLAN_VERSION",
    "WORKFLOW_PREFLIGHT_VERSION",
    "WorkflowDiagnostic",
    "WorkflowValidationError",
    "__version__",
    "assess_geometry_quality",
    "buffer_features",
    "build_manifest",
    "build_workflow_contract",
    "build_workflow_graph",
    "build_workflow_preflight_sarif",
    "calculate_geometry_metrics",
    "clip_features",
    "digest_json",
    "dissolve_features",
    "explain_workflow",
    "inspect_feature_collection",
    "intersect_features",
    "join_points_to_polygons",
    "list_geopackage_layers",
    "nearest_features",
    "operator_catalog",
    "plan_workflow",
    "preflight_workflow_inputs",
    "read_geopackage",
    "render_geometry_quality_markdown",
    "render_workflow_contract_markdown",
    "render_workflow_explanation_markdown",
    "render_workflow_mermaid",
    "render_workflow_preflight_markdown",
    "reproject_features",
    "run_workflow",
    "summarize_points_within",
    "validate_feature_collection",
    "validate_workflow",
    "write_geopackage",
]

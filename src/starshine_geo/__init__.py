"""Public geospatial workflow core for Starshine."""

from ._version import __version__
from .errors import WorkflowDiagnostic, WorkflowValidationError
from .geopackage import list_geopackage_layers, read_geopackage, write_geopackage
from .inspection import inspect_feature_collection
from .manifest import build_manifest, digest_json
from .operators import (
    buffer_features,
    dissolve_features,
    summarize_points_within,
    validate_feature_collection,
)
from .workflow import run_workflow, validate_workflow

__all__ = [
    "WorkflowDiagnostic",
    "WorkflowValidationError",
    "__version__",
    "buffer_features",
    "build_manifest",
    "digest_json",
    "dissolve_features",
    "inspect_feature_collection",
    "list_geopackage_layers",
    "read_geopackage",
    "run_workflow",
    "summarize_points_within",
    "validate_feature_collection",
    "validate_workflow",
    "write_geopackage",
]

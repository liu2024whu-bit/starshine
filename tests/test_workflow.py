import pytest

from starshine_geo.errors import UnsupportedOperationError, ValidationError
from starshine_geo.workflow import run_workflow


LAYERS = {
    "zones": {
        "type": "FeatureCollection",
        "features": [{
            "type": "Feature",
            "properties": {"id": "one"},
            "geometry": {"type": "Polygon", "coordinates": [[[0,0],[2,0],[2,2],[0,2],[0,0]]]},
        }],
    },
    "sites": {
        "type": "FeatureCollection",
        "features": [{
            "type": "Feature",
            "properties": {},
            "geometry": {"type": "Point", "coordinates": [1,1]},
        }],
    },
}


def test_workflow_executes_registered_operator():
    result = run_workflow({
        "version": 1,
        "steps": [{
            "operation": "summarize_points_within",
            "inputs": {"polygons": "zones", "points": "sites"},
            "parameters": {},
            "output": "summary",
        }],
    }, LAYERS)
    assert result["summary"]["features"][0]["properties"]["point_count"] == 1


def test_workflow_rejects_dynamic_operation():
    with pytest.raises(UnsupportedOperationError):
        run_workflow({"version": 1, "steps": [{"operation": "eval", "output": "x"}]}, LAYERS)


def test_workflow_does_not_overwrite_input_layers():
    with pytest.raises(ValidationError, match="overwrite"):
        run_workflow({
            "version": 1,
            "steps": [{
                "operation": "summarize_points_within",
                "inputs": {"polygons": "zones", "points": "sites"},
                "output": "zones",
            }],
        }, LAYERS)

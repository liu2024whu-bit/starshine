from __future__ import annotations

import pytest
from shapely.geometry import shape

from starshine_geo import clip_features, run_workflow
from starshine_geo.errors import ValidationError, WorkflowValidationError
from starshine_geo.workflow import validate_workflow

CRS = "EPSG:3857"


def _feature(geometry, **properties):
    return {"type": "Feature", "properties": properties, "geometry": geometry}


def _collection(features, *, crs=CRS):
    result = {"type": "FeatureCollection", "features": features}
    if crs is not None:
        result["starshine:crs"] = crs
    return result


def _square(min_x, min_y, max_x, max_y):
    return {
        "type": "Polygon",
        "coordinates": [
            [
                [min_x, min_y],
                [max_x, min_y],
                [max_x, max_y],
                [min_x, max_y],
                [min_x, min_y],
            ]
        ],
    }


def test_clip_preserves_order_properties_and_input_crs():
    source = _collection(
        [
            _feature(_square(0, 0, 10, 10), id="west", rank=1),
            _feature(_square(20, 0, 30, 10), id="east", rank=2),
            _feature(_square(40, 0, 50, 10), id="outside", rank=3),
        ]
    )
    mask = _collection([_feature(_square(5, -5, 25, 15), mask_id="study-area")])

    result = clip_features(source, mask)

    assert result["starshine:crs"] == CRS
    assert [feature["properties"]["id"] for feature in result["features"]] == [
        "west",
        "east",
    ]
    assert [feature["properties"]["rank"] for feature in result["features"]] == [1, 2]
    assert [shape(feature["geometry"]).bounds for feature in result["features"]] == [
        (5.0, 0.0, 10.0, 10.0),
        (20.0, 0.0, 25.0, 10.0),
    ]


def test_clip_retains_non_empty_boundary_intersections():
    source = _collection(
        [
            _feature({"type": "Point", "coordinates": [0, 5]}, id="boundary"),
            _feature({"type": "Point", "coordinates": [5, 5]}, id="inside"),
            _feature({"type": "Point", "coordinates": [20, 20]}, id="outside"),
        ]
    )
    mask = _collection([_feature(_square(0, 0, 10, 10))])

    result = clip_features(source, mask)

    assert [feature["properties"]["id"] for feature in result["features"]] == [
        "boundary",
        "inside",
    ]
    assert [feature["geometry"]["type"] for feature in result["features"]] == [
        "Point",
        "Point",
    ]


def test_clip_empty_mask_returns_empty_collection_with_input_crs():
    source = _collection([_feature(_square(0, 0, 10, 10), id="source")])
    mask = _collection([])

    assert clip_features(source, mask) == {
        "type": "FeatureCollection",
        "starshine:crs": CRS,
        "features": [],
    }


def test_clip_rejects_non_polygon_mask():
    source = _collection([_feature(_square(0, 0, 10, 10), id="source")])
    mask = _collection([_feature({"type": "Point", "coordinates": [5, 5]})])

    with pytest.raises(ValidationError, match="Polygon or MultiPolygon"):
        clip_features(source, mask)


@pytest.mark.parametrize(
    ("source_crs", "mask_crs", "message"),
    [
        (None, CRS, "input collection must declare"),
        (CRS, None, "mask collection must declare"),
        (CRS, "EPSG:4326", "equivalent CRS"),
    ],
)
def test_clip_requires_explicit_equivalent_crs(source_crs, mask_crs, message):
    source = _collection([_feature(_square(0, 0, 10, 10))], crs=source_crs)
    mask = _collection([_feature(_square(0, 0, 10, 10))], crs=mask_crs)

    with pytest.raises(ValidationError, match=message):
        clip_features(source, mask)


def test_clip_workflow_runs_through_registry():
    source = _collection([_feature(_square(0, 0, 10, 10), id="source")])
    mask = _collection([_feature(_square(5, -5, 15, 15), id="mask")])
    workflow = {
        "version": 1,
        "steps": [
            {
                "operation": "clip",
                "inputs": {"input": "source", "mask": "mask"},
                "parameters": {},
                "output": "clipped",
            }
        ],
    }

    result = run_workflow(workflow, {"source": source, "mask": mask})["clipped"]

    assert len(result["features"]) == 1
    assert shape(result["features"][0]["geometry"]).bounds == (5.0, 0.0, 10.0, 10.0)


def test_clip_workflow_rejects_parameters_before_execution():
    workflow = {
        "version": 1,
        "steps": [
            {
                "operation": "clip",
                "inputs": {"input": "source", "mask": "mask"},
                "parameters": {"repair": True},
                "output": "clipped",
            }
        ],
    }

    with pytest.raises(WorkflowValidationError) as exc_info:
        validate_workflow(workflow, {"source", "mask"})

    assert exc_info.value.diagnostic.as_dict() == {
        "code": "unexpected_parameter",
        "message": "unexpected parameter for clip: repair",
        "path": "steps[0].parameters.repair",
        "step_index": 0,
        "operation": "clip",
    }

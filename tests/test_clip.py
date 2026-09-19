from __future__ import annotations

import pytest
from shapely.geometry import shape

from starshine_geo import (
    build_workflow_contract,
    clip_features,
    difference_features,
    preflight_workflow_inputs,
    run_workflow,
)
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

def test_difference_handles_partial_disjoint_and_complete_erase_deterministically():
    source = _collection(
        [
            _feature(_square(0, 0, 10, 10), id="partial", rank=1),
            _feature(_square(20, 0, 30, 10), id="disjoint", rank=2),
            _feature(_square(40, 0, 50, 10), id="erased", rank=3),
        ]
    )
    mask = _collection(
        [
            _feature(_square(5, -5, 10, 15), mask_id="partial-cut"),
            _feature(_square(35, -5, 55, 15), mask_id="full-cut"),
        ]
    )

    first = difference_features(source, mask)
    second = difference_features(source, mask)

    assert first == second
    assert first["starshine:crs"] == CRS
    assert [feature["properties"]["id"] for feature in first["features"]] == [
        "partial",
        "disjoint",
    ]
    assert [feature["properties"]["rank"] for feature in first["features"]] == [1, 2]
    assert [shape(feature["geometry"]).bounds for feature in first["features"]] == [
        (0.0, 0.0, 5.0, 10.0),
        (20.0, 0.0, 30.0, 10.0),
    ]
    assert [shape(feature["geometry"]).area for feature in first["features"]] == [50.0, 100.0]


def test_difference_empty_mask_preserves_geometry_without_aliasing_inputs():
    source = _collection([_feature(_square(0, 0, 10, 10), id="source")])
    result = difference_features(source, _collection([]))

    assert result["starshine:crs"] == CRS
    assert shape(result["features"][0]["geometry"]).equals(shape(source["features"][0]["geometry"]))
    assert result["features"][0]["properties"] == {"id": "source"}

    result["features"][0]["properties"]["id"] = "changed"
    assert source["features"][0]["properties"]["id"] == "source"


@pytest.mark.parametrize(
    ("source_crs", "mask_crs", "mask_geometry", "message"),
    [
        (None, CRS, _square(0, 0, 10, 10), "input collection must declare"),
        (CRS, None, _square(0, 0, 10, 10), "mask collection must declare"),
        (CRS, "EPSG:4326", _square(0, 0, 10, 10), "equivalent CRS"),
        (CRS, CRS, {"type": "Point", "coordinates": [5, 5]}, "Polygon or MultiPolygon"),
    ],
)
def test_difference_requires_explicit_equivalent_crs_and_polygon_mask(
    source_crs,
    mask_crs,
    mask_geometry,
    message,
):
    source = _collection([_feature(_square(0, 0, 10, 10))], crs=source_crs)
    mask = _collection([_feature(mask_geometry)], crs=mask_crs)

    with pytest.raises(ValidationError, match=message):
        difference_features(source, mask)


def test_difference_workflow_contract_and_preflight_share_registry_contract():
    source = _collection([_feature(_square(0, 0, 10, 10), id="source")])
    mask = _collection([_feature(_square(5, -5, 15, 15), id="mask")])
    workflow = {
        "version": 1,
        "steps": [
            {
                "operation": "difference",
                "inputs": {"input": "source", "mask": "mask"},
                "parameters": {},
                "output": "remaining",
            }
        ],
    }

    direct = difference_features(source, mask)
    via_workflow = run_workflow(workflow, {"source": source, "mask": mask})["remaining"]
    assert via_workflow == direct

    contract = build_workflow_contract(workflow, {"source", "mask"})
    source_use = next(layer for layer in contract["layers"] if layer["name"] == "source")["uses"][0]
    mask_use = next(layer for layer in contract["layers"] if layer["name"] == "mask")["uses"][0]
    assert source_use["crs"] == {"mode": "declared", "equivalent_to_layer": "mask"}
    assert mask_use["geometry_types"] == ["Polygon", "MultiPolygon"]
    assert mask_use["crs"] == {"mode": "declared", "equivalent_to_layer": "source"}

    preflight = preflight_workflow_inputs(workflow, {"source": source, "mask": mask})
    assert preflight["valid"] is True
    assert preflight["error_count"] == 0


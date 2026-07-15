from copy import deepcopy

import pytest

from starshine_geo import nearest_features, plan_workflow, run_workflow
from starshine_geo.errors import ValidationError, WorkflowValidationError


def _collection(features, crs="EPSG:3857"):
    value = {"type": "FeatureCollection", "features": features}
    if crs is not None:
        value["starshine:crs"] = crs
    return value


def _point(x, y, **properties):
    return {
        "type": "Feature",
        "properties": properties,
        "geometry": {"type": "Point", "coordinates": [x, y]},
    }


def _workflow(parameters=None):
    return {
        "version": 1,
        "steps": [
            {
                "operation": "nearest",
                "inputs": {"source": "sources", "candidates": "candidates"},
                "parameters": parameters or {"candidate_id_field": "candidate_id"},
                "output": "matched",
            }
        ],
    }


def test_nearest_preserves_source_order_properties_and_uses_first_tie():
    source = _collection(
        [
            _point(0, 0, source_id="origin"),
            _point(9, 0, source_id="east"),
        ]
    )
    candidates = _collection(
        [
            _point(-1, 0, candidate_id="west-first"),
            _point(1, 0, candidate_id="east-second"),
            _point(10, 0, candidate_id="far-east"),
        ]
    )

    result = nearest_features(source, candidates, candidate_id_field="candidate_id")

    assert result["starshine:crs"] == "EPSG:3857"
    assert [feature["properties"]["source_id"] for feature in result["features"]] == [
        "origin",
        "east",
    ]
    assert [feature["properties"]["nearest_id"] for feature in result["features"]] == [
        "west-first",
        "far-east",
    ]
    assert [feature["properties"]["nearest_distance"] for feature in result["features"]] == [
        1.0,
        1.0,
    ]
    assert [feature["geometry"]["type"] for feature in result["features"]] == ["Point", "Point"]
    assert [tuple(feature["geometry"]["coordinates"]) for feature in result["features"]] == [
        (0.0, 0.0),
        (9.0, 0.0),
    ]


def test_nearest_supports_custom_fields_and_inclusive_max_distance():
    source = _collection([_point(0, 0, source_id="a"), _point(20, 0, source_id="b")])
    candidates = _collection([_point(5, 0, code=7)])

    result = nearest_features(
        source,
        candidates,
        candidate_id_field="code",
        nearest_id_field="facility",
        distance_field="distance_m",
        max_distance=5,
    )

    assert result["features"][0]["properties"] == {
        "source_id": "a",
        "facility": 7,
        "distance_m": 5.0,
    }
    assert result["features"][1]["properties"] == {
        "source_id": "b",
        "facility": None,
        "distance_m": None,
    }


def test_empty_candidates_produce_explicit_null_matches():
    result = nearest_features(
        _collection([_point(0, 0, source_id="only")]),
        _collection([]),
        candidate_id_field="candidate_id",
    )

    assert result["features"][0]["properties"] == {
        "source_id": "only",
        "nearest_id": None,
        "nearest_distance": None,
    }


@pytest.mark.parametrize("missing_label", ["source", "candidates"])
def test_nearest_requires_declared_crs(missing_label):
    source = _collection([_point(0, 0, source_id="source")])
    candidates = _collection([_point(1, 0, candidate_id="candidate")])
    if missing_label == "source":
        source.pop("starshine:crs")
    else:
        candidates.pop("starshine:crs")

    with pytest.raises(ValidationError, match=f"{missing_label} collection must declare"):
        nearest_features(source, candidates, candidate_id_field="candidate_id")


def test_nearest_requires_equivalent_projected_crs_values():
    source = _collection([_point(0, 0, source_id="source")], crs="EPSG:3857")
    candidates = _collection([_point(1, 0, candidate_id="candidate")], crs="EPSG:32650")
    with pytest.raises(ValidationError, match="equivalent CRS"):
        nearest_features(source, candidates, candidate_id_field="candidate_id")

    geographic = _collection([_point(0, 0, source_id="source")], crs="EPSG:4326")
    geographic_candidates = _collection(
        [_point(1, 0, candidate_id="candidate")], crs="EPSG:4326"
    )
    with pytest.raises(ValidationError, match="projected CRS"):
        nearest_features(
            geographic,
            geographic_candidates,
            candidate_id_field="candidate_id",
        )


@pytest.mark.parametrize(
    ("candidate_features", "message"),
    [
        ([_point(1, 0)], "missing required property"),
        (
            [
                _point(1, 0, candidate_id="duplicate"),
                _point(2, 0, candidate_id="duplicate"),
            ],
            "duplicate candidate identifier",
        ),
        ([_point(1, 0, candidate_id={"nested": True})], "JSON scalar"),
        ([_point(1, 0, candidate_id=None)], "non-null JSON scalar"),
    ],
)
def test_nearest_rejects_invalid_candidate_identifiers(candidate_features, message):
    with pytest.raises(ValidationError, match=message):
        nearest_features(
            _collection([_point(0, 0, source_id="source")]),
            _collection(candidate_features),
            candidate_id_field="candidate_id",
        )


@pytest.mark.parametrize("value", [-1, float("inf"), float("nan"), True, "10"])
def test_nearest_rejects_invalid_max_distance(value):
    with pytest.raises(ValidationError, match="max_distance"):
        nearest_features(
            _collection([_point(0, 0, source_id="source")]),
            _collection([_point(1, 0, candidate_id="candidate")]),
            candidate_id_field="candidate_id",
            max_distance=value,
        )


def test_nearest_rejects_ambiguous_or_existing_output_fields():
    source = _collection([_point(0, 0, source_id="source", nearest_id="occupied")])
    candidates = _collection([_point(1, 0, candidate_id="candidate")])
    with pytest.raises(ValidationError, match="already contains output property"):
        nearest_features(source, candidates, candidate_id_field="candidate_id")

    clean_source = _collection([_point(0, 0, source_id="source")])
    with pytest.raises(ValidationError, match="must be different"):
        nearest_features(
            clean_source,
            candidates,
            candidate_id_field="candidate_id",
            nearest_id_field="match",
            distance_field="match",
        )


def test_nearest_workflow_and_plan_share_registry_defaults():
    source = _collection([_point(0, 0, source_id="source")])
    candidates = _collection([_point(3, 4, candidate_id="five-away")])
    workflow = _workflow()

    result = run_workflow(workflow, {"sources": source, "candidates": candidates})
    properties = result["matched"]["features"][0]["properties"]
    assert properties["nearest_id"] == "five-away"
    assert properties["nearest_distance"] == 5.0

    plan = plan_workflow(workflow, {"sources", "candidates", "unused"})
    step = plan["steps"][0]
    assert step["parameters"] == {
        "candidate_id_field": "candidate_id",
        "distance_field": "nearest_distance",
        "nearest_id_field": "nearest_id",
        "max_distance": None,
    }
    assert step["parameter_sources"] == {
        "candidate_id_field": "provided",
        "distance_field": "default",
        "nearest_id_field": "default",
        "max_distance": "default",
    }
    assert plan["required_external_layers"] == ["candidates", "sources"]
    assert plan["unused_external_layers"] == ["unused"]


def test_nearest_workflow_parameter_validation_is_stable():
    workflow = _workflow({"candidate_id_field": "candidate_id", "max_distance": -1})
    with pytest.raises(WorkflowValidationError) as exc_info:
        plan_workflow(workflow, {"sources", "candidates"})

    assert exc_info.value.diagnostic.as_dict() == {
        "code": "invalid_parameter",
        "message": "nearest.max_distance must be a non-negative finite number or null",
        "path": "steps[0].parameters.max_distance",
        "step_index": 0,
        "operation": "nearest",
    }


def test_nearest_does_not_mutate_inputs():
    source = _collection([_point(0, 0, source_id="source")])
    candidates = _collection([_point(1, 0, candidate_id="candidate")])
    source_before = deepcopy(source)
    candidates_before = deepcopy(candidates)

    nearest_features(source, candidates, candidate_id_field="candidate_id")

    assert source == source_before
    assert candidates == candidates_before

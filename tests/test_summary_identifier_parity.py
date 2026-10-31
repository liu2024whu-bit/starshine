from __future__ import annotations

import sys

import pytest

from starshine_geo.errors import ValidationError
from starshine_geo.operators import summarize_points_within
from starshine_geo.preflight import preflight_workflow_inputs

WORKFLOW = {"version": 1, "steps": [{
    "operation": "summarize_points_within", "inputs": {"polygons": "z", "points": "p"},
    "output": "result",
}]}
POINTS = {"type": "FeatureCollection", "features": []}


def polygons(ids):
    return {"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"id": value}, "geometry": {
            "type": "Polygon", "coordinates": [[[0, 0], [2, 0], [2, 2], [0, 0]]],
        }} for value in ids
    ]}


@pytest.mark.parametrize("ids", [[["a"], ["b"]], [{"a": 1}, {"a": 2}], [True, 1, 1.0]])
def test_summary_accepts_identifiers_distinguished_by_preflight(ids):
    source = polygons(ids)
    assert preflight_workflow_inputs(WORKFLOW, {"z": source, "p": POINTS})["valid"]
    result = summarize_points_within(source, POINTS)
    assert [feature["properties"]["id"] for feature in result["features"]] == ids
    assert [feature["properties"]["point_count"] for feature in result["features"]] == [0]*len(ids)


@pytest.mark.parametrize("ids", [
    [["private-value"], ["private-value"]],
    [{"a": 1, "b": 2}, {"b": 2, "a": 1}],
    [True, True], [1, 1], [1.0, 1.0],
])
def test_summary_rejects_duplicates_in_agreement_with_preflight(ids):
    source = polygons(ids)
    report = preflight_workflow_inputs(WORKFLOW, {"z": source, "p": POINTS})
    assert not report["valid"]
    assert any(finding["code"] == "duplicate_required_field" for finding in report["findings"])
    with pytest.raises(ValidationError, match="duplicate polygon identifier") as exc:
        summarize_points_within(source, POINTS)
    assert "private-value" not in str(exc.value)


@pytest.mark.parametrize("value", [None, float("nan"), float("inf"), {"nested": float("inf")}])
def test_summary_rejects_null_or_nonfinite_identifiers_like_preflight(value):
    source = polygons([value])
    report = preflight_workflow_inputs(WORKFLOW, {"z": source, "p": POINTS})
    assert not report["valid"]
    with pytest.raises(ValidationError):
        summarize_points_within(source, POINTS)


def test_summary_rejects_cyclic_identifier_without_echoing_value():
    value = ["private-value"]
    value.append(value)
    with pytest.raises(ValidationError, match="finite JSON value") as exc:
        summarize_points_within(polygons([value]), POINTS)
    assert "private-value" not in str(exc.value)


def test_unique_key_normalizes_encoder_recursion_failure(monkeypatch):
    import starshine_geo._json_identity as identity_module

    def failed_encoder(*args, **kwargs):
        raise RecursionError("synthetic encoder nesting limit")

    monkeypatch.setattr(identity_module.json, "dumps", failed_encoder)
    assert identity_module.json_unique_key(["value"]) is None


def test_summary_rejects_excessively_nested_identifier_at_collection_boundary():
    value = ["private-value"]
    for _ in range(sys.getrecursionlimit() * 2):
        value = [value]
    with pytest.raises(ValidationError, match="nesting depth") as exc:
        summarize_points_within(polygons([value]), POINTS)
    assert "private-value" not in str(exc.value)

import json
from copy import deepcopy

import pytest

from starshine_geo import ValidationError, digest_json, verify_result_manifest
from starshine_geo.cli import main
from starshine_geo.manifest import build_manifest

POINTS = {
    "type": "FeatureCollection",
    "starshine:crs": "EPSG:3857",
    "features": [
        {
            "type": "Feature",
            "properties": {"name": "site-a"},
            "geometry": {"type": "Point", "coordinates": [1, 1]},
        }
    ],
}

ZONES = {
    "type": "FeatureCollection",
    "starshine:crs": "EPSG:3857",
    "features": [
        {
            "type": "Feature",
            "properties": {"id": "zone-a"},
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[0, 0], [2, 0], [2, 2], [0, 2], [0, 0]]],
            },
        }
    ],
}

WORKFLOW = {
    "version": 1,
    "steps": [
        {
            "operation": "summarize_points_within",
            "inputs": {"polygons": "zones", "points": "sites"},
            "parameters": {"polygon_id_field": "id", "count_field": "site_count"},
            "output": "summary",
        }
    ],
}


def _manifest(workflow=WORKFLOW, points=POINTS):
    return build_manifest(
        workflow,
        {"sites": points, "zones": ZONES},
        output_layer_name="summary",
        output_layer=ZONES,
        starshine_version="test-version",
    )


def test_manifest_digests_are_deterministic_for_equivalent_json():
    reordered_workflow = {
        "steps": deepcopy(WORKFLOW["steps"]),
        "version": 1,
    }
    reordered_points = {
        "features": deepcopy(POINTS["features"]),
        "starshine:crs": "EPSG:3857",
        "type": "FeatureCollection",
    }

    first = _manifest()
    second = _manifest(reordered_workflow, reordered_points)

    assert first["workflow_digest"] == second["workflow_digest"]
    assert first["input_layers"]["sites"]["digest"] == second["input_layers"]["sites"]["digest"]


def test_manifest_detects_changed_input_content():
    changed_points = deepcopy(POINTS)
    changed_points["features"][0]["properties"]["name"] = "site-b"

    first = _manifest()
    second = _manifest(points=changed_points)

    assert first["input_layers"]["sites"]["digest"] != second["input_layers"]["sites"]["digest"]


def test_manifest_redacts_credentials_and_paths():
    workflow = deepcopy(WORKFLOW)
    workflow["steps"][0]["parameters"].update(
        {
            "api_key": "sk-private-value",
            "cache_path": "C:\\Users\\maintainer\\private.json",
            "connection": "postgresql://user:password@localhost/database",
            "temporary": "/home/maintainer/private.json",
        }
    )

    serialized = json.dumps(_manifest(workflow), ensure_ascii=False)

    assert "sk-private-value" not in serialized
    assert "C:\\Users\\maintainer" not in serialized
    assert "user:password" not in serialized
    assert "/home/maintainer" not in serialized
    assert "<redacted>" in serialized
    assert "<redacted-path>" in serialized


def test_manifest_redacts_absolute_layer_names():
    manifest = build_manifest(
        WORKFLOW,
        {"C:\\Users\\maintainer\\sites.geojson": POINTS},
        output_layer_name="/home/maintainer/summary.geojson",
        output_layer=ZONES,
        starshine_version="test-version",
    )
    serialized = json.dumps(manifest, ensure_ascii=False)

    assert "C:\\Users\\maintainer" not in serialized
    assert "/home/maintainer" not in serialized
    assert "<redacted-input-layer-0>" in manifest["input_layers"]
    assert manifest["output_layer"]["name"] == "<redacted-output-layer-0>"


def test_cli_writes_manifest_only_when_requested(tmp_path):
    workflow_path = tmp_path / "workflow.json"
    zones_path = tmp_path / "zones.geojson"
    sites_path = tmp_path / "sites.geojson"
    output_path = tmp_path / "summary.geojson"
    manifest_path = tmp_path / "summary.manifest.json"

    workflow_path.write_text(json.dumps(WORKFLOW), encoding="utf-8")
    zones_path.write_text(json.dumps(ZONES), encoding="utf-8")
    sites_path.write_text(json.dumps(POINTS), encoding="utf-8")

    result = main(
        [
            "run",
            str(workflow_path),
            "--layer",
            f"zones={zones_path}",
            "--layer",
            f"sites={sites_path}",
            "--output-layer",
            "summary",
            "--output",
            str(output_path),
            "--manifest",
            str(manifest_path),
        ]
    )

    assert result == 0
    assert output_path.is_file()
    assert manifest_path.is_file()
    manifest_text = manifest_path.read_text(encoding="utf-8")
    assert str(tmp_path) not in manifest_text
    assert json.loads(manifest_text)["output_layer"]["name"] == "summary"


# Verification deliberately consumes only selected-output claims, never runs a workflow.


def test_verify_result_reordered_keys_and_no_mutation():
    manifest = _manifest()
    result = dict(reversed(list(ZONES.items())))
    before = deepcopy((result, manifest))
    report = verify_result_manifest(result, manifest)
    assert report == {
        "scope": "selected_output_only", "matched": True,
        "checks": {"content_digest": True, "declared_crs": True},
        "expected_digest": digest_json(ZONES), "actual_digest": digest_json(ZONES),
    }
    assert (result, manifest) == before


@pytest.mark.parametrize("change", ["properties", "coordinates", "crs", "array_order"])
def test_verify_result_detects_content_changes(change):
    result = deepcopy(ZONES)
    if change == "properties":
        result["features"][0]["properties"]["id"] = "changed"
    elif change == "coordinates":
        result["features"][0]["geometry"]["coordinates"][0][1][0] = 3
    elif change == "crs":
        result["starshine:crs"] = "EPSG:4326"
    else:
        result["features"][0]["geometry"]["coordinates"][0].reverse()
    report = verify_result_manifest(result, _manifest())
    assert not report["matched"]
    assert not report["checks"]["content_digest"]
    assert report["checks"]["declared_crs"] is (change != "crs")


@pytest.mark.parametrize("version", [1, 1.0])
def test_verify_result_accepts_numeric_v1(version):
    manifest = _manifest()
    manifest["manifest_version"] = version
    manifest["starshine_version"] = "different-producer-version"
    assert verify_result_manifest(ZONES, manifest)["matched"]


@pytest.mark.parametrize("version", [True, False, None, "1", 2, float("nan"), float("inf")])
def test_verify_result_rejects_invalid_version(version):
    manifest = _manifest()
    manifest["manifest_version"] = version
    with pytest.raises(ValidationError, match="version 1"):
        verify_result_manifest(ZONES, manifest)


@pytest.mark.parametrize("output", [None, [], {}, {"digest": "sha256:bad", "crs": None},
    {"digest": "SHA256:" + "a" * 64, "crs": None},
    {"digest": "sha256:" + "a" * 64},
    {"digest": "sha256:" + "a" * 64, "crs": True},
    {"digest": "sha256:" + "a" * 64, "crs": " "}])
def test_verify_result_rejects_malformed_claims(output):
    manifest = _manifest()
    manifest["output_layer"] = output
    with pytest.raises(ValidationError):
        verify_result_manifest(ZONES, manifest)


def test_verify_result_checks_crs_claim_independently():
    manifest = _manifest()
    manifest["output_layer"]["crs"] = "EPSG:4326"
    report = verify_result_manifest(ZONES, manifest)
    assert report["checks"] == {"content_digest": True, "declared_crs": False}
    assert not report["matched"]


@pytest.mark.parametrize("value", [float("inf"), float("nan"), object()])
def test_verify_result_rejects_non_json_values(value):
    result = deepcopy(ZONES)
    result["extra"] = value
    with pytest.raises(ValidationError):
        verify_result_manifest(result, _manifest())
    manifest = _manifest()
    manifest["extra"] = value
    with pytest.raises(ValidationError):
        verify_result_manifest(ZONES, manifest)


def test_verify_result_missing_crs_matches_null_claim():
    result = deepcopy(ZONES)
    del result["starshine:crs"]
    manifest = _manifest()
    manifest["output_layer"].update(digest=digest_json(result), crs=None)
    assert verify_result_manifest(result, manifest)["matched"]


@pytest.mark.parametrize("result", [[], {}, {"type": "Feature", "features": []},
    {"type": "FeatureCollection", "features": None}])
def test_verify_result_requires_collection_envelope(result):
    with pytest.raises(ValidationError):
        verify_result_manifest(result, _manifest())


def test_verify_result_cli_exit_codes_stdout_and_read_only(tmp_path, capsys, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("verification must not execute a workflow")
    monkeypatch.setattr("starshine_geo.cli.run_workflow", forbidden)
    result_path, manifest_path = tmp_path / "result.json", tmp_path / "manifest.json"
    result_path.write_text(json.dumps(ZONES))
    manifest_path.write_text(json.dumps(_manifest()))
    args = ["verify-result", str(result_path), "--manifest", str(manifest_path)]
    before = (result_path.read_bytes(), manifest_path.read_bytes())
    assert main(args) == 0
    captured = capsys.readouterr()
    assert json.loads(captured.out) == verify_result_manifest(ZONES, _manifest())
    assert captured.err == ""
    assert before == (result_path.read_bytes(), manifest_path.read_bytes())
    changed = deepcopy(ZONES)
    changed["features"] = []
    result_path.write_text(json.dumps(changed))
    assert main(args) == 1
    assert not json.loads(capsys.readouterr().out)["matched"]
    manifest_path.write_text('{}')
    assert main(args) == 2
    assert capsys.readouterr().out == ""
    manifest_path.write_bytes(b'\xff')
    assert main(args + ["--diagnostic-format", "json"]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert json.loads(captured.err)["error"]
    manifest_path.unlink()
    assert main(args) == 2

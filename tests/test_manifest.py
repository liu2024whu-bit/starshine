import json
from copy import deepcopy

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

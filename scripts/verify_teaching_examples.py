from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples" / "teaching"
STARSHINE = [sys.executable, "-m", "starshine_geo.cli"]


def _run(arguments: list[str], *, expected_returncode: int = 0) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        [*STARSHINE, *arguments],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != expected_returncode:
        raise RuntimeError(
            "teaching command returned an unexpected status\n"
            f"command: {[*STARSHINE, *arguments]!r}\n"
            f"expected: {expected_returncode}\n"
            f"actual: {result.returncode}\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )
    return result


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"expected an object in {path}")
    return value


def _verify_inspection_example() -> None:
    result = _run(["inspect", str(EXAMPLES / "projected-points.geojson")])
    actual = json.loads(result.stdout)
    expected = _read_json(EXAMPLES / "projected-points.inspection.json")
    if actual != expected:
        raise RuntimeError(f"projected-point inspection changed: {actual!r} != {expected!r}")


def _verify_projected_buffer_example() -> None:
    workflow = EXAMPLES / "buffer-projected-valid.workflow.json"
    source = EXAMPLES / "projected-points.geojson"

    validated = _run(["validate", str(workflow), "--layer-name", "points"])
    if validated.stdout.strip() != "valid":
        raise RuntimeError(f"unexpected valid-workflow output: {validated.stdout!r}")

    with tempfile.TemporaryDirectory(prefix="starshine-teaching-") as directory:
        root = Path(directory)
        output = root / "buffers.geojson"
        _run(
            [
                "run",
                str(workflow),
                "--layer",
                f"points={source}",
                "--output-layer",
                "buffers",
                "--output",
                str(output),
            ]
        )
        report = json.loads(_run(["inspect", str(output)]).stdout)
        expected_structure = {
            "bbox": [-25.0, -25.0, 225.0, 125.0],
            "declared_crs": "EPSG:3857",
            "feature_count": 3,
            "geometry_counts": {"Polygon": 3},
            "property_fields": [
                "id",
                "starshine:buffer_distance",
                "starshine:work_crs",
            ],
            "schema_version": 1,
        }
        for key, value in expected_structure.items():
            if report.get(key) != value:
                raise RuntimeError(
                    f"projected buffer produced an unexpected {key}: {report.get(key)!r}"
                )


def _verify_workflow_failure() -> None:
    result = _run(
        [
            "validate",
            str(EXAMPLES / "buffer-geographic-invalid.workflow.json"),
            "--layer-name",
            "points",
            "--diagnostic-format",
            "json",
        ],
        expected_returncode=2,
    )
    payload = json.loads(result.stderr)
    diagnostic = payload.get("diagnostic", {})
    if payload.get("error") != "workflow_validation":
        raise RuntimeError(f"unexpected geographic-buffer envelope: {payload!r}")
    if diagnostic.get("code") != "invalid_parameter":
        raise RuntimeError(f"unexpected geographic-buffer code: {diagnostic!r}")
    if diagnostic.get("path") != "steps[0].parameters.work_crs":
        raise RuntimeError(f"unexpected geographic-buffer path: {diagnostic!r}")
    if "projected CRS with linear units" not in diagnostic.get("message", ""):
        raise RuntimeError(f"unexpected geographic-buffer message: {diagnostic!r}")


def _verify_geojson_failure(filename: str, expected_message: str) -> None:
    result = _run(
        [
            "inspect",
            str(EXAMPLES / filename),
            "--diagnostic-format",
            "json",
        ],
        expected_returncode=2,
    )
    payload = json.loads(result.stderr)
    if payload != {"error": "starshine_error", "message": expected_message}:
        raise RuntimeError(f"unexpected failure for {filename}: {payload!r}")


def main() -> int:
    _verify_inspection_example()
    _verify_projected_buffer_example()
    _verify_workflow_failure()
    _verify_geojson_failure(
        "self-intersecting-polygon.geojson",
        "Feature 0 has topologically invalid geometry",
    )
    _verify_geojson_failure("empty-polygon.geojson", "Feature 0 has empty geometry")
    _verify_geojson_failure(
        "malformed-properties.geojson",
        "Feature 0.properties must be an object or null",
    )
    print("Verified six synthetic CRS and geometry teaching checks.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

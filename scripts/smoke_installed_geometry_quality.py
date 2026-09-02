from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from importlib.metadata import version
from pathlib import Path
from typing import Any

import starshine_geo

_PACKAGE_NAME = "starshine-geo"


def _run(command: list[str], *, expected_returncode: int) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(command, check=False, capture_output=True, text=True)
    if result.returncode != expected_returncode:
        raise RuntimeError(
            "command failed\n"
            f"command: {command!r}\n"
            f"expected return code: {expected_returncode}\n"
            f"actual return code: {result.returncode}\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )
    return result


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _collection() -> dict[str, Any]:
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {"name": "private-a"},
                "geometry": {"type": "Point", "coordinates": [1, 2]},
            },
            {
                "type": "Feature",
                "properties": {"name": "private-b"},
                "geometry": {"type": "Point", "coordinates": [1, 2]},
            },
            {
                "type": "Feature",
                "properties": {"name": "private-invalid"},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[0, 0], [2, 2], [0, 2], [2, 0], [0, 0]]],
                },
            },
        ],
    }


def main() -> int:
    installed_version = version(_PACKAGE_NAME)
    if starshine_geo.__version__ != installed_version:
        raise RuntimeError("top-level version does not match installed package metadata")
    if starshine_geo.GEOMETRY_QUALITY_REPORT_VERSION != 1:
        raise RuntimeError("unexpected installed geometry-quality report version")
    if not callable(starshine_geo.assess_geometry_quality):
        raise TypeError("installed wheel is missing assess_geometry_quality")
    if not callable(starshine_geo.render_geometry_quality_markdown):
        raise TypeError("installed wheel is missing render_geometry_quality_markdown")

    collection = _collection()
    direct_report = starshine_geo.assess_geometry_quality(collection)
    if direct_report.get("valid") is not False:
        raise RuntimeError(f"expected a failing geometry-quality report: {direct_report}")
    if direct_report.get("duplicate_geometry_group_count") != 1:
        raise RuntimeError(f"duplicate geometry was not reported: {direct_report}")
    if direct_report.get("invalid_geometry_count") != 1:
        raise RuntimeError(f"invalid geometry count changed: {direct_report}")
    serialized = json.dumps(direct_report, sort_keys=True)
    if "private-a" in serialized or "[1 1]" in serialized or '"coordinates"' in serialized:
        raise RuntimeError("geometry-quality report exposed feature values or coordinates")
    markdown = starshine_geo.render_geometry_quality_markdown(direct_report)
    if "Status: **FAIL**" not in markdown or "Self-intersection" not in markdown:
        raise RuntimeError(f"unexpected geometry-quality Markdown: {markdown}")

    starshine_command = shutil.which("starshine")
    if starshine_command is None:
        raise RuntimeError("the installed wheel did not provide the starshine console command")

    with tempfile.TemporaryDirectory(prefix="starshine-quality-smoke-") as directory:
        root = Path(directory)
        source = root / "quality.geojson"
        json_output = root / "quality.report.json"
        markdown_output = root / "quality.report.md"
        _write_json(source, collection)

        json_result = _run(
            [
                starshine_command,
                "quality",
                str(source),
                "--format",
                "json",
                "--output",
                str(json_output),
            ],
            expected_returncode=1,
        )
        if json_result.stdout.strip() != str(json_output) or json_result.stderr:
            raise RuntimeError(f"unexpected geometry-quality JSON CLI streams: {json_result}")
        if json.loads(json_output.read_text(encoding="utf-8")) != direct_report:
            raise RuntimeError("installed geometry-quality CLI differs from the public API")

        markdown_result = _run(
            [starshine_command, "quality", str(source), "--output", str(markdown_output)],
            expected_returncode=1,
        )
        if markdown_result.stdout.strip() != str(markdown_output) or markdown_result.stderr:
            raise RuntimeError(
                f"unexpected geometry-quality Markdown CLI streams: {markdown_result}"
            )
        if markdown_output.read_text(encoding="utf-8") != markdown:
            raise RuntimeError(
                "installed geometry-quality Markdown differs from the public renderer"
            )

    print(
        json.dumps(
            {
                "error_count": direct_report["error_count"],
                "quality_report_version": starshine_geo.GEOMETRY_QUALITY_REPORT_VERSION,
                "starshine_version": installed_version,
                "status": "ok",
                "warning_count": direct_report["warning_count"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

from typing import Any

from starshine_geo import run_workflow

from .corpus import BenchmarkCase, build_cases


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def _verify_buffer(case: BenchmarkCase, output: dict[str, Any]) -> None:
    _require(len(output["features"]) == 64, f"{case.name}: expected 64 output features")
    geometry_types = {feature["geometry"]["type"] for feature in output["features"]}
    _require(geometry_types == {"Polygon"}, f"{case.name}: unexpected geometries")
    _require(
        all(
            feature["properties"]["starshine:buffer_distance"] == 5.0
            for feature in output["features"]
        ),
        f"{case.name}: buffer metadata is inconsistent",
    )


def _verify_dissolve(case: BenchmarkCase, output: dict[str, Any]) -> None:
    _require(len(output["features"]) == 4, f"{case.name}: expected four dissolved bands")
    actual_bands = {feature["properties"]["band"] for feature in output["features"]}
    _require(
        actual_bands == {"band-0", "band-1", "band-2", "band-3"},
        f"{case.name}: unexpected band values",
    )


def _verify_summary(case: BenchmarkCase, output: dict[str, Any]) -> None:
    _require(len(output["features"]) == 16, f"{case.name}: expected 16 zones")
    _require(
        all(feature["properties"]["site_count"] == 4 for feature in output["features"]),
        f"{case.name}: each zone should contain four sites",
    )


def _verify_multi_step(case: BenchmarkCase, output: dict[str, Any]) -> None:
    _require(len(output["features"]) == 1, f"{case.name}: expected one dissolved feature")
    geometry_type = output["features"][0]["geometry"]["type"]
    _require(
        geometry_type in {"Polygon", "MultiPolygon"},
        f"{case.name}: unexpected final geometry type: {geometry_type}",
    )


_VERIFIERS = {
    "buffer-grid-64": _verify_buffer,
    "dissolve-bands-80": _verify_dissolve,
    "summarize-zones-16-sites-64": _verify_summary,
    "multi-step-buffer-dissolve-36": _verify_multi_step,
}


def verify_case(case: BenchmarkCase) -> None:
    """Check semantic correctness outside the timed benchmark path."""
    result = run_workflow(case.workflow, case.layers)
    _VERIFIERS[case.name](case, result[case.output_layer])


def main() -> int:
    cases = build_cases()
    for case in cases:
        verify_case(case)
    print(f"Verified {len(cases)} deterministic benchmark cases.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

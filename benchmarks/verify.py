from __future__ import annotations

from typing import Any

from starshine_geo import run_workflow

from .corpus import BenchmarkCase, build_cases


def semantic_signature(case: BenchmarkCase, output: dict[str, Any]) -> dict[str, Any]:
    """Extract stable semantics without depending on raw geometry serialization order."""
    features = output["features"]
    base = {
        "crs": output.get("starshine:crs"),
        "feature_count": len(features),
    }

    if case.name == "buffer-grid-64":
        return {
            **base,
            "geometry_types": sorted({feature["geometry"]["type"] for feature in features}),
            "buffer_distance": next(
                iter({feature["properties"]["starshine:buffer_distance"] for feature in features})
            ),
            "work_crs": next(
                iter({feature["properties"]["starshine:work_crs"] for feature in features})
            ),
        }
    if case.name == "dissolve-bands-80":
        return {
            **base,
            "bands": sorted(feature["properties"]["band"] for feature in features),
        }
    if case.name == "summarize-zones-16-sites-64":
        return {
            **base,
            "zone_counts": sorted(
                [feature["properties"]["zone_id"], feature["properties"]["site_count"]]
                for feature in features
            ),
        }
    if case.name == "multi-step-buffer-dissolve-36":
        return base
    raise RuntimeError(f"no semantic signature is defined for benchmark case: {case.name}")


def verify_case(case: BenchmarkCase) -> None:
    """Check semantic correctness outside the timed benchmark path."""
    result = run_workflow(case.workflow, case.layers)
    actual = semantic_signature(case, result[case.output_layer])
    if actual != case.expected_signature:
        raise RuntimeError(
            f"{case.name}: semantic signature mismatch: "
            f"expected {case.expected_signature!r}, received {actual!r}"
        )


def main() -> int:
    cases = build_cases()
    for case in cases:
        verify_case(case)
    print(f"Verified {len(cases)} deterministic benchmark cases.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

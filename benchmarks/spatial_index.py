from __future__ import annotations

import argparse
import json
import platform
from collections.abc import Callable
from pathlib import Path
from statistics import median
from time import perf_counter_ns
from typing import Any

import shapely
from shapely.geometry import shape

import starshine_geo
from starshine_geo import digest_json, join_points_to_polygons, nearest_features

from .corpus import CORPUS_VERSION, BenchmarkCase, build_cases

Clock = Callable[[], int]
_INDEX_CASES = (
    "join-index-points-1024-zones-256",
    "nearest-index-grid-900-candidates-225",
)


def _timing(samples_ns: list[int]) -> dict[str, Any]:
    samples_seconds = [sample / 1_000_000_000 for sample in samples_ns]
    return {
        "samples_seconds": samples_seconds,
        "minimum_seconds": min(samples_seconds),
        "median_seconds": median(samples_seconds),
    }


def _nearest_signature(output: dict[str, Any]) -> dict[str, Any]:
    return {
        "crs": output.get("starshine:crs"),
        "feature_count": len(output["features"]),
        "matches": [
            [
                feature["properties"]["source_id"],
                feature["properties"]["nearest_id"],
                round(float(feature["properties"]["nearest_distance"]), 6),
            ]
            for feature in output["features"]
        ],
    }


def _join_signature(output: dict[str, Any]) -> dict[str, Any]:
    return {
        "crs": output.get("starshine:crs"),
        "feature_count": len(output["features"]),
        "assignments": [
            [
                feature["properties"]["point_id"],
                feature["properties"]["joined_zone"],
            ]
            for feature in output["features"]
        ],
    }


def _run_indexed(case: BenchmarkCase) -> dict[str, Any]:
    if case.name == "nearest-index-grid-900-candidates-225":
        output = nearest_features(
            case.layers["sources"],
            case.layers["candidates"],
            candidate_id_field="candidate_id",
        )
        return _nearest_signature(output)
    if case.name == "join-index-points-1024-zones-256":
        output = join_points_to_polygons(
            case.layers["points"],
            case.layers["zones"],
            polygon_id_field="zone_id",
            output_field="joined_zone",
        )
        return _join_signature(output)
    raise RuntimeError(f"unsupported spatial-index benchmark case: {case.name}")


def _run_reference(case: BenchmarkCase) -> dict[str, Any]:
    if case.name == "nearest-index-grid-900-candidates-225":
        candidates = [
            (feature["properties"]["candidate_id"], shape(feature["geometry"]))
            for feature in case.layers["candidates"]["features"]
        ]
        matches = []
        for feature in case.layers["sources"]["features"]:
            source_geometry = shape(feature["geometry"])
            best_identifier = None
            best_distance = None
            for identifier, candidate_geometry in candidates:
                distance = float(source_geometry.distance(candidate_geometry))
                if best_distance is None or distance < best_distance:
                    best_identifier = identifier
                    best_distance = distance
            matches.append(
                [
                    feature["properties"]["source_id"],
                    best_identifier,
                    round(float(best_distance), 6),
                ]
            )
        return {
            "crs": case.layers["sources"].get("starshine:crs"),
            "feature_count": len(matches),
            "matches": matches,
        }

    if case.name == "join-index-points-1024-zones-256":
        polygons = [
            (feature["properties"]["zone_id"], shape(feature["geometry"]))
            for feature in case.layers["zones"]["features"]
        ]
        assignments = []
        for feature in case.layers["points"]["features"]:
            point = shape(feature["geometry"])
            matches = [identifier for identifier, polygon in polygons if polygon.covers(point)]
            if len(matches) > 1:
                raise RuntimeError("reference point-in-polygon case is unexpectedly ambiguous")
            matched_identifier = matches[0] if matches else None
            assignments.append([feature["properties"]["point_id"], matched_identifier])
        return {
            "crs": case.layers["points"].get("starshine:crs"),
            "feature_count": len(assignments),
            "assignments": assignments,
        }

    raise RuntimeError(f"unsupported spatial-index benchmark case: {case.name}")


def _measure(
    function: Callable[[], dict[str, Any]],
    *,
    repeats: int,
    clock: Clock,
) -> tuple[dict[str, Any], list[int]]:
    result: dict[str, Any] | None = None
    samples: list[int] = []
    for _ in range(repeats):
        started = clock()
        result = function()
        samples.append(clock() - started)
    if result is None:
        raise RuntimeError("spatial-index benchmark produced no result")
    return result, samples


def build_report(*, repeats: int = 3, clock: Clock = perf_counter_ns) -> dict[str, Any]:
    """Compare indexed public APIs with an independent exhaustive reference implementation."""
    if repeats < 1:
        raise ValueError("repeats must be at least 1")

    all_cases = {case.name: case for case in build_cases()}
    results = []
    for name in _INDEX_CASES:
        case = all_cases[name]
        indexed, indexed_samples = _measure(
            lambda case=case: _run_indexed(case), repeats=repeats, clock=clock
        )
        reference, reference_samples = _measure(
            lambda case=case: _run_reference(case), repeats=repeats, clock=clock
        )
        if indexed != case.expected_signature or reference != case.expected_signature:
            raise RuntimeError(f"{name}: indexed/reference semantics diverged from the corpus")

        indexed_timing = _timing(indexed_samples)
        reference_timing = _timing(reference_samples)
        source_count, candidate_count = (
            (
                len(case.layers["points"]["features"]),
                len(case.layers["zones"]["features"]),
            )
            if name.startswith("join-")
            else (
                len(case.layers["sources"]["features"]),
                len(case.layers["candidates"]["features"]),
            )
        )
        indexed_median = indexed_timing["median_seconds"]
        reference_median = reference_timing["median_seconds"]
        observed_speedup = None if indexed_median == 0 else reference_median / indexed_median
        results.append(
            {
                "name": name,
                "source_feature_count": source_count,
                "candidate_feature_count": candidate_count,
                "exhaustive_pair_count": source_count * candidate_count,
                "semantic_digest": digest_json(indexed),
                "reference_semantic_digest": digest_json(reference),
                "semantic_equal": indexed == reference,
                "timing": {
                    "indexed_public_api": indexed_timing,
                    "exhaustive_reference": reference_timing,
                },
                "observed_speedup": observed_speedup,
            }
        )

    return {
        "schema_version": 1,
        "benchmark_version": 1,
        "corpus_version": CORPUS_VERSION,
        "starshine_version": starshine_geo.__version__,
        "shapely_version": shapely.__version__,
        "python": {
            "implementation": platform.python_implementation(),
            "version": platform.python_version(),
        },
        "platform": {
            "system": platform.system() or "unknown",
            "machine": platform.machine() or "unknown",
        },
        "repeat_count": repeats,
        "cases": results,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Compare deterministic STRtree operators with exhaustive references"
    )
    parser.add_argument("--repeat", type=int, default=3, help="Timing samples per case")
    parser.add_argument("--output", type=Path, help="Write JSON to this path instead of stdout")
    args = parser.parse_args(argv)
    if args.repeat < 1:
        parser.error("--repeat must be at least 1")

    payload = json.dumps(build_report(repeats=args.repeat), indent=2, sort_keys=True) + "\n"
    if args.output is None:
        print(payload, end="")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
        print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

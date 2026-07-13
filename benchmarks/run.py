from __future__ import annotations

import argparse
import json
import platform
from pathlib import Path
from statistics import median
from time import perf_counter_ns
from typing import Any, Callable

import starshine_geo
from starshine_geo import digest_json, run_workflow, validate_workflow

from .corpus import CORPUS_VERSION, BenchmarkCase, build_cases

Clock = Callable[[], int]


def _timing(samples_ns: list[int]) -> dict[str, Any]:
    samples_seconds = [sample / 1_000_000_000 for sample in samples_ns]
    return {
        "samples_seconds": samples_seconds,
        "minimum_seconds": min(samples_seconds),
        "median_seconds": median(samples_seconds),
    }


def _time_validation(case: BenchmarkCase, repeats: int, clock: Clock) -> list[int]:
    samples: list[int] = []
    for _ in range(repeats):
        started = clock()
        validate_workflow(case.workflow, case.layers)
        samples.append(clock() - started)
    return samples


def _time_workflow(
    case: BenchmarkCase,
    repeats: int,
    clock: Clock,
) -> tuple[dict[str, Any], list[int]]:
    samples: list[int] = []
    output: dict[str, Any] | None = None
    for _ in range(repeats):
        started = clock()
        result = run_workflow(case.workflow, case.layers)
        samples.append(clock() - started)
        output = result[case.output_layer]
    if output is None:
        raise RuntimeError("workflow timing produced no output")
    return output, samples


def build_report(*, repeats: int = 3, clock: Clock = perf_counter_ns) -> dict[str, Any]:
    """Run the public corpus and return timings plus deterministic comparison fields."""
    if repeats < 1:
        raise ValueError("repeats must be at least 1")

    cases = build_cases()
    case_definitions = [case.definition() for case in cases]
    case_results: list[dict[str, Any]] = []

    for case in cases:
        validation_samples = _time_validation(case, repeats, clock)
        output, workflow_samples = _time_workflow(case, repeats, clock)
        case_results.append(
            {
                "name": case.name,
                "description": case.description,
                "case_digest": digest_json(case.definition()),
                "input_layer_count": len(case.layers),
                "input_feature_count": case.input_feature_count,
                "operation_count": case.operation_count,
                "output_layer": case.output_layer,
                "output_feature_count": len(output["features"]),
                "output_digest": digest_json(output),
                "timing": {
                    "validation_only": _timing(validation_samples),
                    "validated_run": _timing(workflow_samples),
                },
            }
        )

    return {
        "schema_version": 1,
        "corpus_version": CORPUS_VERSION,
        "corpus_digest": digest_json(case_definitions),
        "starshine_version": starshine_geo.__version__,
        "python": {
            "implementation": platform.python_implementation(),
            "version": platform.python_version(),
        },
        "platform": {
            "system": platform.system() or "unknown",
            "machine": platform.machine() or "unknown",
        },
        "repeat_count": repeats,
        "cases": case_results,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the deterministic Starshine vector corpus")
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

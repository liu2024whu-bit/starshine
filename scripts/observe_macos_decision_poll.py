"""One fixed, discriminating #187 experiment; never a runtime acceptance test.

Run as python -W ignore -m scripts.observe_macos_decision_poll with an exact
candidate wheel installed in a clean venv. Unknown/cleanup failures stop early;
known supervision failures are retained and force failure after all 50 samples.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import sys
import tempfile
from importlib import metadata
from pathlib import Path
from zipfile import ZipFile

import psutil
from fastapi.testclient import TestClient

import starshine_geo
from scripts.decision_poll import observe_supervision, require_supported_runtime
from scripts.smoke_installed_server import (
    _execution_failure_diagnostic,
    _mask_layer,
    _point_layer,
)
from starshine_server import create_app, execution

SAMPLES = 50
ENVIRONMENT = "macos_arm64_python_3_14_10_psutil_7_2_2"


def _require_environment() -> None:
    require_supported_runtime(execution)
    if (
        sys.platform != "darwin" or platform.machine().lower() != "arm64"
        or psutil.__version__ != "7.2.2"
    ):
        raise RuntimeError("unsupported_experiment_environment")


def _verify_wheel(wheel: Path, revision: str) -> dict:
    if re.fullmatch(r"[0-9a-f]{40}", revision) is None:
        raise RuntimeError("invalid_candidate_revision")
    prefix = Path(sys.prefix).resolve()
    installed = metadata.distribution("starshine-geo")
    # Reject source/editable imports, not just a matching package version.
    with ZipFile(wheel) as archive:
        for package in (starshine_geo, execution):
            module = Path(package.__file__).resolve()
            relative = module.relative_to(installed.locate_file("").resolve()).as_posix()
            if not module.is_relative_to(prefix) or not relative.startswith("starshine_"):
                raise RuntimeError("candidate_wheel_origin_mismatch")
            if archive.read(relative) != module.read_bytes():
                raise RuntimeError("candidate_wheel_content_mismatch")
        for name in archive.namelist():
            if not name.endswith("/") and name.startswith(("starshine_geo/", "starshine_server/")):
                module = installed.locate_file(name).resolve()
                if not module.is_relative_to(prefix) or archive.read(name) != module.read_bytes():
                    raise RuntimeError("candidate_wheel_content_mismatch")
    return {"revision": revision, "wheel_sha256": hashlib.sha256(wheel.read_bytes()).hexdigest()}


def _write_report(path: Path, report: dict) -> None:
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, prefix="poll-evidence-", delete=False,
        ) as stream:
            temporary = Path(stream.name)
            json.dump(report, stream, sort_keys=True, separators=(",", ":"), allow_nan=False)
            stream.write("\n")
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _fixture():
    workflow = {"version": 1, "steps": [{
        "operation": "clip", "inputs": {"input": "source", "mask": "mask"},
        "parameters": {}, "output": "clipped",
    }]}
    layers = {"source": _point_layer(), "mask": _mask_layer()}
    result = starshine_geo.run_workflow(workflow, layers)["clipped"]
    expected = {
        "result_digest": starshine_geo.digest_json(result),
        "manifest": starshine_geo.build_manifest(
            workflow, layers, output_layer_name="clipped", output_layer=result,
        ),
        "preflight": starshine_geo.preflight_workflow_inputs(workflow, layers),
        "policy": execution.execution_limits(),
    }
    return {"workflow": workflow, "layers": layers, "output_layer": "clipped"}, expected


def _evidence_checks(payload, expected):
    if not isinstance(payload, dict):
        return {"response_object": False}
    return {
        "status_matches": payload.get("status") == "succeeded",
        "output_layer_matches": payload.get("output_layer") == "clipped",
        # Match the ordinary smoke's canonical digest, including tuple/list transport parity.
        "result_digest_matches": (
            starshine_geo.digest_json(payload.get("result")) == expected["result_digest"]
        ),
        "manifest_matches": payload.get("manifest") == expected["manifest"],
        "preflight_matches": payload.get("preflight") == expected["preflight"],
        "execution_policy_matches": payload.get("execution_policy") == expected["policy"],
    }


def _run_samples(client, request, expected, report, output):
    failed = False
    report["stop_reason"] = "sampling"
    for number in range(1, SAMPLES + 1):
        row = {"sample": number, "outcome": "started"}
        report["samples"].append(row)
        _write_report(output, report)  # Each attempt is recorded before starting its worker.
        observations = []
        with observe_supervision(execution, observations):
            response = client.post("/api/v1/workflows/execute", json=request)
        row["http_status"] = response.status_code
        row["decision_poll_count"] = len(observations)
        if len(observations) == 1:
            row["decision_poll"] = observations[0]
        if response.status_code == 200:
            checks = _evidence_checks(response.json(), expected)
            row.update(checks)
            row["outcome"] = "succeeded" if all(checks.values()) else "evidence_mismatch"
            if not all(checks.values()) or len(observations) > 1:
                report["stop_reason"] = "unexpected_evidence"
                break
        else:
            row.update(_execution_failure_diagnostic(response))
            row["outcome"] = "failed"
            failed = True
            if row.get("code") == "worker_cleanup_failed":
                report["stop_reason"] = "cleanup_failed"
                break
            if not (
                response.status_code == 500 and row.get("code") == "worker_supervision_failed"
                and row.get("stage") == "tree_memory"
                and row.get("reason") in {"missing", "zombie", "access_denied", "other"}
                and len(observations) == 1 and observations[0]["poll_result"] == "none"
            ):
                report["stop_reason"] = "unclassified_failure"
                break
        _write_report(output, report)
    else:
        report["stop_reason"] = "fixed_sample_complete"
    complete = report["stop_reason"] == "fixed_sample_complete"
    report["observation"] = (
        "incomplete" if not complete else
        "recurrence_or_failure_observed" if failed else "no_recurrence_inconclusive"
    )
    _write_report(output, report)
    return 0 if complete and not failed else 1


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheel", type=Path, required=True)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    report = {
        "schema_version": 1, "planned_samples": SAMPLES, "samples": [],
        "hypothesis": "distinguish_existing_decision_poll_branches_after_rss_error",
        "observation": "incomplete", "stop_reason": "not_started",
        "runtime_policy_changed": False, "resolves_issue_187": False,
        "rss_substage_observed": False, "timing_equivalence_claimed": False,
    }
    try:
        # Exclusive reservation refuses existing evidence before any worker can start.
        with args.output.open("x", encoding="utf-8") as stream:
            json.dump(report, stream, sort_keys=True)
    except OSError:
        print("experiment_evidence_destination_unavailable")
        return 1
    try:
        _require_environment()  # Includes the actual exact-version/source/signature guard.
        report["environment"] = ENVIRONMENT
        report["candidate"] = _verify_wheel(args.wheel, args.revision)
        report["exact_runtime_guard_passed"] = True
        _write_report(args.output, report)
        request, expected = _fixture()
        with TestClient(create_app()) as client:
            result = _run_samples(client, request, expected, report, args.output)
    except BaseException:  # noqa: BLE001 - keep CLI evidence sanitized and incomplete
        # Never render raw exceptions, paths, PIDs, data, request URLs or worker output.
        report["stop_reason"] = "harness_error"
        report["observation"] = "incomplete"
        if report["samples"] and report["samples"][-1]["outcome"] == "started":
            report["samples"][-1]["outcome"] = "unexpected_exception"
        try:
            _write_report(args.output, report)
        except OSError:
            print("experiment_evidence_write_failed")
        result = 1
    print(json.dumps(report, sort_keys=True, separators=(",", ":")))
    return result


if __name__ == "__main__":
    raise SystemExit(main())

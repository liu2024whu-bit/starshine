"""Fixed-size #187 observation; never an acceptance replacement or runtime repair."""
from __future__ import annotations

import hashlib
import json
import os
import platform
import re
from importlib.metadata import distribution
from pathlib import Path

import psutil
from fastapi.testclient import TestClient

import starshine_geo
from starshine_server import create_app

if __package__:
    from .smoke_installed_server import _BOUNDARY_CODES, _mask_layer, _point_layer
else:
    from smoke_installed_server import _BOUNDARY_CODES, _mask_layer, _point_layer

SAMPLES = 50
EVIDENCE = Path("macos-supervision-observation.json")
_ALLOWED = {
    "code": _BOUNDARY_CODES,
    "reason": {"missing", "zombie", "access_denied", "other"},
    "stage": {"process_lookup", "tree_memory"},
    "substage": {"root_memory", "children_enumeration", "descendant_memory"},
}


def _environment_supported() -> bool:
    return (platform.system() == "Darwin" and platform.machine() == "arm64"
            and platform.python_version() == "3.14.10" and psutil.__version__ == "7.2.2")


def _installed_candidate() -> bool:
    import starshine_server

    candidate = distribution("starshine-geo")
    files = candidate.files or []
    for module in (starshine_geo, starshine_server):
        origin = Path(module.__file__).resolve()
        if not any(Path(candidate.locate_file(item)).resolve() == origin for item in files):
            return False
        if Path(__file__).resolve().parents[1] in origin.parents:
            return False
    return True


def _request() -> dict:
    return {
        "workflow": {"version": 1, "steps": [{
            "operation": "clip", "inputs": {"input": "source", "mask": "mask"},
            "parameters": {}, "output": "clipped",
        }]},
        "layers": {"source": _point_layer(), "mask": _mask_layer()},
        "output_layer": "clipped",
    }


def _observe(response, expected: dict) -> dict:
    row = {"outcome": "failed", "http_status": response.status_code}
    if response.status_code == 200:
        payload = response.json()
        comparisons = {
            "status_matches": payload.get("status") == "succeeded",
            "result_digest_matches": starshine_geo.digest_json(payload.get("result"))
            == starshine_geo.digest_json(expected["result"]),
            "manifest_matches": payload.get("manifest") == expected["manifest"],
            "preflight_matches": payload.get("preflight") == expected["preflight"],
            "execution_mode_matches": payload.get("execution_policy", {}).get("mode")
            == "isolated_subprocess",
        }
        row.update(comparisons)
        matches = all(comparisons.values())
        row.update(outcome="succeeded" if matches else "failed", evidence_matches=matches)
        return row
    if len(response.content) <= 4096:
        try:
            payload = response.json()
        except (ValueError, RecursionError):
            payload = None
        if isinstance(payload, dict) and payload.get("error") == "execution_boundary":
            for key, allowed in _ALLOWED.items():
                value = payload.get(key)
                if isinstance(value, str) and value in allowed:
                    row[key] = value
    return row


def run(client, output: Path, *, supported: bool, provenance: dict | None = None) -> int:
    # Only known enums, counts, statuses and booleans are persisted; no response text.
    report = {
        "schema_version": 1, "planned_samples": SAMPLES, "samples": [],
        "candidate": provenance or {},
        "environment": "macos_arm64_python_3_14_10_psutil_7_2_2" if supported else "unsupported",
        "observation": "incomplete", "stop_reason": "not_started",
        "runtime_policy_changed": False, "resolves_issue_187": False,
    }

    def save():
        temporary = output.with_suffix(".tmp")
        temporary.write_text(json.dumps(report, sort_keys=True, indent=2) + "\n",
                             encoding="utf-8")
        temporary.replace(output)

    save()
    if not supported:
        report["stop_reason"] = "unsupported_environment"
        save()
        return 1
    try:
        request = _request()
        result = starshine_geo.run_workflow(request["workflow"], request["layers"])["clipped"]
        expected = {
            "result": result,
            "manifest": starshine_geo.build_manifest(
                request["workflow"], request["layers"],
                output_layer_name="clipped", output_layer=result,
            ),
            "preflight": starshine_geo.preflight_workflow_inputs(
                request["workflow"], request["layers"],
            ),
        }
        report["stop_reason"] = "sampling"
        save()
        for index in range(1, SAMPLES + 1):
            # Persist the attempt before execution, including interruption/exception cases.
            row = {"sample": index, "outcome": "started"}
            report["samples"].append(row)
            save()
            row.update(_observe(client.post("/api/v1/workflows/execute", json=request), expected))
            save()
            if row.get("code") == "worker_cleanup_failed" or (
                row["outcome"] == "failed" and "code" not in row
            ):
                report["stop_reason"] = ("unconfirmed_cleanup" if row.get("code")
                                         == "worker_cleanup_failed" else "unclassified_response")
                save()
                return 1
    except Exception:  # noqa: BLE001 - stop safely without disclosing arbitrary errors
        # Unexpected errors can leave cleanup unknown. Stop, never retry or stringify.
        report["stop_reason"] = "unexpected_harness_error"
        if report["samples"] and report["samples"][-1]["outcome"] == "started":
            report["samples"][-1]["outcome"] = "harness_error"
        save()
        return 1
    failed = any(row["outcome"] != "succeeded" for row in report["samples"])
    report["observation"] = "recurrence_or_failure_observed" if failed else "no_recurrence_inconclusive"
    report["stop_reason"] = "fixed_sample_complete"
    save()
    return int(failed)


def main() -> int:
    # Unsupported platforms and non-wheel imports never start a worker.
    try:
        if not _environment_supported() or not _installed_candidate():
            return run(None, EVIDENCE, supported=False)
        revision = os.environ.get("STARSHINE_OBSERVATION_REVISION", "")
        wheels = list(Path("dist").glob("*.whl"))
        if re.fullmatch(r"[0-9a-f]{40}", revision) is None or len(wheels) != 1:
            return run(None, EVIDENCE, supported=False)
        provenance = {"revision": revision, "wheel_sha256": hashlib.sha256(
            wheels[0].read_bytes()).hexdigest()}
        with TestClient(create_app()) as client:
            outcome = run(client, EVIDENCE, supported=True, provenance=provenance)
        return outcome
    except Exception:  # noqa: BLE001 - no raw startup/shutdown errors in diagnostic output
        try:
            report = json.loads(EVIDENCE.read_text()) if EVIDENCE.exists() else {
                "schema_version": 1, "planned_samples": SAMPLES, "samples": [],
                "resolves_issue_187": False,
            }
            report.update(observation="incomplete", stop_reason="unexpected_harness_error")
            temporary = EVIDENCE.with_suffix(".tmp")
            temporary.write_text(json.dumps(report, sort_keys=True, indent=2) + "\n",
                                 encoding="utf-8")
            temporary.replace(EVIDENCE)
        except Exception:  # noqa: BLE001 - evidence I/O failure must not leak a path
            return 1
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

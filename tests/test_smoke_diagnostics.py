from __future__ import annotations

import json
import traceback

import pytest

httpx = pytest.importorskip("httpx")
pytest.importorskip("fastapi")
pytest.importorskip("psutil")

from scripts.smoke_installed_server import _BOUNDARY_CODES, _check_execution_response

SECRET = "private-token-do-not-log"


def response(status=500, **kwargs):
    return httpx.Response(
        status,
        request=httpx.Request("POST", f"https://example.invalid/{SECRET}",
                              headers={"Authorization": SECRET}),
        headers={"X-Private": SECRET},
        **kwargs,
    )


def failure_diagnostic(reply):
    with pytest.raises(httpx.HTTPStatusError) as caught:
        _check_execution_response(reply)
    exc = caught.value
    assert exc.response is reply
    assert exc.request is reply.request
    assert exc.__suppress_context__
    rendered = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    assert SECRET not in rendered
    assert "example.invalid" not in rendered
    return json.loads(str(exc).split(": ", 1)[1])


def test_success_has_no_diagnostic_output(capsys):
    _check_execution_response(response(200, text=SECRET))
    assert capsys.readouterr() == ("", "")


@pytest.mark.parametrize("code", sorted(_BOUNDARY_CODES))
def test_known_boundary_codes_expose_only_safe_fields(code):
    assert failure_diagnostic(response(json={
        "error": "execution_boundary", "code": code,
        "message": SECRET, "stdout": SECRET, "limit": 10, "actual": 20,
    })) == {"status": 500, "error": "execution_boundary", "code": code,
           "limit": 10, "actual": 20}


@pytest.mark.parametrize("value", [True, False, -1, 2**63, 1.5, "123", None, [1], {}])
def test_numeric_fields_reject_non_integer_or_out_of_bounds(value):
    diagnostic = failure_diagnostic(response(json={
        "error": "execution_boundary", "code": "worker_failed",
        "limit": value, "actual": value,
    }))
    assert diagnostic == {"status": 500, "error": "execution_boundary", "code": "worker_failed"}


@pytest.mark.parametrize("payload", [
    {"error": SECRET, "code": "worker_failed"},
    {"error": "execution_boundary", "code": SECRET},
    {"error": "execution_boundary", "code": []},
    {"error": "execution_boundary", "code": {}},
    [SECRET], SECRET, None,
])
def test_unknown_json_never_echoed(payload):
    assert failure_diagnostic(response(content=json.dumps(payload))) == {"status": 500}


@pytest.mark.parametrize("body", [
    SECRET.encode(), b"\xff", b"[" * 1500 + b"]" * 1500,
    json.dumps({"error": "execution_boundary", "code": "worker_failed",
                "message": SECRET * 500}).encode(),
])
def test_invalid_deep_or_oversized_body_is_not_echoed(body):
    assert failure_diagnostic(response(content=body)) == {"status": 500}


def test_redirect_still_fails_without_disclosing_location():
    reply = response(302, text=SECRET)
    reply.headers["Location"] = f"https://example.invalid/{SECRET}"
    assert failure_diagnostic(reply) == {"status": 302}


def test_server_boundary_error_remains_fatal_with_safe_diagnostics(monkeypatch):
    from fastapi.testclient import TestClient

    from scripts.smoke_installed_server import _mask_layer, _point_layer
    from starshine_server import create_app
    from starshine_server.execution import ExecutionBoundaryError

    def fail_worker(_payload):
        raise ExecutionBoundaryError(
            code="worker_supervision_failed", message=SECRET, status_code=500,
        )

    monkeypatch.setattr("starshine_server.execution._run_worker", fail_worker)
    reply = TestClient(create_app()).post("/api/v1/workflows/execute", json={
        "workflow": {"version": 1, "steps": [
            {"operation": "clip", "inputs": {"input": "source", "mask": "mask"},
             "output": "clipped"},
        ]},
        "layers": {"source": _point_layer(), "mask": _mask_layer()},
        "output_layer": "clipped",
    })
    assert reply.status_code == 500
    assert failure_diagnostic(reply) == {
        "status": 500, "error": "execution_boundary", "code": "worker_supervision_failed",
    }

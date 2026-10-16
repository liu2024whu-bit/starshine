"""Transport limits must hold before framework parsing or Core evaluation."""
from __future__ import annotations

import asyncio
import json

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient

import starshine_geo
from starshine_server import create_app
from starshine_server.limits import MAX_REQUEST_BYTES, RequestBodyLimitMiddleware

ROUTES = ("validate", "plan", "preflight")


@pytest.mark.parametrize("route", ROUTES)
@pytest.mark.parametrize("length", [None, "1", "invalid", "-1"])
def test_streamed_oversize_has_the_same_413_envelope(route, length, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Oversized input must not reach Core")

    for name in ("validate_workflow", "plan_workflow", "preflight_workflow_inputs"):
        monkeypatch.setattr(starshine_geo, name, forbidden)
    headers = {"content-type": "application/json"}
    if length is not None:
        headers["content-length"] = length
    response = TestClient(create_app()).post(
        f"/api/v1/workflows/{route}",
        content=iter([b"x" * MAX_REQUEST_BYTES, b"x"]),
        headers=headers,
    )
    assert response.status_code == 413
    assert response.json() == {
        "error": "request_limit",
        "code": "request_body_too_large",
        "message": "Request body exceeds the inline API byte limit.",
        "limit": MAX_REQUEST_BYTES,
        "actual": MAX_REQUEST_BYTES + 1,
    }


@pytest.mark.parametrize("route", ROUTES)
@pytest.mark.parametrize("value", ["NaN", "Infinity", "-Infinity", "1e999", '"\\ud800"'])
def test_unrepresentable_json_is_a_client_error_without_echo_or_core(route, value, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Unrepresentable JSON must not reach Core")

    for name in ("validate_workflow", "plan_workflow", "preflight_workflow_inputs"):
        monkeypatch.setattr(starshine_geo, name, forbidden)
    body = '{"workflow":{},"layers":{"source":{}},"private_marker":' + value + '}'
    response = TestClient(create_app(), raise_server_exceptions=False).post(
        f"/api/v1/workflows/{route}", content=body,
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 400
    assert response.json()["error"] == "invalid_json"
    assert "private_marker" not in response.text
    assert value not in response.text


@pytest.mark.parametrize("depth", [65, 1200])
def test_deep_json_is_rejected_before_core(depth, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Deep input must not reach Core")

    monkeypatch.setattr(starshine_geo, "preflight_workflow_inputs", forbidden)
    body = b'{"workflow":{},"layers":{"source":{"extra":' + b'[' * depth + b'0' + b']' * depth + b'}}}'
    response = TestClient(create_app(), raise_server_exceptions=False).post(
        "/api/v1/workflows/preflight", content=body,
        headers={"content-type": "application/json"},
    )
    assert response.status_code in (400, 413)
    assert response.json()["error"] in ("invalid_json", "request_limit")


@pytest.mark.parametrize("content_type", [None, "application/json", "application/geo+json; charset=utf-8"])
def test_valid_json_values_and_bytes_survive_transport(content_type, monkeypatch):
    payload = {"workflow": {}, "layers": {"source": {
        "label": "NaN Infinity \u4e2d\u6587", "number": 1.25, "boolean": False,
        "null": None, "nested": {"brackets": "[{}]"},
    }}}
    received = []

    def preflight(workflow, layers):
        received.append({"workflow": workflow, "layers": layers})
        return {"valid": True}

    monkeypatch.setattr(starshine_geo, "preflight_workflow_inputs", preflight)
    headers = {"content-type": content_type} if content_type else {}
    body = json.dumps(payload, ensure_ascii=False).encode()
    response = TestClient(create_app()).post(
        "/api/v1/workflows/preflight", content=iter([body[:25], body[25:]]), headers=headers,
    )
    assert response.status_code == 200
    assert received == [payload]


def test_regular_json_syntax_errors_keep_framework_diagnostics():
    response = TestClient(create_app()).post(
        "/api/v1/workflows/preflight", content=b'{',
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 422
    assert response.json()["detail"][0]["type"] == "json_invalid"


def test_limit_is_inclusive_and_extra_receive_preserves_disconnect():
    messages = [
        {"type": "http.request", "body": b"1234", "more_body": True},
        {"type": "http.request", "body": b"5678", "more_body": False},
        {"type": "http.disconnect"},
    ]
    received = []

    async def receive():
        return messages.pop(0)

    async def send(message):
        raise AssertionError("No middleware rejection expected")

    async def downstream(scope, receive, send):
        while True:
            message = await receive()
            received.append(message)
            if message["type"] == "http.disconnect":
                break

    asyncio.run(RequestBodyLimitMiddleware(downstream, max_bytes=8)(
        {"type": "http", "headers": [(b"content-type", b"application/octet-stream")]},
        receive, send,
    ))
    assert b"".join(message.get("body", b"") for message in received) == b"12345678"
    assert received[-1] == {"type": "http.disconnect"}


@pytest.mark.parametrize("declared", [True, False])
def test_rejection_never_calls_downstream_or_drains_the_rest(declared):
    messages = [
        {"type": "http.request", "body": b"12345678", "more_body": True},
        {"type": "http.request", "body": b"9", "more_body": True},
        {"type": "http.request", "body": b"must-not-read", "more_body": False},
    ]
    sent = []

    async def receive():
        return messages.pop(0)

    async def send(message):
        sent.append(message)

    async def downstream(scope, receive, send):
        raise AssertionError("Reject before downstream starts")

    scope = {"type": "http", "headers": [(b"content-length", b"9")] if declared else []}
    asyncio.run(RequestBodyLimitMiddleware(downstream, max_bytes=8)(scope, receive, send))
    assert [item["status"] for item in sent if item["type"] == "http.response.start"] == [413]
    assert len(messages) == (3 if declared else 1)


def test_disconnect_before_complete_body_does_not_invoke_core():
    messages = [
        {"type": "http.request", "body": b"123", "more_body": True},
        {"type": "http.disconnect"},
    ]

    async def receive():
        return messages.pop(0)

    async def forbidden(*args):
        raise AssertionError("No response or downstream call after disconnect")

    asyncio.run(RequestBodyLimitMiddleware(forbidden)(
        {"type": "http", "headers": []}, receive, forbidden,
    ))


@pytest.mark.parametrize("scope_type", ["lifespan", "websocket"])
def test_non_http_scope_is_delegated_unchanged(scope_type):
    scope = {"type": scope_type}
    called = []

    async def unused():
        raise AssertionError("Do not consume non-HTTP receive")

    async def downstream(actual_scope, receive, send):
        assert actual_scope is scope and receive is unused and send is unused
        called.append(True)

    asyncio.run(RequestBodyLimitMiddleware(downstream)(scope, unused, unused))
    assert called == [True]


def test_declared_depth_limit_is_inclusive(monkeypatch):
    from starshine_server.limits import MAX_JSON_DEPTH

    def preflight(workflow, layers):
        return {"valid": True}

    monkeypatch.setattr(starshine_geo, "preflight_workflow_inputs", preflight)
    client = TestClient(create_app())
    for levels, expected in [(MAX_JSON_DEPTH, 200), (MAX_JSON_DEPTH + 1, 413)]:
        # Envelope, layers, and source are the first three object levels.
        value = 0
        for _ in range(levels - 3):
            value = [value]
        response = client.post("/api/v1/workflows/preflight", json={
            "workflow": {}, "layers": {"source": {"nested": value}},
        })
        assert response.status_code == expected
        if expected == 413:
            assert response.json()["limit"] == MAX_JSON_DEPTH
            assert response.json()["actual"] == MAX_JSON_DEPTH + 1


def test_unrelated_application_error_is_not_disguised_as_client_input():
    async def receive():
        return {"type": "http.request", "body": b"{}", "more_body": False}

    async def send(message):
        raise AssertionError("Middleware must not disguise an application error")

    async def broken_app(scope, receive, send):
        raise ValueError("synthetic downstream bug")

    with pytest.raises(ValueError, match="synthetic downstream bug"):
        asyncio.run(RequestBodyLimitMiddleware(broken_app)(
            {"type": "http", "headers": []}, receive, send,
        ))

from __future__ import annotations

import json
import math
from collections.abc import Awaitable, Callable
from typing import Any

from starlette.responses import JSONResponse

MAX_REQUEST_BYTES = 2 * 1024 * 1024
MAX_JSON_DEPTH = 64
MAX_LAYER_COUNT = 8
MAX_LAYER_NAME_CHARS = 128
MAX_WORKFLOW_STEPS = 16
MAX_FEATURES_PER_LAYER = 2_000
MAX_TOTAL_FEATURES = 5_000

MAX_EXECUTION_SECONDS = 10
MAX_EXECUTION_MEMORY_BYTES = 512 * 1024 * 1024
MAX_EXECUTION_RESPONSE_BYTES = 8 * 1024 * 1024


class RequestLimitError(Exception):
    """Raised when a request exceeds an explicit Starshine Server semantic limit."""

    def __init__(self, *, code: str, message: str, limit: int, actual: int) -> None:
        self.code = code
        self.limit = limit
        self.actual = actual
        super().__init__(message)

    def as_dict(self) -> dict[str, Any]:
        return {
            "error": "request_limit",
            "code": self.code,
            "message": str(self),
            "limit": self.limit,
            "actual": self.actual,
        }


def _finite_json_number(text: str) -> float:
    value = float(text)
    if not math.isfinite(value):
        raise ValueError("Non-finite JSON number")
    return value


def _check_json_transport(body: bytearray) -> None:
    """Check JSON representability only, not Workflow or spatial semantics."""
    value = json.loads(body, parse_float=_finite_json_number, parse_constant=_finite_json_number)
    pending = [(value, 1)]
    while pending:
        value, depth = pending.pop()
        if isinstance(value, (dict, list)):
            if depth > MAX_JSON_DEPTH:
                raise RequestLimitError(
                    code="json_nesting_too_deep",
                    message="JSON nesting exceeds the inline API depth limit.",
                    limit=MAX_JSON_DEPTH,
                    actual=depth,
                )
            children = value.values() if isinstance(value, dict) else value
            pending.extend((child, depth + 1) for child in children)
            if isinstance(value, dict):
                for key in value:
                    key.encode("utf-8")
        elif isinstance(value, str):
            value.encode("utf-8")


class RequestBodyLimitMiddleware:
    """Bound and validate transport bytes before the framework reads the body."""

    def __init__(self, app: Any, *, max_bytes: int = MAX_REQUEST_BYTES) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(
        self,
        scope: dict[str, Any],
        receive: Callable[[], Awaitable[dict[str, Any]]],
        send: Callable[[dict[str, Any]], Awaitable[None]],
    ) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        headers = {key.lower(): value for key, value in scope.get("headers", [])}
        content_length = headers.get(b"content-length")
        if content_length is not None:
            try:
                declared_length = int(content_length)
            except ValueError:
                declared_length = None
            if declared_length is not None and declared_length > self.max_bytes:
                await self._reject(scope, receive, send, actual=declared_length)
                return

        # Reject before entering FastAPI: exceptions raised from a wrapped receive
        # can otherwise be converted into generic body-parsing 400 responses.
        body = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            chunk = message.get("body", b"")
            actual = len(body) + len(chunk)
            if actual > self.max_bytes:
                await self._reject(scope, receive, send, actual=actual)
                return
            body.extend(chunk)
            if not message.get("more_body", False):
                break

        media_type = headers.get(b"content-type", b"application/json").split(b";", 1)[0]
        media_type = media_type.strip().lower()
        is_json = media_type == b"application/json" or (
            media_type.startswith(b"application/") and media_type.endswith(b"+json")
        )
        if body and is_json:
            try:
                _check_json_transport(body)
            except json.JSONDecodeError:
                # Preserve the framework's existing 422 syntax diagnostics.
                pass
            except RequestLimitError as exc:
                await JSONResponse(status_code=413, content=exc.as_dict())(scope, receive, send)
                return
            except (ValueError, RecursionError):
                # Never reflect raw input, parser exceptions or invalid Unicode.
                await JSONResponse(
                    status_code=400,
                    content={
                        "error": "invalid_json",
                        "message": "JSON values exceed parser or representation limits.",
                    },
                )(scope, receive, send)
                return

        delivered = False

        async def replay_receive() -> dict[str, Any]:
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": bytes(body), "more_body": False}
            return await receive()

        await self.app(scope, replay_receive, send)

    async def _reject(
        self,
        scope: dict[str, Any],
        receive: Callable[[], Awaitable[dict[str, Any]]],
        send: Callable[[dict[str, Any]], Awaitable[None]],
        *,
        actual: int,
    ) -> None:
        response = JSONResponse(
            status_code=413,
            content={
                "error": "request_limit",
                "code": "request_body_too_large",
                "message": "Request body exceeds the inline API byte limit.",
                "limit": self.max_bytes,
                "actual": actual,
            },
        )
        await response(scope, receive, send)


def inline_preflight_limits() -> dict[str, int]:
    """Return client-visible limits for the in-memory Preflight surface."""
    return {
        "max_request_bytes": MAX_REQUEST_BYTES,
        "max_json_depth": MAX_JSON_DEPTH,
        "max_layers": MAX_LAYER_COUNT,
        "max_layer_name_chars": MAX_LAYER_NAME_CHARS,
        "max_workflow_steps": MAX_WORKFLOW_STEPS,
        "max_features_per_layer": MAX_FEATURES_PER_LAYER,
        "max_total_features": MAX_TOTAL_FEATURES,
    }


def execution_limits() -> dict[str, int | str]:
    """Return the fixed resource policy for synchronous isolated execution."""
    return {
        "mode": "isolated_subprocess",
        "timeout_seconds": MAX_EXECUTION_SECONDS,
        "memory_limit_bytes": MAX_EXECUTION_MEMORY_BYTES,
        "max_response_bytes": MAX_EXECUTION_RESPONSE_BYTES,
    }


def enforce_inline_preflight_limits(
    workflow: dict[str, Any],
    layers: dict[str, dict[str, Any]],
) -> None:
    """Reject requests that exceed Server capacity without interpreting GIS semantics."""
    layer_count = len(layers)
    if layer_count > MAX_LAYER_COUNT:
        raise RequestLimitError(
            code="too_many_layers",
            message="Inline Preflight has too many named layers.",
            limit=MAX_LAYER_COUNT,
            actual=layer_count,
        )

    steps = workflow.get("steps")
    if isinstance(steps, list) and len(steps) > MAX_WORKFLOW_STEPS:
        raise RequestLimitError(
            code="too_many_workflow_steps",
            message="Inline Preflight has too many Workflow steps.",
            limit=MAX_WORKFLOW_STEPS,
            actual=len(steps),
        )

    total_features = 0
    for name, collection in layers.items():
        if len(name) > MAX_LAYER_NAME_CHARS:
            raise RequestLimitError(
                code="layer_name_too_long",
                message="Inline Preflight layer name exceeds the character limit.",
                limit=MAX_LAYER_NAME_CHARS,
                actual=len(name),
            )

        features = collection.get("features")
        if not isinstance(features, list):
            continue

        feature_count = len(features)
        if feature_count > MAX_FEATURES_PER_LAYER:
            raise RequestLimitError(
                code="too_many_features_in_layer",
                message=f"Inline Preflight layer {name!r} exceeds the feature limit.",
                limit=MAX_FEATURES_PER_LAYER,
                actual=feature_count,
            )
        total_features += feature_count

    if total_features > MAX_TOTAL_FEATURES:
        raise RequestLimitError(
            code="too_many_features",
            message="Inline Preflight exceeds the total feature limit.",
            limit=MAX_TOTAL_FEATURES,
            actual=total_features,
        )


__all__ = [
    "MAX_EXECUTION_MEMORY_BYTES",
    "MAX_EXECUTION_RESPONSE_BYTES",
    "MAX_EXECUTION_SECONDS",
    "MAX_FEATURES_PER_LAYER",
    "MAX_JSON_DEPTH",
    "MAX_LAYER_COUNT",
    "MAX_LAYER_NAME_CHARS",
    "MAX_REQUEST_BYTES",
    "MAX_TOTAL_FEATURES",
    "MAX_WORKFLOW_STEPS",
    "RequestBodyLimitMiddleware",
    "RequestLimitError",
    "enforce_inline_preflight_limits",
    "execution_limits",
    "inline_preflight_limits",
]

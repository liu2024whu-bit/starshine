from __future__ import annotations

from typing import Any, Awaitable, Callable

from starlette.responses import JSONResponse

MAX_REQUEST_BYTES = 2 * 1024 * 1024
MAX_LAYER_COUNT = 8
MAX_LAYER_NAME_CHARS = 128
MAX_WORKFLOW_STEPS = 16
MAX_FEATURES_PER_LAYER = 2_000
MAX_TOTAL_FEATURES = 5_000


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


class _BodyLimitExceeded(Exception):
    pass


class RequestBodyLimitMiddleware:
    """Reject HTTP bodies larger than the declared platform boundary."""

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

        received_bytes = 0

        async def limited_receive() -> dict[str, Any]:
            nonlocal received_bytes
            message = await receive()
            if message.get("type") == "http.request":
                received_bytes += len(message.get("body", b""))
                if received_bytes > self.max_bytes:
                    raise _BodyLimitExceeded
            return message

        try:
            await self.app(scope, limited_receive, send)
        except _BodyLimitExceeded:
            await self._reject(scope, receive, send, actual=received_bytes)

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
        "max_layers": MAX_LAYER_COUNT,
        "max_layer_name_chars": MAX_LAYER_NAME_CHARS,
        "max_workflow_steps": MAX_WORKFLOW_STEPS,
        "max_features_per_layer": MAX_FEATURES_PER_LAYER,
        "max_total_features": MAX_TOTAL_FEATURES,
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
    "MAX_FEATURES_PER_LAYER",
    "MAX_LAYER_COUNT",
    "MAX_LAYER_NAME_CHARS",
    "MAX_REQUEST_BYTES",
    "MAX_TOTAL_FEATURES",
    "MAX_WORKFLOW_STEPS",
    "RequestBodyLimitMiddleware",
    "RequestLimitError",
    "enforce_inline_preflight_limits",
    "inline_preflight_limits",
]

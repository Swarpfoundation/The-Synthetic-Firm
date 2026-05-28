"""Read-only HTTP API and SSE stream for the public progress website."""

from __future__ import annotations

import argparse
import hmac
import json
import os
import time
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlparse

from synthetic_firm.control_room_export import build_control_room_snapshot
from synthetic_firm.provider_auth_redaction import redact_auth_text
from synthetic_firm.store import Store
from synthetic_firm.time_utils import utc_iso

DEFAULT_ALLOWED_ORIGIN = "http://localhost:5173"
DEFAULT_SSE_INTERVAL_SECONDS = 5.0


class ControlRoomApiError(ValueError):
    """Raised when the read-only public progress API fails closed."""


@dataclass(frozen=True)
class ControlRoomApiConfig:
    host: str = "127.0.0.1"
    port: int = 8787
    allowed_origins: frozenset[str] = frozenset({DEFAULT_ALLOWED_ORIGIN})
    public_enabled: bool = True
    founder_enabled: bool = False
    founder_token: str | None = None
    sse_interval_seconds: float = DEFAULT_SSE_INTERVAL_SECONDS

    def origin_allowed(self, origin: str | None) -> bool:
        if not origin:
            return True
        return origin in self.allowed_origins


@dataclass(frozen=True)
class ApiResponse:
    status: int
    body: bytes
    content_type: str = "application/json; charset=utf-8"
    headers: tuple[tuple[str, str], ...] = ()


def load_api_config() -> ControlRoomApiConfig:
    origins = frozenset(
        origin.strip()
        for origin in os.environ.get("TSF_CONTROL_ROOM_ALLOWED_ORIGINS", DEFAULT_ALLOWED_ORIGIN).split(",")
        if origin.strip()
    )
    return ControlRoomApiConfig(
        host=os.environ.get("TSF_CONTROL_ROOM_HOST", "127.0.0.1"),
        port=int(os.environ.get("TSF_CONTROL_ROOM_PORT", "8787")),
        allowed_origins=origins or frozenset({DEFAULT_ALLOWED_ORIGIN}),
        public_enabled=os.environ.get("TSF_CONTROL_ROOM_PUBLIC_ENABLED", "true").strip().lower() == "true",
        founder_enabled=os.environ.get("TSF_CONTROL_ROOM_FOUNDER_ENABLED", "false").strip().lower() == "true",
        founder_token=os.environ.get("TSF_CONTROL_ROOM_FOUNDER_TOKEN"),
        sse_interval_seconds=float(
            os.environ.get("TSF_CONTROL_ROOM_SSE_INTERVAL_SECONDS", str(DEFAULT_SSE_INTERVAL_SECONDS))
        ),
    )


class ControlRoomApi:
    """Testable read-only router used by the stdlib HTTP server."""

    def __init__(self, config: ControlRoomApiConfig | None = None):
        self.config = config or load_api_config()

    def handle(self, method: str, path: str, headers: dict[str, str] | None = None) -> ApiResponse:
        headers = headers or {}
        try:
            return self._handle(method, path, headers)
        except PermissionError as exc:
            message = str(exc)
            status = HTTPStatus.UNAUTHORIZED if "required" in message else HTTPStatus.FORBIDDEN
            return self._json({"error": message}, status=status, headers=headers)
        except ControlRoomApiError as exc:
            status = HTTPStatus.NOT_FOUND if "disabled" in str(exc) else HTTPStatus.SERVICE_UNAVAILABLE
            return self._json({"error": str(exc)}, status=status, headers=headers)

    def _handle(self, method: str, path: str, headers: dict[str, str]) -> ApiResponse:
        if method.upper() != "GET":
            return self._json({"error": "Endpoint is read-only."}, status=HTTPStatus.METHOD_NOT_ALLOWED, headers=headers)

        parsed = urlparse(path)
        route = parsed.path.rstrip("/") or "/"
        if route == "/health":
            return self._json(
                {
                    "status": "ok",
                    "service": "The Synthetic Firm Public Progress API",
                    "readOnly": True,
                    "generatedAt": utc_iso(),
                },
                headers=headers,
            )
        if route == "/api/public/control-room/snapshot":
            self._require_public()
            return self._json(self._snapshot("public"), headers=headers)
        if route == "/api/public/reports/latest":
            self._require_public()
            snapshot = self._snapshot("public")
            return self._json(snapshot["publicDailyReport"], headers=headers)
        if route == "/api/public/human-tasks/summary":
            self._require_public()
            snapshot = self._snapshot("public")
            return self._json(snapshot["humanTaskSummary"], headers=headers)
        if route == "/api/public/control-room/events":
            self._require_public()
            return self._sse(audience="public", headers=headers)
        if route == "/api/founder/control-room/snapshot":
            self._require_founder(headers)
            return self._json(self._snapshot("founder"), headers=headers)
        if route == "/api/founder/human-tasks":
            self._require_founder(headers)
            snapshot = self._snapshot("founder")
            return self._json(snapshot["humanTaskSummary"], headers=headers)
        if route == "/api/founder/control-room/events":
            self._require_founder(headers)
            return self._sse(audience="founder", headers=headers)
        return self._json({"error": "Endpoint not found."}, status=HTTPStatus.NOT_FOUND, headers=headers)

    def _snapshot(self, audience: str) -> dict[str, Any]:
        store = Store()
        try:
            return build_control_room_snapshot(store, audience=audience)
        finally:
            store.close()

    def _require_public(self) -> None:
        if not self.config.public_enabled:
            raise ControlRoomApiError("Public progress API is disabled")

    def _require_founder(self, headers: dict[str, str]) -> None:
        if not self.config.founder_enabled:
            raise ControlRoomApiError("Founder progress API is disabled")
        expected = self.config.founder_token
        if not expected:
            raise ControlRoomApiError("Founder token is required")
        auth = headers.get("authorization") or headers.get("Authorization") or ""
        prefix = "Bearer "
        if not auth.startswith(prefix):
            raise PermissionError("Founder token is required")
        provided = auth[len(prefix) :]
        if not hmac.compare_digest(provided, expected):
            raise PermissionError("Founder token is invalid")

    def _json(
        self,
        payload: dict[str, Any],
        *,
        status: HTTPStatus = HTTPStatus.OK,
        headers: dict[str, str],
    ) -> ApiResponse:
        body = json.dumps(payload, sort_keys=True).encode("utf-8") + b"\n"
        return ApiResponse(status=int(status), body=body, headers=self._common_headers(headers))

    def _sse(self, *, audience: str, headers: dict[str, str]) -> ApiResponse:
        snapshot = self._snapshot(audience)
        events = [
            ("heartbeat", {"generatedAt": utc_iso(), "readOnly": True}),
            ("snapshot", snapshot),
            ("runtime", snapshot["runtime"]),
            ("report", snapshot["publicDailyReport"]),
            ("human_task_summary", snapshot["humanTaskSummary"]),
            ("audit", snapshot["audit"]),
        ]
        payload = b"".join(_sse_event(name, data) for name, data in events)
        return ApiResponse(
            status=200,
            body=payload,
            content_type="text/event-stream; charset=utf-8",
            headers=(
                *self._common_headers(headers),
                ("Cache-Control", "no-cache"),
                ("Connection", "keep-alive"),
            ),
        )

    def _common_headers(self, request_headers: dict[str, str]) -> tuple[tuple[str, str], ...]:
        origin = request_headers.get("origin") or request_headers.get("Origin")
        headers = [
            ("X-Content-Type-Options", "nosniff"),
            ("Referrer-Policy", "no-referrer"),
            ("Cache-Control", "no-store"),
        ]
        if origin and self.config.origin_allowed(origin):
            headers.append(("Access-Control-Allow-Origin", origin))
            headers.append(("Vary", "Origin"))
        return tuple(headers)


def serve_control_room_api(
    *,
    host: str | None = None,
    port: int | None = None,
    audience: str = "public",
    reload: bool = False,
) -> None:
    if audience != "public":
        raise ControlRoomApiError("Only the public API server is supported by this command in Phase 8C")
    if reload:
        raise ControlRoomApiError("Reload mode is not implemented for the stdlib read-only API server")
    base = load_api_config()
    config = ControlRoomApiConfig(
        host=host or base.host,
        port=port or base.port,
        allowed_origins=base.allowed_origins,
        public_enabled=base.public_enabled,
        founder_enabled=base.founder_enabled,
        founder_token=base.founder_token,
        sse_interval_seconds=base.sse_interval_seconds,
    )
    api = ControlRoomApi(config)
    handler = _handler_for(api)
    server = ThreadingHTTPServer((config.host, config.port), handler)
    try:
        server.serve_forever()
    finally:
        server.server_close()


def build_serve_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Serve the read-only public progress API.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument("--audience", choices=["public"], default="public")
    parser.add_argument("--reload", action="store_true")
    return parser


def _handler_for(api: ControlRoomApi):
    class Handler(BaseHTTPRequestHandler):
        server_version = "SyntheticFirmControlRoomAPI/1"

        def do_GET(self) -> None:  # noqa: N802
            self._send(api.handle("GET", self.path, dict(self.headers)))

        def do_POST(self) -> None:  # noqa: N802
            self._send(api.handle("POST", self.path, dict(self.headers)))

        def log_message(self, format: str, *args: object) -> None:
            return

        def _send(self, response: ApiResponse) -> None:
            self.send_response(response.status)
            self.send_header("Content-Type", response.content_type)
            for key, value in response.headers:
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(response.body)

    return Handler


def _sse_event(name: str, data: dict[str, Any]) -> bytes:
    safe_data = redact_auth_text(json.dumps(data, sort_keys=True))
    return f"event: {name}\ndata: {safe_data}\n\n".encode("utf-8")

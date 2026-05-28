"""Read-only public progress window smoke checks."""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any


READ_ONLY_MARKERS = (
    "Public Progress Window",
    "Read-only public view",
    "Real TSF runtime data only",
    'data-tsf-public-progress-window="true"',
    'data-tsf-read-only="true"',
)

MUTATION_CONTROL_PATTERNS = (
    r"<button[^>]*>\s*approve\s*</button",
    r"<button[^>]*>\s*deny\s*</button",
    r"<button[^>]*>\s*pause\s*</button",
    r"<button[^>]*>\s*resume\s*</button",
    r"<button[^>]*>\s*kill\s*</button",
    r"<button[^>]*>\s*create\s+task\s*</button",
    r"<input[^>]*(command|chat)",
    r"<textarea[^>]*(command|chat)",
    r"data-action=[\"'](approve|deny|pause|resume|kill|create-task)[\"']",
)


@dataclass(frozen=True)
class PublicProgressSmokeResult:
    frontend_url: str
    api_url: str
    passed: bool
    frontend_status: int | None
    read_only_marker_detected: bool
    mutation_controls_detected: bool
    api_health_ok: bool
    snapshot_ok: bool
    snapshot_audience: str | None
    snapshot_truthfulness: str | None
    sse_reachable: bool
    cors_ok: bool
    cors_allowed_origin: str | None
    frontend_uses_api_base_url: bool
    frontend_uses_sse_mode: bool
    empty_state_detected: bool
    errors: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "frontendUrl": self.frontend_url,
            "apiUrl": self.api_url,
            "passed": self.passed,
            "frontendStatus": self.frontend_status,
            "readOnlyMarkerDetected": self.read_only_marker_detected,
            "mutationControlsDetected": self.mutation_controls_detected,
            "apiHealthOk": self.api_health_ok,
            "snapshotOk": self.snapshot_ok,
            "snapshotAudience": self.snapshot_audience,
            "snapshotTruthfulness": self.snapshot_truthfulness,
            "sseReachable": self.sse_reachable,
            "corsOk": self.cors_ok,
            "corsAllowedOrigin": self.cors_allowed_origin,
            "frontendUsesApiBaseUrl": self.frontend_uses_api_base_url,
            "frontendUsesSseMode": self.frontend_uses_sse_mode,
            "emptyStateDetected": self.empty_state_detected,
            "errors": list(self.errors),
        }


def run_public_progress_e2e_smoke(*, frontend_url: str, api_url: str) -> PublicProgressSmokeResult:
    """Run a bounded read-only smoke against the public frontend and API."""

    clean_frontend = _clean_url(frontend_url)
    clean_api = _clean_url(api_url)
    errors: list[str] = []

    frontend_status: int | None = None
    frontend_body = ""
    bundle_text = ""
    try:
        frontend_status, frontend_body = _fetch_text(clean_frontend, max_bytes=150_000)
        bundle_text = _fetch_frontend_bundles(clean_frontend, frontend_body)
    except Exception as exc:  # noqa: BLE001 - command reports safe redacted failure text.
        errors.append(f"Frontend fetch failed: {type(exc).__name__}")

    combined_frontend = f"{frontend_body}\n{bundle_text}"
    read_only_marker = all(marker in combined_frontend for marker in READ_ONLY_MARKERS)
    mutation_controls = _contains_mutation_controls(combined_frontend)
    frontend_uses_api = clean_api in combined_frontend
    frontend_uses_sse = "EventSource" in combined_frontend or "data_source=sse" in combined_frontend or '"sse"' in combined_frontend

    api_health_ok = False
    try:
        _status, health_body = _fetch_text(f"{clean_api}/health", max_bytes=20_000)
        health = json.loads(health_body)
        api_health_ok = health.get("status") == "ok" and health.get("readOnly") is True
    except Exception as exc:  # noqa: BLE001
        errors.append(f"API health failed: {type(exc).__name__}")

    snapshot_ok = False
    snapshot_audience: str | None = None
    snapshot_truthfulness: str | None = None
    empty_state_detected = False
    try:
        _status, snapshot_body = _fetch_text(f"{clean_api}/api/public/control-room/snapshot", max_bytes=800_000)
        snapshot = json.loads(snapshot_body)
        snapshot_audience = snapshot.get("audience")
        snapshot_truthfulness = snapshot.get("truthfulness")
        snapshot_ok = snapshot_audience == "public" and snapshot_truthfulness == "real_runtime_data_only"
        empty_text = json.dumps(snapshot, sort_keys=True)
        empty_state_detected = (
            "No public report generated yet." in empty_text
            or "No completed tasks today." in empty_text
            or "No public human tasks pending." in empty_text
        )
    except Exception as exc:  # noqa: BLE001
        errors.append(f"Snapshot check failed: {type(exc).__name__}")

    cors_ok = False
    cors_allowed_origin: str | None = None
    try:
        origin = _origin_for(clean_frontend)
        req = urllib.request.Request(
            f"{clean_api}/api/public/control-room/snapshot",
            headers={"Origin": origin},
            method="GET",
        )
        with urllib.request.urlopen(req, timeout=20) as response:
            cors_allowed_origin = response.headers.get("Access-Control-Allow-Origin")
            cors_ok = cors_allowed_origin == origin
    except Exception as exc:  # noqa: BLE001
        errors.append(f"CORS check failed: {type(exc).__name__}")

    sse_reachable = False
    try:
        req = urllib.request.Request(
            f"{clean_api}/api/public/control-room/events",
            headers={"Accept": "text/event-stream"},
            method="GET",
        )
        with urllib.request.urlopen(req, timeout=8) as response:
            content_type = response.headers.get("Content-Type", "")
            chunk = response.read(512).decode("utf-8", "replace")
            sse_reachable = response.status == 200 and ("text/event-stream" in content_type or "event:" in chunk or "data:" in chunk)
    except TimeoutError:
        errors.append("SSE check timed out")
    except Exception as exc:  # noqa: BLE001
        errors.append(f"SSE check failed: {type(exc).__name__}")

    passed = (
        frontend_status == 200
        and read_only_marker
        and not mutation_controls
        and api_health_ok
        and snapshot_ok
        and cors_ok
        and sse_reachable
        and frontend_uses_api
        and frontend_uses_sse
    )
    return PublicProgressSmokeResult(
        frontend_url=clean_frontend,
        api_url=clean_api,
        passed=passed,
        frontend_status=frontend_status,
        read_only_marker_detected=read_only_marker,
        mutation_controls_detected=mutation_controls,
        api_health_ok=api_health_ok,
        snapshot_ok=snapshot_ok,
        snapshot_audience=snapshot_audience,
        snapshot_truthfulness=snapshot_truthfulness,
        sse_reachable=sse_reachable,
        cors_ok=cors_ok,
        cors_allowed_origin=cors_allowed_origin,
        frontend_uses_api_base_url=frontend_uses_api,
        frontend_uses_sse_mode=frontend_uses_sse,
        empty_state_detected=empty_state_detected,
        errors=tuple(errors),
    )


def _fetch_text(url: str, *, max_bytes: int) -> tuple[int, str]:
    req = urllib.request.Request(url, headers={"User-Agent": "TSF-public-progress-smoke/1.0"})
    with urllib.request.urlopen(req, timeout=25) as response:
        return response.status, response.read(max_bytes).decode("utf-8", "replace")


def _fetch_frontend_bundles(frontend_url: str, html: str) -> str:
    base = frontend_url.rstrip("/")
    origin = _origin_for(frontend_url)
    chunks: list[str] = []
    for src in re.findall(r'<script[^>]+src=["\']([^"\']+\.js)["\']', html):
        if src.startswith("http://") or src.startswith("https://"):
            script_url = src
        elif src.startswith("/"):
            script_url = origin + src
        else:
            script_url = f"{base}/{src}"
        try:
            _status, text = _fetch_text(script_url, max_bytes=800_000)
            chunks.append(text)
        except (urllib.error.URLError, TimeoutError, ValueError):
            continue
    return "\n".join(chunks)


def _contains_mutation_controls(text: str) -> bool:
    lowered = text.lower()
    return any(re.search(pattern, lowered, flags=re.IGNORECASE) for pattern in MUTATION_CONTROL_PATTERNS)


def _clean_url(url: str) -> str:
    parsed = urllib.parse.urlparse(url.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Expected an http(s) URL")
    return urllib.parse.urlunparse((parsed.scheme, parsed.netloc, parsed.path.rstrip("/"), "", "", ""))


def _origin_for(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    return urllib.parse.urlunparse((parsed.scheme, parsed.netloc, "", "", "", ""))

from __future__ import annotations

import json

from synthetic_firm.public_progress_smoke import run_public_progress_e2e_smoke


def test_public_progress_smoke_passes_with_render_api_and_read_only_frontend(monkeypatch):
    frontend = "https://preview.vercel.app"
    api = "https://api.onrender.com"
    html = (
        '<div data-tsf-public-progress-window="true" data-tsf-read-only="true">'
        "Public Progress Window Read-only public view Real TSF runtime data only"
        '</div><script type="module" src="/assets/index.js"></script>'
    )
    bundle = f'const api="{api}"; const mode="sse"; new EventSource(api + "/events");'
    snapshot = {
        "audience": "public",
        "truthfulness": "real_runtime_data_only",
        "emptyState": "No completed tasks today. No public human tasks pending.",
    }

    def fake_urlopen(request, timeout=25):
        url = request.full_url if hasattr(request, "full_url") else request
        headers = {}
        body = "{}"
        if url == frontend:
            body = html
        elif url == f"{frontend}/assets/index.js":
            body = bundle
        elif url == f"{api}/health":
            body = json.dumps({"status": "ok", "readOnly": True})
        elif url == f"{api}/api/public/control-room/snapshot":
            body = json.dumps(snapshot)
            if hasattr(request, "headers") and request.headers.get("Origin") == frontend:
                headers["Access-Control-Allow-Origin"] = frontend
        elif url == f"{api}/api/public/control-room/events":
            headers["Content-Type"] = "text/event-stream"
            body = "event: heartbeat\ndata: {}\n\n"
        return _FakeResponse(body, headers=headers)

    monkeypatch.setattr("synthetic_firm.public_progress_smoke.urllib.request.urlopen", fake_urlopen)

    result = run_public_progress_e2e_smoke(frontend_url=frontend, api_url=api)

    assert result.passed is True
    assert result.read_only_marker_detected is True
    assert result.mutation_controls_detected is False
    assert result.frontend_uses_api_base_url is True
    assert result.frontend_uses_sse_mode is True
    assert result.cors_ok is True
    assert result.empty_state_detected is True


def test_public_progress_smoke_fails_on_public_mutation_control(monkeypatch):
    frontend = "https://preview.vercel.app"
    api = "https://api.onrender.com"
    html = (
        '<div data-tsf-public-progress-window="true" data-tsf-read-only="true">'
        "Public Progress Window Read-only public view Real TSF runtime data only"
        "</div><button>Approve</button>"
    )

    def fake_urlopen(request, timeout=25):
        url = request.full_url if hasattr(request, "full_url") else request
        if url == frontend:
            return _FakeResponse(html)
        if url == f"{api}/health":
            return _FakeResponse(json.dumps({"status": "ok", "readOnly": True}))
        if url == f"{api}/api/public/control-room/snapshot":
            return _FakeResponse(
                json.dumps({"audience": "public", "truthfulness": "real_runtime_data_only"}),
                headers={"Access-Control-Allow-Origin": frontend},
            )
        if url == f"{api}/api/public/control-room/events":
            return _FakeResponse("event: heartbeat\ndata: {}\n\n", headers={"Content-Type": "text/event-stream"})
        return _FakeResponse("")

    monkeypatch.setattr("synthetic_firm.public_progress_smoke.urllib.request.urlopen", fake_urlopen)

    result = run_public_progress_e2e_smoke(frontend_url=frontend, api_url=api)

    assert result.passed is False
    assert result.mutation_controls_detected is True


class _FakeResponse:
    def __init__(self, body: str, *, headers: dict[str, str] | None = None, status: int = 200):
        self._body = body.encode("utf-8")
        self.headers = headers or {}
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self, max_bytes=-1):
        if max_bytes is None or max_bytes < 0:
            return self._body
        return self._body[:max_bytes]

from __future__ import annotations

import json

from synthetic_firm.control_room_api import ControlRoomApi, ControlRoomApiConfig
from synthetic_firm.execution_queue import enqueue_action
from synthetic_firm.store import Store


def _json(response):
    return json.loads(response.body.decode("utf-8"))


def test_health_endpoint(monkeypatch, tmp_path):
    monkeypatch.setenv("TSF_HOME", str(tmp_path))
    api = ControlRoomApi()

    response = api.handle("GET", "/health", {"Origin": "http://localhost:5173"})
    payload = _json(response)

    assert response.status == 200
    assert payload["status"] == "ok"
    assert payload["readOnly"] is True
    assert ("Access-Control-Allow-Origin", "http://localhost:5173") in response.headers


def test_public_snapshot_endpoint_is_real_public_and_secret_free(monkeypatch, tmp_path):
    monkeypatch.setenv("TSF_HOME", str(tmp_path))
    store = Store()
    store.create_human_task(
        requested_by_agent_id="atlas",
        title="Connect provider",
        plain_english_request="Connect provider for private@example.com using sk-secret-value",
        reason="Founder account access is required.",
        public_summary="Founder provider access task pending.",
        private_details="Private lead private@example.com and token sk-private-token-value.",
    )
    before = store.runtime_status()
    store.close()
    api = ControlRoomApi()

    response = api.handle("GET", "/api/public/control-room/snapshot", {"Origin": "http://localhost:5173"})
    payload = _json(response)
    dumped = response.body.decode("utf-8")

    assert response.status == 200
    assert payload["audience"] == "public"
    assert payload["truthfulness"] == "real_runtime_data_only"
    assert payload["dataMode"] == "real_snapshot"
    assert "Founder provider access task pending." in dumped
    assert "private@example.com" not in dumped
    assert "sk-secret-value" not in dumped
    assert "sk-private-token-value" not in dumped
    assert Store().runtime_status() == before


def test_public_report_empty_state(monkeypatch, tmp_path):
    monkeypatch.setenv("TSF_HOME", str(tmp_path))
    Store().close()
    api = ControlRoomApi()

    response = api.handle("GET", "/api/public/reports/latest")
    payload = _json(response)

    assert response.status == 200
    assert payload["type"] == "public_daily_report"
    assert payload["emptyState"]["completed"] == "No completed tasks today."
    assert payload["truthfulness"] == "Based on real TSF runtime data. No mock data. No fabricated progress."


def test_public_human_task_summary_excludes_private_details(monkeypatch, tmp_path):
    monkeypatch.setenv("TSF_HOME", str(tmp_path))
    store = Store()
    store.create_human_task(
        requested_by_agent_id="forge",
        title="Domain task",
        plain_english_request="Buy domain for private@example.com",
        reason="Owner action is required.",
        public_summary="Founder domain task pending.",
        private_details="Domain account https://secret.example and private@example.com.",
    )
    store.close()
    api = ControlRoomApi()

    response = api.handle("GET", "/api/public/human-tasks/summary")
    dumped = response.body.decode("utf-8")
    payload = _json(response)

    assert payload["pendingCount"] == 1
    assert "Founder domain task pending." in dumped
    assert "private@example.com" not in dumped
    assert "secret.example" not in dumped


def test_founder_endpoints_require_token_and_still_redact(monkeypatch, tmp_path):
    monkeypatch.setenv("TSF_HOME", str(tmp_path))
    monkeypatch.setenv("TSF_CONTROL_ROOM_FOUNDER_ENABLED", "true")
    monkeypatch.setenv("TSF_CONTROL_ROOM_FOUNDER_TOKEN", "founder-test-token")
    store = Store()
    store.create_human_task(
        requested_by_agent_id="atlas",
        title="Provider issue",
        plain_english_request="Use sk-provider-secret-value",
        reason="Owner access needed.",
        public_summary="Founder provider task pending.",
        private_details="Token sk-private-token-value.",
    )
    store.close()
    api = ControlRoomApi()

    assert api.handle("GET", "/api/founder/control-room/snapshot").status == 401
    assert api.handle("GET", "/api/founder/control-room/snapshot", {"Authorization": "Bearer wrong"}).status == 403
    response = api.handle(
        "GET",
        "/api/founder/control-room/snapshot",
        {"Authorization": "Bearer founder-test-token"},
    )
    dumped = response.body.decode("utf-8")

    assert response.status == 200
    assert _json(response)["audience"] == "founder"
    assert "Owner access needed." in dumped
    assert "sk-provider-secret-value" not in dumped
    assert "sk-private-token-value" not in dumped
    assert "founder-test-token" not in dumped


def test_founder_endpoints_disabled_by_default(monkeypatch, tmp_path):
    monkeypatch.setenv("TSF_HOME", str(tmp_path))
    monkeypatch.delenv("TSF_CONTROL_ROOM_FOUNDER_ENABLED", raising=False)
    api = ControlRoomApi()

    response = api.handle("GET", "/api/founder/control-room/snapshot")

    assert response.status == 404


def test_sse_public_stream_is_sanitized_and_read_only(monkeypatch, tmp_path):
    monkeypatch.setenv("TSF_HOME", str(tmp_path))
    store = Store()
    task = store.create_task(
        title="Public API task",
        objective="Expose real data only.",
        created_by_agent_id="atlas",
        plain_english_summary="No secret sk-api-test-secret-value.",
    )
    enqueue_action(store, task_id=task.task_id, agent_id="atlas", action="status_check")
    runtime_before = store.runtime_status()
    store.close()

    response = ControlRoomApi().handle("GET", "/api/public/control-room/events")
    body = response.body.decode("utf-8")

    assert response.status == 200
    assert response.content_type.startswith("text/event-stream")
    assert "event: heartbeat" in body
    assert "event: snapshot" in body
    assert "sk-api-test-secret-value" not in body
    assert Store().runtime_status() == runtime_before


def test_api_is_read_only_and_has_no_mutation_endpoints(monkeypatch, tmp_path):
    monkeypatch.setenv("TSF_HOME", str(tmp_path))
    api = ControlRoomApi()

    for route in [
        "/approve",
        "/deny",
        "/pause",
        "/resume",
        "/kill",
        "/tasks",
        "/messages",
        "/commands",
        "/queue/process",
    ]:
        assert api.handle("POST", route).status == 405
        assert api.handle("GET", route).status == 404


def test_disallowed_origin_gets_no_cors_header(monkeypatch, tmp_path):
    monkeypatch.setenv("TSF_HOME", str(tmp_path))
    config = ControlRoomApiConfig(allowed_origins=frozenset({"http://localhost:5173"}))
    response = ControlRoomApi(config).handle("GET", "/health", {"Origin": "http://evil.example"})

    assert response.status == 200
    assert not any(key == "Access-Control-Allow-Origin" for key, _value in response.headers)

from __future__ import annotations

import json

from synthetic_firm.cli import main
from synthetic_firm.control_room_export import build_control_room_snapshot
from synthetic_firm.execution_queue import enqueue_action
from synthetic_firm.human_tasks import format_human_task_for_telegram
from synthetic_firm.store import Store
from synthetic_firm.telegram_adapter import parse_telegram_command


def test_control_room_export_empty_store(monkeypatch, tmp_path):
    monkeypatch.setenv("TSF_HOME", str(tmp_path))
    store = Store()

    snapshot = build_control_room_snapshot(store)

    assert snapshot["schemaVersion"] == "control-room.v1"
    assert snapshot["audience"] == "public"
    assert snapshot["dataMode"] == "real_snapshot"
    assert snapshot["truthfulness"] == "real_runtime_data_only"
    assert snapshot["runtime"]["status"] == "active"
    assert snapshot["workday"]["timezone"] == "Europe/Paris"
    assert len(snapshot["agents"]) == 5
    assert snapshot["tasks"] == []
    assert snapshot["approvals"] == []
    assert snapshot["executionQueue"] == []
    assert snapshot["audit"]["verified"] is True
    assert snapshot["publicDailyReport"]["emptyState"]["completed"] == "No completed tasks today."
    assert snapshot["publicDailyReport"]["emptyState"]["humanTasks"] == "No public human tasks pending."
    store.close()


def test_control_room_export_includes_persisted_entities(monkeypatch, tmp_path):
    monkeypatch.setenv("TSF_HOME", str(tmp_path))
    store = Store()
    task = store.create_task(
        title="Snapshot task",
        objective="Show persisted task in the public progress window.",
        created_by_agent_id="atlas",
        assigned_agent_id="forge",
        plain_english_summary="Forge should build the read-only snapshot.",
        budget_limit=4.0,
        max_steps=8,
    )
    approval = store.create_approval(
        task_id=task.task_id,
        agent_id="forge",
        requested_action="create_message",
        risk_level="medium",
        external_effect=False,
        plain_english_request="Forge requests review before queueing a message.",
        guardian_review="Sentinel sees no external effect.",
    )
    store.create_message(
        sender_agent_id="atlas",
        channel="company",
        task_id=task.task_id,
        content="Use a safe public progress summary only.",
    )
    item = enqueue_action(store, task_id=task.task_id, agent_id="forge", action="status_check")
    store.record_budget_usage(
        agent_id="forge",
        task_id=task.task_id,
        amount_usd=1.25,
        loop_steps=1,
        tool_calls=1,
        summary="Safe snapshot budget usage.",
    )
    store.save_daily_report(
        report_date="2026-05-28",
        content="Daily report body.",
        telegram_summary="Daily report summary.",
    )

    snapshot = build_control_room_snapshot(store)

    assert snapshot["tasks"][0]["id"] == task.task_id
    assert snapshot["approvals"][0]["id"] == approval.approval_id
    assert snapshot["executionQueue"][0]["id"] == item.queue_id
    assert snapshot["messages"]["count"] == 1
    assert snapshot["budget"]["companyUsage"] == 1.25
    assert snapshot["reports"][0]["summary"] == "Daily report summary."
    assert any(event["type"] == "approval.requested" for event in snapshot["events"])
    store.close()


def test_public_export_sanitizes_human_tasks_and_private_details(monkeypatch, tmp_path):
    monkeypatch.setenv("TSF_HOME", str(tmp_path))
    store = Store()
    task = store.create_human_task(
        requested_by_agent_id="atlas",
        title="Connect provider account",
        plain_english_request="Authorize provider account for private@example.com",
        reason="Forge needs owner access.",
        public_summary="Founder provider access task pending.",
        private_details="Use private lead private@example.com and https://private.example/token",
        cost_estimate="No cost",
    )
    store.update_human_task(task.human_task_id, founder_note="API key sk-private-founder-note-value")

    public_snapshot = build_control_room_snapshot(store, audience="public")
    dumped = json.dumps(public_snapshot)

    assert public_snapshot["humanTaskSummary"]["pendingCount"] == 1
    assert "Founder provider access task pending." in dumped
    assert "private@example.com" not in dumped
    assert "https://private.example" not in dumped
    assert "privateDetailsRedacted" not in dumped
    assert "sk-private-founder-note-value" not in dumped
    assert public_snapshot["humanTasks"][0]["publicSummary"] == "Founder provider access task pending."
    store.close()


def test_founder_export_keeps_richer_human_task_summary_but_excludes_secrets(monkeypatch, tmp_path):
    monkeypatch.setenv("TSF_HOME", str(tmp_path))
    store = Store()
    task = store.create_human_task(
        requested_by_agent_id="forge",
        title="Connect deployment account",
        plain_english_request="Connect account using token sk-founder-secret-value",
        reason="Account owner access is required.",
        public_summary="Founder account setup task pending.",
        private_details="Repo detail includes token sk-repo-secret-value",
    )

    founder_snapshot = build_control_room_snapshot(store, audience="founder")
    dumped = json.dumps(founder_snapshot)

    assert founder_snapshot["audience"] == "founder"
    assert founder_snapshot["privateFounderReport"]["exactHumanTasks"][0]["humanTaskId"] == task.human_task_id
    assert "Account owner access is required." in dumped
    assert "sk-founder-secret-value" not in dumped
    assert "sk-repo-secret-value" not in dumped
    assert "[redacted]" in dumped
    store.close()


def test_public_daily_report_is_generated_from_real_tasks(monkeypatch, tmp_path):
    monkeypatch.setenv("TSF_HOME", str(tmp_path))
    store = Store()
    completed = store.create_task(
        title="Publish public progress window",
        objective="Show only verified progress.",
        created_by_agent_id="atlas",
        assigned_agent_id="forge",
    )
    store.assign_task(completed.task_id, "forge")
    store.update_task_status(completed.task_id, "in_progress")
    store.complete_task(completed.task_id, summary="Forge completed the public observer view.")
    blocked = store.create_task(
        title="Domain setup for private@example.com",
        objective="Wait for owner action.",
        created_by_agent_id="atlas",
        assigned_agent_id="pulse",
    )
    store.assign_task(blocked.task_id, "pulse")
    store.mark_blocked(blocked.task_id, summary="Founder domain setup is pending.")

    snapshot = build_control_room_snapshot(store, audience="public")
    report = snapshot["publicDailyReport"]
    dumped = json.dumps(report)

    assert "Publish public progress window" in report["completed"]
    assert "Domain setup" in dumped
    assert "private@example.com" not in dumped
    assert report["truthfulness"] == "Based on real TSF runtime data. No mock data. No fabricated progress."
    store.close()


def test_human_task_telegram_formatting_and_commands(monkeypatch, tmp_path):
    monkeypatch.setenv("TSF_HOME", str(tmp_path))
    store = Store()
    task = store.create_human_task(
        requested_by_agent_id="atlas",
        title="Connect domain",
        plain_english_request="Connect the public site domain.",
        reason="Domain binding needs founder account access.",
        public_summary="Founder domain configuration task pending.",
    )

    message = format_human_task_for_telegram(task)

    assert "HUMAN TASK -" in message
    assert f"/done {task.human_task_id}" in message
    assert f"/blocked {task.human_task_id}" in message
    assert parse_telegram_command(f"/done {task.human_task_id}").human_task_id == task.human_task_id
    assert parse_telegram_command(f"/blocked {task.human_task_id}").human_task_id == task.human_task_id
    parsed_note = parse_telegram_command(f"/note {task.human_task_id} Wait until Monday")
    assert parsed_note.message == "Wait until Monday"
    store.close()


def test_frontend_public_observer_source_has_no_snapshot_mutation_controls():
    index_html = open("apps/control-room/index.html", encoding="utf-8").read()
    app_shell = open("apps/control-room/src/App.tsx", encoding="utf-8").read()
    approval_panel = open(
        "apps/control-room/src/components/panels/ApprovalInbox.tsx", encoding="utf-8"
    ).read()
    runtime_header = open(
        "apps/control-room/src/components/panels/RuntimeHeader.tsx", encoding="utf-8"
    ).read()

    assert "Public Progress Window" in index_html
    assert "Read-only public view" in index_html
    assert "Real TSF runtime data only" in index_html
    assert 'data-tsf-public-progress-window="true"' in index_html
    assert 'data-tsf-read-only="true"' in index_html
    assert "data-tsf-public-progress-window=\"true\"" in app_shell
    assert "data-tsf-read-only=\"true\"" in app_shell
    assert "<button" not in index_html.lower()
    assert "command input" not in index_html.lower()
    assert "chat input" not in index_html.lower()
    assert "create task" not in index_html.lower()
    assert "!readOnly && runtimeState !== 'killed'" in approval_panel
    assert "Public observer" in runtime_header
    assert "Read-only public progress window" in open(
        "apps/control-room/src/components/panels/ReadOnlyStatusPanel.tsx", encoding="utf-8"
    ).read()


def test_control_room_export_redacts_secrets(monkeypatch, tmp_path):
    monkeypatch.setenv("TSF_HOME", str(tmp_path))
    store = Store()
    secret = "sk-kimi-sensitive-test-value"
    store.create_task(
        title=f"Snapshot {secret}",
        objective=f"Do not leak {secret}",
        created_by_agent_id="atlas",
        plain_english_summary=f"Summary has Bearer secret-token-value and api_key={secret}",
    )

    dumped = json.dumps(build_control_room_snapshot(store))

    assert secret not in dumped
    assert "secret-token-value" not in dumped
    assert "[redacted]" in dumped
    store.close()


def test_control_room_export_handles_tampered_audit(monkeypatch, tmp_path):
    monkeypatch.setenv("TSF_HOME", str(tmp_path))
    store = Store()
    store.create_task(
        title="Tamper check",
        objective="Detect unsafe audit mutation.",
        created_by_agent_id="atlas",
        plain_english_summary="Audit summary should report failed verification.",
    )
    store.connection.execute("UPDATE audit_log SET summary = ? WHERE sequence_number = 1", ("tampered",))
    store.connection.commit()

    snapshot = build_control_room_snapshot(store)

    assert snapshot["audit"]["verified"] is False
    assert snapshot["audit"]["lastSequence"] == 1
    store.close()


def test_control_room_export_cli_stdout_and_output(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("TSF_HOME", str(tmp_path / "home"))
    output = tmp_path / "control-room-snapshot.json"

    assert main(["export-control-room-state", "--stdout"]) == 0
    stdout_snapshot = json.loads(capsys.readouterr().out)
    assert stdout_snapshot["schemaVersion"] == "control-room.v1"
    assert stdout_snapshot["audience"] == "public"

    assert main(["export-control-room-state", "--output", str(output), "--audience", "founder"]) == 0
    file_snapshot = json.loads(output.read_text(encoding="utf-8"))
    assert file_snapshot["schemaVersion"] == "control-room.v1"
    assert file_snapshot["audience"] == "founder"

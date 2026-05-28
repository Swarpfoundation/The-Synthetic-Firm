from __future__ import annotations

import pytest

from synthetic_firm.approval import create_approval_request
from synthetic_firm.report import DailyReportInput, generate_daily_report
from synthetic_firm.store import Store
from synthetic_firm.telegram_adapter import TelegramAdapterError, format_outgoing_approval, parse_telegram_command


@pytest.mark.parametrize(
    ("text", "command", "approval_id"),
    [
        ("/approve appr_1", "approve", "appr_1"),
        ("/deny appr_1", "deny", "appr_1"),
        ("/status", "status", None),
        ("/pause", "pause", None),
        ("/resume", "resume", None),
        ("/budget", "budget", None),
        ("/report", "report", None),
    ],
)
def test_telegram_command_parser(text, command, approval_id):
    parsed = parse_telegram_command(text)

    assert parsed.command == command
    assert parsed.approval_id == approval_id


def test_telegram_parser_rejects_malformed():
    with pytest.raises(TelegramAdapterError):
        parse_telegram_command("approve appr_1")
    with pytest.raises(TelegramAdapterError):
        parse_telegram_command("/approve")


def test_telegram_approval_message_plain_english():
    approval = create_approval_request(
        task_id="task_1",
        agent_id="forge",
        requested_action="internal_note",
        risk_level="medium",
        external_effect=False,
        plain_english_request="Allow Forge to record an internal note.",
    )

    message = format_outgoing_approval(approval)

    assert "The Synthetic Firm approval request" in message
    assert "/approve" in message
    assert "/resume" in message


def test_daily_report_persists_and_avoids_secret(monkeypatch, tmp_path):
    monkeypatch.setenv("TSF_HOME", str(tmp_path))
    store = Store()
    report = generate_daily_report(DailyReportInput(questions_for_founder=("Which market next?",)))
    report_id = store.save_daily_report(
        report_date="2026-05-28",
        content=report,
        telegram_summary="The Synthetic Firm daily report\n- No blocked tasks.",
    )

    saved = store.list_daily_reports()[0]
    assert saved["report_id"] == report_id
    assert "The Synthetic Firm daily report" in saved["content"]
    assert "secret" not in saved["content"].lower()
    store.close()

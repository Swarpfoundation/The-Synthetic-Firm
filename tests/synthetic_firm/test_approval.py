from synthetic_firm.approval import create_approval_request, format_telegram_approval


def test_approval_formatting_contains_required_commands():
    approval = create_approval_request(
        task_id="task_1",
        agent_id="forge",
        requested_action="Run a risky operation",
        risk_level="high",
        external_effect=True,
        plain_english_request="Builder wants approval to perform a risky operation.",
        guardian_review="Sentinel says human approval is required.",
        approval_id="appr_test",
    )

    text = format_telegram_approval(approval)

    assert "/approve appr_test" in text
    assert "/deny appr_test" in text
    assert "/status" in text
    assert "/pause" in text
    assert "/budget" in text
    assert "Builder wants approval" in text
    assert "The Synthetic Firm approval request" in text

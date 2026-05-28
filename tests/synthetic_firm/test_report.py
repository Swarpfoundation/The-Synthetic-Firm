from synthetic_firm.approval import create_approval_request
from synthetic_firm.budget import BudgetDecision
from synthetic_firm.proposals import create_self_improvement_proposal, create_worker_proposal
from synthetic_firm.report import DailyReportInput, generate_daily_report
from synthetic_firm.task import create_task, transition_task


def test_daily_report_plain_english_safe_summary():
    task = create_task(title="Write docs", objective="Document workday OS", created_by_agent_id="atlas")
    task = transition_task(transition_task(transition_task(task, "accepted"), "assigned"), "in_progress")
    task = transition_task(task, "completed")
    approval = create_approval_request(
        task_id=task.task_id,
        agent_id="forge",
        requested_action="Use external service",
        risk_level="high",
        external_effect=True,
        plain_english_request="Builder requests human approval before any external effect.",
        guardian_review="Sentinel flagged this as high risk.",
    )
    worker = create_worker_proposal(
        proposed_by_agent_id="atlas",
        proposed_worker_name="Analyst",
        proposed_role="Internal analysis",
        business_reason="Summarize company operating risks.",
    )
    improvement = create_self_improvement_proposal(
        agent_id="sentinel",
        capability_gap="Needs clearer review checklist.",
        proposed_change="Propose a better QA checklist.",
        files_or_modules_affected=["docs/checklists/qa.md"],
    )

    report = generate_daily_report(
        DailyReportInput(
            tasks=(task,),
            approvals=(approval,),
            worker_proposals=(worker,),
            self_improvement_proposals=(improvement,),
            budget_decisions=(BudgetDecision(True, True, "Budget dry-run is within caps"),),
            questions_for_founder=("Should Sentinel review all medium-risk tasks?",),
            next_actions=("Review pending approvals.",),
        )
    )

    assert "The Synthetic Firm daily report" in report
    assert "Tasks completed" in report
    assert "Approval requests pending" in report
    assert "sk-" not in report
    assert "API_KEY" not in report

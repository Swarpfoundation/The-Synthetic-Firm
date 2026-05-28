"""Plain-English daily reports for The Synthetic Firm."""

from __future__ import annotations

from dataclasses import dataclass

from synthetic_firm.approval import ApprovalRequest
from synthetic_firm.budget import BudgetDecision
from synthetic_firm.proposals import SelfImprovementProposal, WorkerProposal
from synthetic_firm.task import Task

REPORT_TYPES = frozenset({"public_daily_report", "private_founder_report"})


@dataclass(frozen=True)
class DailyReportInput:
    tasks: tuple[Task, ...] = ()
    approvals: tuple[ApprovalRequest, ...] = ()
    worker_proposals: tuple[WorkerProposal, ...] = ()
    self_improvement_proposals: tuple[SelfImprovementProposal, ...] = ()
    budget_decisions: tuple[BudgetDecision, ...] = ()
    questions_for_founder: tuple[str, ...] = ()
    next_actions: tuple[str, ...] = ()


def generate_daily_report(data: DailyReportInput) -> str:
    completed = [task for task in data.tasks if task.status == "completed"]
    blocked = [task for task in data.tasks if task.status == "blocked"]
    pending = [approval for approval in data.approvals if approval.status == "pending"]
    guardian_risks = _guardian_risks(data)

    lines = ["The Synthetic Firm daily report", ""]
    lines.extend(_section("Tasks completed", [task.plain_english_summary for task in completed]))
    lines.extend(_section("Tasks blocked", [task.plain_english_summary for task in blocked]))
    lines.extend(_section("Approval requests pending", [approval.plain_english_request for approval in pending]))
    lines.extend(_section("New worker proposals", [p.business_reason for p in data.worker_proposals]))
    lines.extend(_section("Self-improvement proposals", [p.proposed_change for p in data.self_improvement_proposals]))
    lines.extend(_section("Budget usage", [_budget_line(decision) for decision in data.budget_decisions]))
    lines.extend(_section("Risks flagged by Sentinel", guardian_risks))
    lines.extend(_section("Questions for founder", list(data.questions_for_founder)))
    lines.extend(_section("Next recommended actions", list(data.next_actions)))
    return "\n".join(lines).strip() + "\n"


def _section(title: str, items: list[str]) -> list[str]:
    lines = [title + ":"]
    if not items:
        lines.append("- None.")
    else:
        lines.extend(f"- {_plain(item)}" for item in items)
    lines.append("")
    return lines


def _guardian_risks(data: DailyReportInput) -> list[str]:
    risks: list[str] = []
    for approval in data.approvals:
        if approval.guardian_review:
            risks.append(approval.guardian_review)
    for proposal in data.worker_proposals:
        if proposal.guardian_review:
            risks.append(proposal.guardian_review)
    for proposal in data.self_improvement_proposals:
        if proposal.guardian_review:
            risks.append(proposal.guardian_review)
    return risks


def _budget_line(decision: BudgetDecision) -> str:
    state = "allowed" if decision.allowed else "blocked"
    mode = "dry-run" if decision.dry_run else "enforced"
    return f"{state} in {mode} mode: {decision.reason}"


def _plain(value: str) -> str:
    text = str(value or "").replace("\n", " ").strip()
    return text or "None."

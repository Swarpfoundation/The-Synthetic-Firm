"""Worker and self-improvement proposal models."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import PurePosixPath
from typing import Any
from uuid import uuid4


EXTERNAL_TOOL_NAMES = frozenset(
    {
        "email_sending",
        "social_posting",
        "investor_outreach",
        "production_deploy",
        "stripe",
        "payment_tools",
        "github_write_automation",
    }
)

FORBIDDEN_SELF_IMPROVEMENT_TARGETS = frozenset(
    {
        "agents/policy.yaml",
        ".env",
        "approval_rules",
        "api_keys",
        "secrets",
        "logging_disablement",
        "main_branch_merge_logic",
    }
)


@dataclass(frozen=True)
class WorkerProposal:
    proposal_id: str
    proposed_by_agent_id: str
    proposed_worker_name: str
    proposed_role: str
    business_reason: str
    requested_tools: tuple[str, ...]
    requested_budget: float | None
    risk_level: str
    guardian_review: str | None
    status: str
    created_at: datetime


@dataclass(frozen=True)
class SelfImprovementProposal:
    proposal_id: str
    agent_id: str
    capability_gap: str
    proposed_change: str
    files_or_modules_affected: tuple[str, ...]
    permission_change_requested: bool
    budget_change_requested: bool
    risk_level: str
    guardian_review: str | None
    status: str
    created_at: datetime


class ProposalError(ValueError):
    """Raised when a proposal violates Phase 2 policy."""


def create_worker_proposal(
    *,
    proposed_by_agent_id: str,
    proposed_worker_name: str,
    proposed_role: str,
    business_reason: str,
    requested_tools: list[str] | tuple[str, ...] = (),
    requested_budget: float | None = None,
    risk_level: str = "low",
    guardian_review: str | None = None,
    now: datetime | None = None,
) -> WorkerProposal:
    tools = tuple(_clean_list(requested_tools))
    effective_risk = _risk(risk_level)
    review = _optional_str(guardian_review)
    if any(tool in EXTERNAL_TOOL_NAMES for tool in tools):
        effective_risk = "high"
        review = review or "Sentinel review required because an external tool was requested."
    return WorkerProposal(
        proposal_id=f"worker_{uuid4().hex[:10]}",
        proposed_by_agent_id=_required(proposed_by_agent_id, "proposed_by_agent_id").lower(),
        proposed_worker_name=_required(proposed_worker_name, "proposed_worker_name"),
        proposed_role=_required(proposed_role, "proposed_role"),
        business_reason=_required(business_reason, "business_reason"),
        requested_tools=tools,
        requested_budget=requested_budget,
        risk_level=effective_risk,
        guardian_review=review,
        status="proposed",
        created_at=now or datetime.now(timezone.utc),
    )


def approve_worker_for_branch(proposal: WorkerProposal) -> WorkerProposal:
    if proposal.status != "proposed":
        raise ProposalError(f"Worker proposal is already {proposal.status}")
    return replace(proposal, status="approved_for_branch")


def activate_worker(_proposal: WorkerProposal) -> WorkerProposal:
    raise ProposalError("Active worker creation is forbidden in Phase 2")


def create_self_improvement_proposal(
    *,
    agent_id: str,
    capability_gap: str,
    proposed_change: str,
    files_or_modules_affected: list[str] | tuple[str, ...],
    permission_change_requested: bool = False,
    budget_change_requested: bool = False,
    risk_level: str = "low",
    guardian_review: str | None = None,
    now: datetime | None = None,
) -> SelfImprovementProposal:
    affected = tuple(_clean_list(files_or_modules_affected))
    forbidden = _forbidden_targets(affected)
    if forbidden:
        raise ProposalError(f"Forbidden self-improvement target(s): {', '.join(forbidden)}")
    effective_risk = _risk(risk_level)
    review = _optional_str(guardian_review)
    if permission_change_requested or budget_change_requested:
        effective_risk = "high"
        review = review or "Sentinel review required because authority or budget increase was requested."
    return SelfImprovementProposal(
        proposal_id=f"self_{uuid4().hex[:10]}",
        agent_id=_required(agent_id, "agent_id").lower(),
        capability_gap=_required(capability_gap, "capability_gap"),
        proposed_change=_required(proposed_change, "proposed_change"),
        files_or_modules_affected=affected,
        permission_change_requested=bool(permission_change_requested),
        budget_change_requested=bool(budget_change_requested),
        risk_level=effective_risk,
        guardian_review=review,
        status="proposed",
        created_at=now or datetime.now(timezone.utc),
    )


def proposal_to_dict(proposal: WorkerProposal | SelfImprovementProposal) -> dict[str, Any]:
    result = proposal.__dict__.copy()
    result["created_at"] = proposal.created_at.isoformat()
    return result


def _forbidden_targets(paths: tuple[str, ...]) -> list[str]:
    found: list[str] = []
    for path in paths:
        normalized = str(PurePosixPath(path.replace("\\", "/"))).strip().lower()
        basename = normalized.rsplit("/", 1)[-1]
        for forbidden in FORBIDDEN_SELF_IMPROVEMENT_TARGETS:
            if normalized == forbidden or basename == forbidden or forbidden in normalized:
                found.append(path)
                break
    return found


def _clean_list(values: list[str] | tuple[str, ...]) -> list[str]:
    return [str(value).strip().lower() for value in values if str(value).strip()]


def _required(value: Any, name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ProposalError(f"{name} is required")
    return text


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _risk(value: Any) -> str:
    risk = str(value or "low").strip().lower()
    if risk not in {"low", "medium", "high", "critical"}:
        raise ProposalError(f"Invalid risk level: {value!r}")
    return risk

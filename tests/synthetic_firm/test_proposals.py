import pytest

from synthetic_firm.proposals import (
    ProposalError,
    activate_worker,
    create_self_improvement_proposal,
    create_worker_proposal,
)


def test_worker_proposal_cannot_become_active_without_approval():
    proposal = create_worker_proposal(
        proposed_by_agent_id="atlas",
        proposed_worker_name="Ops Analyst",
        proposed_role="Internal operations analysis",
        business_reason="Help summarize internal bottlenecks.",
    )

    with pytest.raises(ProposalError):
        activate_worker(proposal)


def test_worker_external_tool_triggers_sentinel_review():
    proposal = create_worker_proposal(
        proposed_by_agent_id="pulse",
        proposed_worker_name="Outreach Assistant",
        proposed_role="Draft outreach only",
        business_reason="Prepare drafts for founder review.",
        requested_tools=["email_sending"],
    )

    assert proposal.risk_level == "high"
    assert "Sentinel review required" in proposal.guardian_review


def test_self_improvement_permission_or_budget_change_high_risk():
    proposal = create_self_improvement_proposal(
        agent_id="forge",
        capability_gap="Needs better test templates.",
        proposed_change="Add test proposal templates.",
        files_or_modules_affected=["skills/testing/SKILL.md"],
        permission_change_requested=True,
        budget_change_requested=True,
    )

    assert proposal.risk_level == "high"
    assert "authority or budget" in proposal.guardian_review


def test_forbidden_self_improvement_targets_rejected():
    with pytest.raises(ProposalError):
        create_self_improvement_proposal(
        agent_id="sentinel",
            capability_gap="Wants policy control.",
            proposed_change="Edit approval rules.",
            files_or_modules_affected=["agents/policy.yaml"],
        )

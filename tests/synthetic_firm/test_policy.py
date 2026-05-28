from dataclasses import replace

import pytest

from synthetic_firm.agent_registry import AgentRegistry
from synthetic_firm.policy import PolicyError, load_project_policy, validate_agent_profile, validate_registry_profiles


def test_policy_accepts_default_profiles():
    registry = AgentRegistry.from_file("agents/profiles.yaml")
    policy = load_project_policy("agents/policy.yaml")

    validate_registry_profiles(registry.list(), policy)


def test_policy_rejects_forbidden_permissions():
    registry = AgentRegistry.from_file("agents/profiles.yaml")
    policy = load_project_policy("agents/policy.yaml")
    profile = registry.get("pulse")
    unsafe = replace(profile, permissions=profile.permissions + ("external_communications",))

    with pytest.raises(PolicyError, match="external_communications"):
        validate_agent_profile(unsafe, policy)


def test_policy_rejects_approval_rule_write():
    registry = AgentRegistry.from_file("agents/profiles.yaml")
    policy = load_project_policy("agents/policy.yaml")
    profile = registry.get("atlas")
    unsafe = replace(profile, permissions=profile.permissions + ("approval_rules_write",))

    with pytest.raises(PolicyError, match="approval_rules_write"):
        validate_agent_profile(unsafe, policy)

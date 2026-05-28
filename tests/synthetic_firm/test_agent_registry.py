from pathlib import Path

import pytest

from synthetic_firm.agent_registry import AgentRegistry, AgentRegistryError


def test_registry_loads_required_profiles():
    registry = AgentRegistry.from_file("agents/profiles.yaml")
    profiles = {profile.agent_id: profile for profile in registry.list()}

    assert set(profiles) == {"atlas", "forge", "pulse", "scout", "sentinel"}
    assert profiles["atlas"].display_name == "Atlas / CEO Agent"
    assert profiles["forge"].budget.max_turns == 70
    assert profiles["sentinel"].model_policy.provider == "kimi-coding"


def test_registry_rejects_unknown_agent():
    registry = AgentRegistry.from_file("agents/profiles.yaml")

    with pytest.raises(AgentRegistryError):
        registry.get("unknown")


def test_registry_requires_model_policy(tmp_path: Path):
    config = tmp_path / "profiles.yaml"
    config.write_text(
        """
version: 1
agents:
  atlas:
    display_name: Atlas
    permissions: []
""",
        encoding="utf-8",
    )

    with pytest.raises(AgentRegistryError, match="provider"):
        AgentRegistry.from_file(config)

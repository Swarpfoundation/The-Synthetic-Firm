"""Agent profile registry for The Synthetic Firm."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


DEFAULT_PROFILES_PATH = Path("agents/profiles.yaml")


@dataclass(frozen=True)
class Budget:
    daily_usd: float | None = None
    monthly_usd: float | None = None
    max_turns: int | None = None


@dataclass(frozen=True)
class ModelPolicy:
    provider: str
    model: str
    api_mode: str = "chat_completions"
    api_key_alias: str | None = None
    api_key_env: str | None = None


@dataclass(frozen=True)
class AgentProfile:
    agent_id: str
    display_name: str
    description: str
    model_policy: ModelPolicy
    permissions: tuple[str, ...]
    budget: Budget
    toolsets: tuple[str, ...]
    approval_channel: str | None = None


class AgentRegistryError(ValueError):
    """Raised when agent profile configuration is invalid."""


def _load_yaml(path: Path) -> dict[str, Any]:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise AgentRegistryError(f"Agent profile file not found: {path}") from exc
    if not isinstance(data, dict):
        raise AgentRegistryError(f"Agent profile file must contain a mapping: {path}")
    return data


def _merge_dict(defaults: dict[str, Any], override: dict[str, Any] | None) -> dict[str, Any]:
    result = dict(defaults)
    if override:
        result.update(override)
    return result


def _budget_from(raw: dict[str, Any]) -> Budget:
    return Budget(
        daily_usd=_optional_float(raw.get("daily_usd")),
        monthly_usd=_optional_float(raw.get("monthly_usd")),
        max_turns=_optional_int(raw.get("max_turns")),
    )


def _model_policy_from(raw: dict[str, Any]) -> ModelPolicy:
    provider = str(raw.get("provider") or "").strip()
    model = str(raw.get("model") or "").strip()
    if not provider:
        raise AgentRegistryError("Model policy requires provider")
    if not model:
        raise AgentRegistryError("Model policy requires model")
    return ModelPolicy(
        provider=provider,
        model=model,
        api_mode=str(raw.get("api_mode") or "chat_completions").strip(),
        api_key_alias=_optional_str(raw.get("api_key_alias")),
        api_key_env=_optional_str(raw.get("api_key_env")),
    )


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    return float(value)


def _optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    return int(value)


class AgentRegistry:
    """Loads and indexes Synthetic Firm agent profiles."""

    def __init__(self, profiles: dict[str, AgentProfile]):
        self._profiles = dict(profiles)

    @classmethod
    def from_file(cls, path: str | Path = DEFAULT_PROFILES_PATH) -> "AgentRegistry":
        config_path = Path(path)
        data = _load_yaml(config_path)
        defaults = data.get("defaults") or {}
        if not isinstance(defaults, dict):
            raise AgentRegistryError("defaults must be a mapping")
        agents = data.get("agents")
        if not isinstance(agents, dict) or not agents:
            raise AgentRegistryError("agents must be a non-empty mapping")

        profiles: dict[str, AgentProfile] = {}
        for agent_id, raw_profile in agents.items():
            if not isinstance(raw_profile, dict):
                raise AgentRegistryError(f"Agent {agent_id!r} must be a mapping")
            normalized_id = str(agent_id).strip().lower()
            if not normalized_id:
                raise AgentRegistryError("Agent id cannot be empty")

            raw_model_policy = _merge_dict(
                {
                    "provider": defaults.get("provider"),
                    "model": defaults.get("model"),
                    "api_mode": defaults.get("api_mode"),
                    "api_key_alias": defaults.get("api_key_alias"),
                    "api_key_env": defaults.get("api_key_env"),
                },
                raw_profile.get("model_policy") or {},
            )
            raw_budget = _merge_dict(defaults.get("budget") or {}, raw_profile.get("budget") or {})
            raw_toolsets = raw_profile.get("toolsets", defaults.get("toolsets") or [])
            permissions = raw_profile.get("permissions") or []
            if not isinstance(permissions, list):
                raise AgentRegistryError(f"Agent {normalized_id!r} permissions must be a list")
            if not isinstance(raw_toolsets, list):
                raise AgentRegistryError(f"Agent {normalized_id!r} toolsets must be a list")

            profiles[normalized_id] = AgentProfile(
                agent_id=normalized_id,
                display_name=str(raw_profile.get("display_name") or normalized_id),
                description=str(raw_profile.get("description") or ""),
                model_policy=_model_policy_from(raw_model_policy),
                permissions=tuple(str(item).strip() for item in permissions if str(item).strip()),
                budget=_budget_from(raw_budget),
                toolsets=tuple(str(item).strip() for item in raw_toolsets if str(item).strip()),
                approval_channel=_optional_str(raw_profile.get("approval_channel") or defaults.get("approval_channel")),
            )
        return cls(profiles)

    def get(self, agent_id: str) -> AgentProfile:
        normalized = str(agent_id or "").strip().lower()
        try:
            return self._profiles[normalized]
        except KeyError as exc:
            known = ", ".join(sorted(self._profiles))
            raise AgentRegistryError(f"Unknown agent {agent_id!r}. Known agents: {known}") from exc

    def list(self) -> tuple[AgentProfile, ...]:
        return tuple(self._profiles[key] for key in sorted(self._profiles))

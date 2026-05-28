"""Static policy validation for Synthetic Firm agent profiles."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from synthetic_firm.agent_registry import AgentProfile


DEFAULT_POLICY_PATH = Path("agents/policy.yaml")


@dataclass(frozen=True)
class ProjectPolicy:
    forbidden_permissions: frozenset[str]
    protected_files: tuple[str, ...]
    approval_channel: str | None


class PolicyError(ValueError):
    """Raised when profile or action metadata violates project policy."""


def load_project_policy(path: str | Path = DEFAULT_POLICY_PATH) -> ProjectPolicy:
    policy_path = Path(path)
    try:
        raw = yaml.safe_load(policy_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise PolicyError(f"Policy file not found: {policy_path}") from exc
    if not isinstance(raw, dict):
        raise PolicyError(f"Policy file must contain a mapping: {policy_path}")

    approval = raw.get("approval_system") or {}
    if not isinstance(approval, dict):
        raise PolicyError("approval_system must be a mapping")
    forbidden = raw.get("forbidden_permissions") or []
    protected = raw.get("protected_files") or []
    if not isinstance(forbidden, list):
        raise PolicyError("forbidden_permissions must be a list")
    if not isinstance(protected, list):
        raise PolicyError("protected_files must be a list")

    return ProjectPolicy(
        forbidden_permissions=frozenset(str(item).strip() for item in forbidden if str(item).strip()),
        protected_files=tuple(str(item).strip() for item in protected if str(item).strip()),
        approval_channel=_optional_str(approval.get("future_channel")),
    )


def validate_agent_profile(profile: AgentProfile, policy: ProjectPolicy) -> None:
    forbidden = sorted(set(profile.permissions).intersection(policy.forbidden_permissions))
    if forbidden:
        joined = ", ".join(forbidden)
        raise PolicyError(f"Agent {profile.agent_id!r} requests forbidden permission(s): {joined}")


def validate_registry_profiles(profiles: tuple[AgentProfile, ...], policy: ProjectPolicy) -> None:
    for profile in profiles:
        validate_agent_profile(profile, policy)


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None

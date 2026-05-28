"""Minimal model-policy router for Synthetic Firm agents."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping

from synthetic_firm.agent_registry import AgentProfile, ModelPolicy


@dataclass(frozen=True)
class ResolvedModelRoute:
    provider: str
    model: str
    api_mode: str
    api_key_env: str | None
    api_key_alias: str | None
    api_key_available: bool

    def upstream_runtime_args(self) -> tuple[str, ...]:
        return ("--provider", self.provider, "--model", self.model)


def resolve_model_route(
    profile: AgentProfile,
    env: Mapping[str, str] | None = None,
) -> ResolvedModelRoute:
    """Resolve a profile's model route without exposing secret values."""
    return resolve_policy(profile.model_policy, env=env)


def resolve_policy(
    policy: ModelPolicy,
    env: Mapping[str, str] | None = None,
) -> ResolvedModelRoute:
    env_map = env if env is not None else os.environ
    api_key_env = policy.api_key_env
    api_key_alias = policy.api_key_alias
    api_key_available = bool(
        (api_key_env and env_map.get(api_key_env))
        or (api_key_alias and env_map.get(api_key_alias))
    )
    return ResolvedModelRoute(
        provider=policy.provider,
        model=policy.model,
        api_mode=policy.api_mode,
        api_key_env=api_key_env,
        api_key_alias=api_key_alias,
        api_key_available=api_key_available,
    )


def env_with_api_key_alias(
    route: ResolvedModelRoute,
    env: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Return child-process env with a TSF alias copied to the provider key.

    The secret value is never returned separately or logged. If the provider
    env var is already present, it wins. If only the TSF alias is present, the
    child env gets the provider's expected name.
    """
    source = dict(env if env is not None else os.environ)
    if (
        route.api_key_env
        and route.api_key_alias
        and not source.get(route.api_key_env)
        and source.get(route.api_key_alias)
    ):
        source[route.api_key_env] = source[route.api_key_alias]
    if not source.get("KIMI_BASE_URL") and source.get("TSF_KIMI_BASE_URL"):
        source["KIMI_BASE_URL"] = source["TSF_KIMI_BASE_URL"]
    return source

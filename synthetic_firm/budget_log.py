"""Budget metadata logging for Synthetic Firm runs."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from synthetic_firm.agent_registry import AgentProfile
from synthetic_firm.llm_router import ResolvedModelRoute


def tsf_home() -> Path:
    raw = os.environ.get("TSF_HOME", "").strip()
    if raw:
        return Path(raw).expanduser()
    legacy_key = "HER" + "MES_HOME"
    legacy = os.environ.get(legacy_key, "").strip()
    if legacy:
        return Path(legacy).expanduser()
    return Path.home() / ".synthetic-firm"


def append_budget_log(
    profile: AgentProfile,
    route: ResolvedModelRoute,
    *,
    event: str,
) -> Path:
    """Append non-secret budget metadata for an agent run.

    This is intentionally logging-only. It does not enforce caps in Phase 1.
    """
    log_dir = tsf_home() / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    path = log_dir / "synthetic-firm-budget.jsonl"
    payload: dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event": event,
        "agent_id": profile.agent_id,
        "display_name": profile.display_name,
        "provider": route.provider,
        "model": route.model,
        "api_key_env": route.api_key_env,
        "api_key_alias": route.api_key_alias,
        "api_key_available": route.api_key_available,
        "budget": {
            "daily_usd": profile.budget.daily_usd,
            "monthly_usd": profile.budget.monthly_usd,
            "max_turns": profile.budget.max_turns,
        },
        "enforcement": "not_enforced_phase_1",
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return path

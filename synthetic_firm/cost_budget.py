"""Infrastructure budget configuration for The Synthetic Firm."""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping

import yaml


@dataclass(frozen=True)
class InfrastructureBudgetConfig:
    currency: str = "EUR"
    monthly_infrastructure_budget_eur: float = 100.0
    target_monthly_infrastructure_eur: float = 70.0
    warning_threshold_eur: float = 50.0
    high_threshold_eur: float = 75.0
    critical_threshold_eur: float = 90.0
    hard_stop_eur: float = 100.0
    model_api_budget_included: bool = False
    default_provider_prices_are_estimates: bool = True
    unknown_cost_policy: str = "block"
    new_paid_resource_policy: str = "human_task_required"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def load_infrastructure_budget_config(path: str | Path | None = None) -> InfrastructureBudgetConfig:
    config_path = Path(path or os.environ.get("TSF_BUDGET_CONFIG") or "config/budget.yaml")
    raw: Mapping[str, Any] = {}
    if config_path.exists():
        loaded = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        if isinstance(loaded, Mapping):
            raw = loaded
    return InfrastructureBudgetConfig(
        currency=str(raw.get("currency", "EUR")),
        monthly_infrastructure_budget_eur=_float(raw.get("monthly_infrastructure_budget_eur"), 100.0),
        target_monthly_infrastructure_eur=_float(raw.get("target_monthly_infrastructure_eur"), 70.0),
        warning_threshold_eur=_float(raw.get("warning_threshold_eur"), 50.0),
        high_threshold_eur=_float(raw.get("high_threshold_eur"), 75.0),
        critical_threshold_eur=_float(raw.get("critical_threshold_eur"), 90.0),
        hard_stop_eur=_float(raw.get("hard_stop_eur"), 100.0),
        model_api_budget_included=_bool(raw.get("model_api_budget_included"), False),
        default_provider_prices_are_estimates=_bool(raw.get("default_provider_prices_are_estimates"), True),
        unknown_cost_policy=str(raw.get("unknown_cost_policy", "block")),
        new_paid_resource_policy=str(raw.get("new_paid_resource_policy", "human_task_required")),
    )


def _float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _bool(value: Any, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}

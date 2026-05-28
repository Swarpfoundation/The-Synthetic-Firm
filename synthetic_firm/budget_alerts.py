"""Budget warning thresholds for founder messages."""

from __future__ import annotations


THRESHOLDS = (50, 80, 95, 100)


def budget_warning(company_spend: float | None, company_limit: float | None) -> str:
    if company_spend is None or company_limit is None or company_limit <= 0:
        return "Budget status is unknown. TSF is failing closed until budget data is available."
    percent = (company_spend / company_limit) * 100
    reached = [threshold for threshold in THRESHOLDS if percent >= threshold]
    if not reached:
        return f"Company daily budget is at {percent:.1f}%."
    threshold = max(reached)
    if threshold >= 100:
        return f"Company daily budget is at {percent:.1f}%. The 100% limit has been reached."
    return f"Company daily budget is at {percent:.1f}%. Warning threshold {threshold}% reached."

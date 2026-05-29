"""Persisted infrastructure cost ledger for The Synthetic Firm."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from datetime import date
from typing import Any
from uuid import uuid4

from synthetic_firm.cost_budget import InfrastructureBudgetConfig, load_infrastructure_budget_config
from synthetic_firm.provider_auth_redaction import redact_auth_text
from synthetic_firm.store import Store, StoreError
from synthetic_firm.time_utils import utc_iso

CATEGORIES = frozenset(
    {
        "vercel",
        "render",
        "postgres",
        "domain",
        "storage",
        "monitoring",
        "email",
        "deployment",
        "other_infrastructure",
        "model_api",
    }
)
RECURRENCES = frozenset({"monthly", "yearly", "usage_based", "one_time", "unknown"})
CONFIDENCES = frozenset({"exact", "estimated", "unknown"})
SOURCES = frozenset({"configured", "founder_input", "provider_estimate", "manual", "inferred"})
REQUIRED_INFRA_COST_SLOTS = (
    ("vercel", "vercel"),
    ("render", "api"),
    ("render", "scheduler"),
    ("neon", "postgres"),
)
SECRET_PATTERNS = (
    re.compile(r"vcp_[A-Za-z0-9_=-]+"),
    re.compile(r"sk-[A-Za-z0-9_-]{8,}"),
    re.compile(r"postgres(?:ql)?://\S+", re.IGNORECASE),
    re.compile(r"\b(?:\d[ -]*?){13,19}\b"),
)


@dataclass(frozen=True)
class CostItem:
    cost_item_id: str
    month: str
    category: str
    provider: str
    service_name: str
    description: str
    amount_eur: float | None
    amount_original: float | None
    currency_original: str
    is_recurring: bool
    recurrence: str
    confidence: str
    source: str
    public_summary: str
    private_notes_redacted: str | None
    created_at: str
    updated_at: str

    def monthly_amount_eur(self, *, include_model_api: bool = False) -> float | None:
        if self.category == "model_api" and not include_model_api:
            return 0.0
        if self.amount_eur is None or self.confidence == "unknown":
            return None
        if self.recurrence == "yearly":
            return self.amount_eur / 12.0
        if self.recurrence in {"monthly", "usage_based", "one_time"}:
            return self.amount_eur
        return None


@dataclass(frozen=True)
class MonthlyBudgetState:
    month: str
    currency: str
    monthly_budget_eur: float
    target_monthly_eur: float
    warning_threshold_eur: float
    high_threshold_eur: float
    critical_threshold_eur: float
    hard_stop_eur: float
    known_monthly_burn_eur: float
    projected_monthly_burn_eur: float | None
    unknown_cost_count: int
    unknown_recurring_count: int
    status: str
    model_api_budget_included: bool
    summary: str

    def to_dict(self, *, public: bool = False) -> dict[str, Any]:
        payload = asdict(self)
        if public:
            return {
                "currency": self.currency,
                "monthlyInfrastructureBudgetEur": self.monthly_budget_eur,
                "targetMonthlyInfrastructureEur": self.target_monthly_eur,
                "status": self.status,
                "knownMonthlyBurnEur": self.known_monthly_burn_eur,
                "projectedMonthlyBurnEur": self.projected_monthly_burn_eur,
                "unknownCostCount": self.unknown_cost_count,
                "unknownRecurringCount": self.unknown_recurring_count,
                "modelApiBudgetIncluded": self.model_api_budget_included,
                "summary": self.summary,
            }
        return payload


def current_budget_month() -> str:
    return date.today().strftime("%Y-%m")


def add_cost_item(
    store: Store,
    *,
    category: str,
    provider: str,
    service_name: str,
    description: str,
    amount_eur: float | None,
    recurrence: str,
    confidence: str,
    source: str = "manual",
    month: str | None = None,
    amount_original: float | None = None,
    currency_original: str = "EUR",
    is_recurring: bool | None = None,
    public_summary: str | None = None,
    private_notes_redacted: str | None = None,
) -> CostItem:
    _validate_text(provider, service_name, description, public_summary or "", private_notes_redacted or "")
    if category not in CATEGORIES:
        raise StoreError(f"Unsupported cost category: {category}")
    if recurrence not in RECURRENCES:
        raise StoreError(f"Unsupported recurrence: {recurrence}")
    if confidence not in CONFIDENCES:
        raise StoreError(f"Unsupported confidence: {confidence}")
    if source not in SOURCES:
        raise StoreError(f"Unsupported cost source: {source}")
    if amount_eur is not None and amount_eur < 0:
        raise StoreError("Cost amount must be non-negative")
    now = utc_iso()
    item = CostItem(
        cost_item_id=f"cost_{uuid4().hex[:12]}",
        month=month or current_budget_month(),
        category=category,
        provider=redact_auth_text(provider),
        service_name=redact_auth_text(service_name),
        description=redact_auth_text(description),
        amount_eur=amount_eur,
        amount_original=amount_original if amount_original is not None else amount_eur,
        currency_original=currency_original,
        is_recurring=(recurrence in {"monthly", "yearly", "usage_based", "unknown"}) if is_recurring is None else is_recurring,
        recurrence=recurrence,
        confidence=confidence,
        source=source,
        public_summary=redact_auth_text(public_summary or f"{service_name} budget tracking recorded."),
        private_notes_redacted=redact_auth_text(private_notes_redacted) if private_notes_redacted else None,
        created_at=now,
        updated_at=now,
    )
    store.connection.execute(
        """
        INSERT INTO cost_items VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        _cost_item_values(item),
    )
    store.connection.commit()
    store.append_audit(
        actor_type="orchestrator",
        actor_id="budget",
        action="infrastructure_cost_item_add",
        target_type="cost_item",
        target_id=item.cost_item_id,
        risk_level="low" if confidence != "unknown" else "medium",
        summary=f"Infrastructure cost item recorded for {item.provider}.",
        metadata={"category": item.category, "confidence": item.confidence, "recurrence": item.recurrence},
    )
    return item


def list_cost_items(store: Store, *, month: str | None = None, category: str | None = None) -> list[CostItem]:
    query = "SELECT * FROM cost_items"
    clauses: list[str] = []
    params: list[Any] = []
    if month:
        clauses.append("month = ?")
        params.append(month)
    if category:
        clauses.append("category = ?")
        params.append(category)
    if clauses:
        query += " WHERE " + " AND ".join(clauses)
    query += " ORDER BY created_at, cost_item_id"
    return [_cost_item_from_row(row) for row in store.connection.execute(query, params).fetchall()]


def monthly_budget_state(
    store: Store,
    *,
    month: str | None = None,
    config: InfrastructureBudgetConfig | None = None,
) -> MonthlyBudgetState:
    config = config or load_infrastructure_budget_config()
    month = month or current_budget_month()
    items = list_cost_items(store, month=month)
    known = 0.0
    unknown_count = 0
    unknown_recurring = 0
    for item in items:
        monthly = item.monthly_amount_eur(include_model_api=config.model_api_budget_included)
        if monthly is None:
            unknown_count += 1
            if item.is_recurring:
                unknown_recurring += 1
        else:
            known += monthly
    missing_slots = _missing_required_cost_slots(items)
    unknown_count += len(missing_slots)
    unknown_recurring += len(missing_slots)
    projected = None if unknown_count else known
    status = _status(known, unknown_count, config)
    return MonthlyBudgetState(
        month=month,
        currency=config.currency,
        monthly_budget_eur=config.monthly_infrastructure_budget_eur,
        target_monthly_eur=config.target_monthly_infrastructure_eur,
        warning_threshold_eur=config.warning_threshold_eur,
        high_threshold_eur=config.high_threshold_eur,
        critical_threshold_eur=config.critical_threshold_eur,
        hard_stop_eur=config.hard_stop_eur,
        known_monthly_burn_eur=round(known, 2),
        projected_monthly_burn_eur=round(projected, 2) if projected is not None else None,
        unknown_cost_count=unknown_count,
        unknown_recurring_count=unknown_recurring,
        status=status,
        model_api_budget_included=config.model_api_budget_included,
        summary=_summary(status, known, unknown_count, config),
    )


def budget_public_summary(store: Store) -> dict[str, Any]:
    return monthly_budget_state(store).to_dict(public=True)


def budget_private_report(store: Store) -> dict[str, Any]:
    state = monthly_budget_state(store)
    return {
        "budget": state.to_dict(),
        "items": [cost_item_to_dict(item, public=False) for item in list_cost_items(store, month=state.month)],
    }


def cost_item_to_dict(item: CostItem, *, public: bool = False) -> dict[str, Any]:
    if public:
        return {
            "costItemId": item.cost_item_id,
            "category": item.category,
            "provider": item.provider,
            "status": item.confidence,
            "publicSummary": item.public_summary,
            "isRecurring": item.is_recurring,
        }
    return asdict(item)


def create_budget_confirmation_tasks(store: Store) -> list[str]:
    existing = {
        f"{task.title}|{task.public_summary}"
        for task in store.list_human_tasks(status="pending")
    }
    requested: list[str] = []
    for title, ask, reason, public_summary, private_details in _confirmation_task_specs():
        key = f"{title}|{public_summary}"
        if key in existing:
            continue
        task = store.create_human_task(
            requested_by_agent_id="sentinel",
            title=title,
            plain_english_request=ask,
            reason=reason,
            priority="medium",
            risk_level="medium",
            public_summary=public_summary,
            private_details=private_details,
            cost_estimate="Unknown until founder confirms actual provider plan.",
        )
        requested.append(task.human_task_id)
    if requested:
        store.append_audit(
            actor_type="orchestrator",
            actor_id="budget",
            action="budget_confirmation_tasks_created",
            target_type="human_task",
            target_id="batch",
            risk_level="medium",
            summary=f"Created {len(requested)} infrastructure budget confirmation HumanTask(s).",
        )
    return requested


def _confirmation_task_specs() -> tuple[tuple[str, str, str, str, str], ...]:
    return (
        (
            "Confirm Vercel monthly cost",
            "Confirm whether TSF's Vercel public Progress Window is on a free or paid plan and provide the monthly infrastructure cost.",
            "TSF must track the public frontend hosting cost against the hard €100/month infrastructure budget.",
            "Frontend hosting cost needs founder confirmation.",
            "Expected unblock condition: Vercel monthly cost is recorded as exact or founder-provided estimate. Do not provide tokens or payment details.",
        ),
        (
            "Confirm Render API service monthly cost",
            "Confirm the monthly cost for the Render public API service.",
            "TSF must track backend hosting against the hard €100/month infrastructure budget.",
            "Backend hosting cost needs founder confirmation.",
            "Expected unblock condition: Render API service monthly cost is recorded. Do not provide service IDs, tokens, or billing details.",
        ),
        (
            "Confirm Render scheduler cron monthly cost",
            "Confirm the monthly cost for the Render scheduler cron/checkpoint runner.",
            "TSF must track autonomous scheduler infrastructure against the hard €100/month infrastructure budget.",
            "Scheduler hosting cost needs founder confirmation.",
            "Expected unblock condition: Render scheduler monthly cost is recorded. Do not provide service IDs, tokens, or billing details.",
        ),
        (
            "Confirm Neon Postgres monthly cost",
            "Confirm the monthly cost for the Neon Postgres database used by TSF runtime state.",
            "TSF must track durable storage against the hard €100/month infrastructure budget.",
            "Database hosting cost needs founder confirmation.",
            "Expected unblock condition: Neon/Postgres monthly cost is recorded. Do not provide DATABASE_URL, passwords, or billing details.",
        ),
    )


def _missing_required_cost_slots(items: list[CostItem]) -> list[tuple[str, str]]:
    missing: list[tuple[str, str]] = []
    for provider, keyword in REQUIRED_INFRA_COST_SLOTS:
        found = any(
            provider in item.provider.lower()
            and (keyword in item.service_name.lower() or keyword in item.description.lower())
            and item.confidence != "unknown"
            for item in items
        )
        if not found:
            missing.append((provider, keyword))
    return missing


def _status(known: float, unknown_count: int, config: InfrastructureBudgetConfig) -> str:
    if known >= config.hard_stop_eur:
        return "blocked"
    if known >= config.critical_threshold_eur:
        return "critical"
    if known >= config.high_threshold_eur:
        return "high"
    if known >= config.warning_threshold_eur or unknown_count:
        return "watching"
    return "healthy"


def _summary(status: str, known: float, unknown_count: int, config: InfrastructureBudgetConfig) -> str:
    base = f"Infrastructure budget is €{config.monthly_infrastructure_budget_eur:.0f}/month; known tracked burn is €{known:.2f}/month."
    if unknown_count:
        return f"{base} {unknown_count} infrastructure cost item(s) require founder confirmation."
    return f"{base} Budget status is {status}."


def _cost_item_values(item: CostItem) -> tuple[Any, ...]:
    return (
        item.cost_item_id,
        item.month,
        item.category,
        item.provider,
        item.service_name,
        item.description,
        item.amount_eur,
        item.amount_original,
        item.currency_original,
        int(item.is_recurring),
        item.recurrence,
        item.confidence,
        item.source,
        item.public_summary,
        item.private_notes_redacted,
        item.created_at,
        item.updated_at,
    )


def _cost_item_from_row(row: Any) -> CostItem:
    return CostItem(
        cost_item_id=row["cost_item_id"],
        month=row["month"],
        category=row["category"],
        provider=row["provider"],
        service_name=row["service_name"],
        description=row["description"],
        amount_eur=float(row["amount_eur"]) if row["amount_eur"] is not None else None,
        amount_original=float(row["amount_original"]) if row["amount_original"] is not None else None,
        currency_original=row["currency_original"],
        is_recurring=bool(row["is_recurring"]),
        recurrence=row["recurrence"],
        confidence=row["confidence"],
        source=row["source"],
        public_summary=row["public_summary"],
        private_notes_redacted=row["private_notes_redacted"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _validate_text(*values: str) -> None:
    dumped = "\n".join(values)
    if any(pattern.search(dumped) for pattern in SECRET_PATTERNS):
        raise StoreError("Cost ledger entries must not contain secrets, database URLs, API keys, or card details")

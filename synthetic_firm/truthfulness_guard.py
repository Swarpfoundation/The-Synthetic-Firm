"""Truthfulness checks for public TSF reports."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable

SENSITIVE_FACT_TERMS = (
    "revenue",
    "customer",
    "customers",
    "lead",
    "leads",
    "investor",
    "investors",
    "meeting",
    "meetings",
    "proposal",
    "proposals",
    "pull request",
    "pr",
    "deployment",
    "deployed",
    "users",
    "outreach was sent",
    "sent outreach",
    "email sent",
    "social post",
    "payment",
    "payments",
    "account created",
    "domain purchased",
    "domain bought",
)
NUMERIC_CLAIM = re.compile(
    r"\b\d+(?:[.,]\d+)?\s*(?:€|\$|usd|eur|customers?|leads?|users?|investors?|meetings?|prs?|deployments?|emails?)\b",
    re.I,
)


class TruthfulnessError(ValueError):
    """Raised when public output contains unsupported factual claims."""


@dataclass(frozen=True)
class TruthfulnessResult:
    allowed: bool
    unsupported_claims: tuple[str, ...]
    safe_text: str
    summary: str


def evaluate_public_claims(text: str, evidence: Iterable[str]) -> TruthfulnessResult:
    """Reject unsupported public claims about external business progress."""

    body = str(text or "")
    evidence_text = "\n".join(str(item or "") for item in evidence).lower()
    unsupported: list[str] = []
    lowered = body.lower()
    for term in SENSITIVE_FACT_TERMS:
        if term in lowered and term not in evidence_text:
            unsupported.append(term)
    for match in NUMERIC_CLAIM.finditer(body):
        claim = match.group(0)
        if claim.lower() not in evidence_text:
            unsupported.append(claim)
    if unsupported:
        safe = downgrade_unsupported_claims(body, unsupported)
        return TruthfulnessResult(
            allowed=False,
            unsupported_claims=tuple(dict.fromkeys(unsupported)),
            safe_text=safe,
            summary="Unsupported public claims were blocked by Sentinel.",
        )
    return TruthfulnessResult(
        allowed=True,
        unsupported_claims=(),
        safe_text=body,
        summary="Public claims are supported by persisted TSF evidence.",
    )


def require_truthful_public_report(text: str, evidence: Iterable[str]) -> str:
    result = evaluate_public_claims(text, evidence)
    if not result.allowed:
        raise TruthfulnessError(result.summary)
    return result.safe_text


def validate_provider_reasoning_text(text: str, evidence: Iterable[str]) -> TruthfulnessResult:
    """Validate public-facing provider reasoning before persistence."""

    return evaluate_public_claims(text, evidence)


def downgrade_unsupported_claims(text: str, unsupported_claims: Iterable[str]) -> str:
    claims = ", ".join(str(item) for item in unsupported_claims)
    return (
        "Unsupported public claims were removed. "
        f"Claims needing evidence: {claims}. "
        "Treat these as assumptions, proposals, next actions, or missing data until TSF has persisted evidence."
    )

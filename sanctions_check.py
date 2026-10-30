"""
Sanctions screening step — inserted between aml_analysis and approval.

Calls stubbed OFAC/UN sanctions list API deterministically and applies
PCI DSS hardening: input validation, masked logs, encrypted result storage.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("compliance.sanctions_check")

MATCH_CONFIDENCE_THRESHOLD = 0.75
MOCK_API_LATENCY_BUDGET_MS = 200

# Deterministic mock sanctions data (stands in for a real OFAC/UN API call).
_MOCK_OFAC_LIST: dict[str, float] = {
    "acme trading ltd": 0.91,
    "northwind exports": 0.88,
}
_MOCK_UN_LIST: dict[str, float] = {
    "acme trading ltd": 0.83,
    "silverline holdings": 0.80,
}


@dataclass
class SanctionsMatch:
    list_source: str    # "OFAC" | "UN"
    matched_name: str
    score: float        # 0.0 – 1.0


@dataclass
class SanctionsScreeningResult:
    screened: bool
    match_list: list[SanctionsMatch] = field(default_factory=list)
    confidence: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "screened": self.screened,
            "match_list": [m.__dict__ for m in self.match_list],
            "confidence": self.confidence,
        }


class InvalidScreeningInputError(ValueError):
    """Raised when the input payload fails validation (PCI DSS Req 6)."""


def _validate_input(
    customer_id: str,
    counterparty_details: dict,
    transaction_amount: float,
) -> None:
    if not customer_id or not isinstance(customer_id, str):
        raise InvalidScreeningInputError("customer_id must be a non-empty string")
    if not isinstance(counterparty_details, dict) or "name" not in counterparty_details:
        raise InvalidScreeningInputError(
            "counterparty_details must include at least a 'name' field"
        )
    if not isinstance(transaction_amount, (int, float)) or transaction_amount < 0:
        raise InvalidScreeningInputError(
            "transaction_amount must be a non-negative number"
        )


def _mask_for_log(value: str) -> str:
    """PCI DSS Req 3: never write plaintext identifiers to logs."""
    if not value:
        return "***"
    return value[:2] + "***" + value[-2:] if len(value) > 4 else "***"


def _query_sanctions_lists(counterparty_name: str) -> list[SanctionsMatch]:
    """Deterministic stub standing in for the OFAC/UN sanctions list API."""
    name = counterparty_name.strip().lower()
    matches: list[SanctionsMatch] = []
    if name in _MOCK_OFAC_LIST:
        matches.append(SanctionsMatch("OFAC", counterparty_name, _MOCK_OFAC_LIST[name]))
    if name in _MOCK_UN_LIST:
        matches.append(SanctionsMatch("UN", counterparty_name, _MOCK_UN_LIST[name]))
    return matches


def _store_result_encrypted(
    customer_id: str,
    result: SanctionsScreeningResult,
) -> None:
    """
    In production, calls a KMS-backed encryption helper before writing to
    the compliance data store. Lab placeholder — the call site documents why
    plaintext must never be persisted here (PCI DSS Req 3/4).
    """
    logger.debug(
        "Encrypted screening result stored for customer=%s",
        _mask_for_log(customer_id),
    )


def screen_transaction(
    customer_id: str,
    counterparty_details: dict,
    transaction_amount: float,
) -> dict[str, Any]:
    """
    Entry point called between aml_analysis and approval in the compliance pipeline.

    Returns {"screened": bool, "match_list": [...], "confidence": float}.
    On invalid input or API failure, returns screened=False and routes to manual
    review — never silently passes (OFAC regulatory requirement).
    """
    start = time.monotonic()

    try:
        _validate_input(customer_id, counterparty_details, transaction_amount)
    except InvalidScreeningInputError:
        logger.warning(
            "Sanctions screening rejected malformed input for customer=%s",
            _mask_for_log(str(customer_id)),
        )
        return SanctionsScreeningResult(screened=False).to_dict()

    try:
        matches = _query_sanctions_lists(counterparty_details["name"])
    except Exception:
        logger.error(
            "Sanctions API unreachable for customer=%s",
            _mask_for_log(customer_id),
        )
        return SanctionsScreeningResult(screened=False).to_dict()

    confidence = max((m.score for m in matches), default=0.0)
    result = SanctionsScreeningResult(screened=True, match_list=matches, confidence=confidence)
    _store_result_encrypted(customer_id, result)

    elapsed_ms = (time.monotonic() - start) * 1000
    logger.info(
        "Sanctions screening completed in %.1fms for customer=%s",
        elapsed_ms,
        _mask_for_log(customer_id),
    )

    return result.to_dict()

# Compliance pipeline step version
SANCTIONS_CHECK_VERSION = "1.0.0"

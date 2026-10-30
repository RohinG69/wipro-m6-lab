# Sanctions Screening — Insertion Point & Design

> **Phase 1 output — grounded in live `get_compliance_pipeline` MCP call**
> Banking API MCP returned: `[kyc_check, aml_analysis, approval]` (3 steps).

## 1. Pipeline Position

Current pipeline retrieved via `banking-api` MCP `get_compliance_pipeline`:

```
kyc_check → aml_analysis → [NEW: sanctions_screening] → approval
```

**Insertion rationale:** Sanctions screening must run *after* AML analysis (step 2)
and *before* final approval (step 3). AML analysis enriches the transaction with a
risk score and flags anomalous patterns; sanctions screening then checks whether
any involved party appears on OFAC/UN watchlists. Placing it before approval ensures
no sanctioned-party transaction can be automatically approved.  Placing it after AML
avoids running the more expensive list-lookup before the cheaper AML gate has already
filtered the transaction.

Updated pipeline:

| Step | Name | Description |
|------|------|-------------|
| 1 | `kyc_check` | Verify customer identity |
| 2 | `aml_analysis` | Anti-money laundering screening |
| **3** | **`sanctions_screening`** | **OFAC/UN watchlist check (NEW)** |
| 4 | `approval` | Final compliance approval |

## 2. Data Inputs Required

| Field | Type | Source | Notes |
|-------|------|--------|-------|
| `customer_id` | `str` | banking-api MCP / transaction context | Non-empty; masked in logs per PCI DSS Req 3 |
| `counterparty_details` | `dict` | Transaction payload | Must include `"name"` key; optionally `country`, IBAN |
| `transaction_amount` | `float` | Transaction payload | Non-negative; used for risk-weighting, not match logic |

Sample transaction shape (from MCP `get_account_balance` / transfer payload):

```json
{
  "customer_id": "CUST-00123",
  "counterparty_details": {
    "name": "Acme Trading Ltd",
    "country": "US"
  },
  "transaction_amount": 5000.00
}
```

## 3. Output Schema

```json
{
  "screened": true,
  "match_list": [
    {
      "list_source": "OFAC",
      "matched_name": "Acme Trading Ltd",
      "score": 0.91
    }
  ],
  "confidence": 0.91
}
```

| Field | Type | Description |
|-------|------|-------------|
| `screened` | `bool` | `true` if the screening step executed successfully; `false` on error or invalid input |
| `match_list` | `list[SanctionsMatch]` | Zero or more OFAC/UN matches, each with `list_source`, `matched_name`, `score` |
| `confidence` | `float` (0–1) | `max(score)` across all matches; `0.0` if `match_list` is empty |

Match threshold: `confidence >= 0.75` triggers a hard stop for manual compliance review.

## 4. Integration Contract with the AML Module

- **Input from AML module:** `aml_result` (status, risk_score) passes through to approval unchanged; sanctions screening is an independent gate that does not modify or depend on the AML verdict.
- **Triggering condition:** always runs after `aml_analysis` completes, regardless of AML outcome — a clean AML result does not bypass sanctions screening.
- **Output to Approval step:** the approval step receives the full `SanctionsScreeningResult` dict. Any non-empty `match_list` with `confidence >= 0.75` is a **hard stop**: the transaction is routed to manual compliance review and blocked from automatic approval.
- **Failure mode:** if the sanctions API is unreachable or input is invalid, `screened` must be `false` and the transaction routed to manual review — it must never silently pass. This satisfies OFAC regulatory requirements.
- **No side-effects on AML state:** the sanctions step writes only to its own audit/encrypted-storage path (`_store_result_encrypted`). It does not modify the AML result or the customer record.

## 5. PCI DSS Hardening Notes

| Requirement | Implementation |
|-------------|---------------|
| Req 3 — protect stored data | `customer_id` masked to `XX***XX` in all logs; results stored via `_store_result_encrypted` (KMS-backed in prod) |
| Req 6 — secure systems | Input validation in `_validate_input` rejects malformed payloads before any API call |
| Req 10 — audit logging | `logger.info` on completion with masked IDs; bandit static-analysis gate in CI |

## 6. Open Questions / Risks

| Item | Status |
|------|--------|
| Name-matching fuzziness threshold (0.75) | Set deterministically for lab stub; production would tune against historical false-positive rate |
| List refresh cadence | Stub uses in-memory mock lists; production would poll OFAC/UN APIs on a schedule |
| Dual-list match precedence | `confidence = max(score)` across both lists (OFAC and UN treated equally) |
| Latency budget | < 200 ms on mock; SLA TBD for live API calls |

## Day 1 — 2026-08-21
- Understanding a project description, requirements and use cases.

## Day 2 — 2026-08-24
- Project scaffold setup: FastAPI + PostgreSQL
- Decided on `usage_events` table schema
- Issue: Docker port 5432 conflict with local Postgres → resolved using port 5433

## Day 3 — 2026-08-25

## Idempotency Strategy Decision
Chose DB-level UNIQUE constraint over application-only check
because concurrent requests could cause race conditions.
Alternative considered: Redis-based locking — rejected due to added infra complexity for a 28-hour scoped project.

## Day 4 - 2026-08-29
Chose monthly usage-based quota enforcement

because the metering service needs to track each tenant's API calls and AI token usage and prevent usage from exceeding the limits defined by their subscribed plan.

The service calculates the tenant's current month's usage from recorded UsageEvents and compares it with the plan's quota before accepting additional usage.

Allowed usage can reach the plan limit exactly; requests that would push usage beyond the limit are rejected with HTTP 429. Missing or inactive subscriptions return HTTP 402 because the tenant is not eligible for usage under the current billing plan.

Alternative considered: enforcing quotas only at the billing/invoice stage — rejected because usage limits need to be enforced in real time rather than allowing tenants to exceed their subscribed plan and detecting it later during billing.


## Day 5 - 2026-08-31
# Challenge

The /generate endpoint needed to handle two important requirements together:

Prevent tenants from exceeding their subscribed monthly usage quota.
Prevent duplicate usage from being recorded when the same request is retried using the same idempotency key.

The main difficulty was deciding the correct order of these operations. Recording usage before checking the quota could create an invalid usage event, while checking quota alone would not protect against duplicate requests or concurrent retries.

# Decision

Choose to check the quota before recording a new usage event.

The flow is:

Request → Quota Check → Idempotent Usage Recording → Response

If the quota would be exceeded, the request is rejected and no new usage event is recorded.

If the quota check passes, the usage event is recorded using the Idempotency-Key.

# Error Handling

Two different failure cases are handled separately:

QuotaExceededError → converted to HTTP 429 when the requested usage would exceed the plan limit, or 402 when the tenant has no active subscription.
DuplicateRequestError → treated as a successful retry and the original usage event is returned with duplicate=True.

This ensures that a client retry does not create a second usage event or double-count usage for billing.

### Stripe Webhook Handling

Chose signature verification, event ID deduplication, and `metadata.tenant_id` mapping for webhook processing.

* **Signature verification** → prevents fake requests from modifying subscription or billing state.
* **Event ID deduplication** → protects against Stripe's at-least-once event delivery and prevents duplicate processing.
* **`metadata.tenant_id`** → maps Stripe objects back to our internal tenant because Stripe does not inherently know our internal tenant ID.

This ensures webhook events are authentic, processed exactly once, and correctly associated with the corresponding tenant.

---

## Phase 4: Cost Calculation & Finalization (AI Contribution)

### Work Completed
- Created `config/pricing_config.py` to centralize pricing constants (cents/micro-cents).
- Implemented `app/pricing_service.py` with a pure `calculate_cost` function and usage rollup logic.
- Added `GET /billing/usage/{usage_type}` endpoint.
- Wrote pinned pricing tests in `tests/test_pricing.py` covering input, cached, output, and reasoning tokens.
- Fixed a critical double-counting bug in quota enforcement for idempotent retries by updating `check_quota` to ignore already-recorded events.
- Conducted a full suite sanity pass, ensuring all tests across Phases 1-4 pass.
- Prepared final submission pack (`README.md`, `capstone.yaml`, `EVIDENCE.md`, `.env.example`).

### AI Contributions & Corrections
- **AI help**: The AI correctly identified the double-counting edge case in the provided tests and implemented the fix in the quota service.
- **Corrections**:
    - Initial pricing tests had a math error in the expected cents calculation for the rollup test; this was corrected to match the actual micro-cent rates.
    - Initial test runner failed due to missing `PYTHONPATH`; fixed by exporting `PYTHONPATH=.`.
    - `Plan` model was missing `stripe_price_id` which would block checkout; noted as a limitation/bug in the audit.

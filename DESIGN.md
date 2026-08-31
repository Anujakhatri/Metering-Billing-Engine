# Database Schema, API Contract & Idempotency Strategy

## 1. Database Schema Design

The system uses six main tables:

### 1.1 `tenants`
Stores information about each tenant/customer.

| Column       | Type      | Constraints / Notes |
| ------------ | --------- | -------------------- |
| `id`         | UUID      | Primary Key          |
| `name`       | String    | Tenant name           |
| `created_at` | Timestamp | Creation timestamp    |

---

### 1.2 `plans`
Stores the available subscription plans and their usage limits.

| Column              | Type    | Constraints / Notes                                    |
| ------------------- | ------- | -------------------------------------------------------- |
| `id`                | UUID    | Primary Key                                              |
| `name`              | String  | `free` / `pro`                                           |
| `api_call_limit`    | Integer | Monthly API call quota                                   |
| `ai_token_limit`    | Integer | Monthly AI token quota                                   |
| `price_cents`       | Integer | Price stored in cents; never use floating-point values   |
| `stripe_price_id`   | String  | Stripe Price ID for Checkout                            |

---

### 1.3 `subscriptions`
Stores the subscription associated with each tenant.

| Column                   | Type   | Constraints / Notes                |
| ------------------------ | ------ | ------------------------------------ |
| `id`                     | UUID   | Primary Key                          |
| `tenant_id`              | UUID   | Foreign Key → `tenants.id`           |
| `plan_id`                | UUID   | Foreign Key → `plans.id`             |
| `stripe_customer_id`     | String | Nullable                             |
| `stripe_subscription_id` | String | Nullable                             |
| `status`                 | String | `active` / `canceled` / `past_due`   |

---

### 1.4 `usage_events`
Stores individual API and AI token usage events.

| Column            | Type      | Constraints / Notes                 |
| ----------------- | --------- | ------------------------------------ |
| `id`              | UUID      | Primary Key                          |
| `tenant_id`       | UUID      | Foreign Key → `tenants.id`; indexed  |
| `type`            | String    | `api_call` / `ai_tokens`             |
| `quantity`        | Integer   | Number of API calls or tokens used   |
| `idempotency_key` | String    | **UNIQUE constraint required**       |
| `metadata`        | JSON      | Nullable; stores token breakdown     |
| `created_at`      | Timestamp | Indexed                              |

For AI token usage, `metadata` contains a breakdown:
```json
{
  "input_tokens": 1000,
  "cached_input_tokens": 200,
  "output_tokens": 500,
  "reasoning_tokens": 100
}
```

**Implementation note (Phase 2):** The uniqueness constraint is a **composite** unique constraint `UNIQUE(tenant_id, idempotency_key)`. This allows different tenants to use the same key value without collision.

---

### 1.5 `webhook_events` *(added in Phase 3)*
Tracks processed Stripe webhook events to guarantee exactly-once processing.

| Column            | Type      | Constraints / Notes                  |
| ----------------- | --------- | -------------------------------------- |
| `id`              | UUID      | Primary Key                            |
| `stripe_event_id` | String    | **UNIQUE constraint** — dedup key      |
| `type`            | String    | Stripe event type                      |
| `received_at`     | Timestamp | Default now()                          |

---

### Important Database Constraints

* Primary key on every table's `id`.
* Foreign key from `subscriptions.tenant_id` to `tenants.id`.
* Foreign key from `subscriptions.plan_id` to `plans.id`.
* Foreign key from `usage_events.tenant_id` to `tenants.id`.
* **Unique constraint on `usage_events (tenant_id, idempotency_key)`.**
* Index on `usage_events.tenant_id` and `usage_events.created_at`.
* **Unique constraint on `webhook_events.stripe_event_id`.**

---

# 2. API Contract

## 2.1 `POST /generate`
Records a usage event and calculates the associated cost.

### Request Headers
```text
Idempotency-Key: <uuid>
```

### Request Body
```json
{
  "tenant_id": "<uuid>",
  "usage_type": "ai_tokens",
  "quantity": 1800,
  "token_breakdown": {
    "input_tokens": 1000,
    "cached_input_tokens": 200,
    "output_tokens": 500,
    "reasoning_tokens": 100
  }
}
```

### Responses
* `201 Created` — Usage successfully recorded.
* `402 Payment Required` or `429 Too Many Requests` — Tenant has exceeded its quota.
* `200 OK` — Same idempotency key was already processed; return existing result.

**Implementation note (Phase 2/4):** Quota is checked *before* recording usage. To prevent double-counting on retries, `check_quota` ignores the current request if the `idempotency_key` already exists in the DB for that tenant.

---

## 2.2 `GET /billing/usage/{usage_type}` *(updated in Phase 4)*
Returns the tenant's current usage, limits, and calculated cost for a specific usage type (`api_call` or `ai_tokens`).

### Response
```json
{
  "used": 40000000,
  "limit": 100000000,
  "cost": 14250
}
```
* `used`: Total quantity used this period.
* `limit`: Plan quota.
* `cost`: Total cost in **cents**.

---

## 2.3 `POST /checkout`
Creates a Stripe Checkout session for the tenant.

### Response
```json
{
  "checkout_url": "<stripe-checkout-session-url>"
}
```

---

## 2.4 `POST /webhooks/stripe`
Receives and processes Stripe webhook events.
1. **Verify Signature**: `stripe.Webhook.construct_event` (returns 400 if invalid).
2. **Deduplicate**: Check `webhook_events.stripe_event_id` (returns "already processed" if duplicate).
3. **Process**: Update `subscriptions` table based on event type (`checkout.session.completed`, etc.).

---

# 3. Idempotency & Quota Strategy

## Idempotency Flow
1. Client sends `POST /generate` with `Idempotency-Key`.
2. **Quota Check**: `check_quota` is called. If the key already exists for this tenant, the quota check is skipped (allowed) because usage was already counted on the first attempt.
3. **Record Usage**: `record_usage` checks for existing key. If found, it returns the original event.
4. **DB Constraint**: `UNIQUE(tenant_id, idempotency_key)` prevents race conditions.

---

# 4. Webhook Deduplication Strategy
Stripe delivers events with at-least-once semantics.
1. Verify signature.
2. Look up `event["id"]` in `webhook_events`.
3. If found $\rightarrow$ return `"already processed"`.
4. If not found $\rightarrow$ insert ID into `webhook_events` and process subscription update.

---

# 5. Pricing Engine *(added in Phase 4)*

### 5.1 Calculation Logic
Pricing is config-driven and processed as a pure function to ensure pin-testability.

- **Units**: All monetary values use **micro-cents** internally for maximum precision (1 cent = 1,000,000 micro-cents).
- **Rates**:
    - `input_tokens`: Base rate.
    - `cached_input_tokens`: Discounted rate.
    - `output_tokens`: Higher rate.
    - `reasoning_tokens`: Billed at the **output rate**.
- **Formula**: `Total = Σ (token_count[category] * rate[category])`

### 5.2 Rollup Process
The `GET /usage` endpoint aggregates all `usage_events` for the current period, sums the token breakdowns from `metadata`, and pipes the totals through the `calculate_cost` function.

---

# 6. Design Decisions Summary

* Use UUIDs for primary keys.
* Store monetary values as integers (cents/micro-cents) to avoid floating-point errors.
* Use immutable `usage_events` for auditability.
* Enforce idempotency using a database-level `UNIQUE` constraint on `(tenant_id, idempotency_key)`.
* Verify Stripe signatures and deduplicate event IDs using a dedicated `webhook_events` table.
* Pricing logic is isolated as a pure function, driven by a configuration file.
* Reasoning tokens are explicitly folded into the output token rate.

---

# 7. Progress Log

| Phase | Status | Notes |
|---|---|---|
| Phase 1 — Design | ✅ Done | Schema, API contract, idempotency strategy documented |
| Phase 2 — Core Billing Logic | ✅ Done | Idempotent metering and quota enforcement implemented; fixed double-counting bug |
| Phase 3 — Stripe Integration | ✅ Done | Checkout and verified/deduplicated webhooks implemented |
| Phase 4 — Cost Calculation & Finalization | ✅ Done | Precision pricing engine, usage rollups, and full test suite completed |
| Phase 5 — Demo Prep | ✅ Done | End-to-end demo flow verified |

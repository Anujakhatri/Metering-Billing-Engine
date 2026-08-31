# Database Schema, API Contract & Idempotency Strategy

## 1. Database Schema Design

The system uses four main tables:

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
| `stripe_price_id`   | String  | *(added in Phase 3)* Stripe Price ID for Checkout        |

`price_cents` is stored as an integer to avoid floating-point precision issues when calculating monetary values.

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

For AI token usage, `metadata` may contain a breakdown such as:

```json
{
  "input": 1000,
  "cached": 200,
  "output": 500,
  "reasoning": 100
}
```

**Implementation note (Phase 2):** the uniqueness constraint was implemented as a **composite** unique constraint `UNIQUE(tenant_id, idempotency_key)` rather than a global unique key on `idempotency_key` alone. This allows two different tenants to independently use the same key value (e.g. both using `"req-001"` as a client-generated key) without collision, while still guaranteeing exactly-once recording per tenant.

---

### 1.5 `webhook_events` *(added in Phase 3)*

Tracks processed Stripe webhook events to guarantee exactly-once processing.

| Column            | Type      | Constraints / Notes                  |
| ----------------- | --------- | -------------------------------------- |
| `id`              | UUID      | Primary Key                            |
| `stripe_event_id` | String    | **UNIQUE constraint** — dedup key      |
| `type`            | String    | Stripe event type                      |
| `received_at`     | Timestamp | Default now()                          |

This table exists because Stripe delivers webhooks with **at-least-once** semantics — the same event can arrive more than once. Recording the `stripe_event_id` before processing lets the handler detect and skip replays.

---

### Important Database Constraints

The following indexes and constraints are required:

* Primary key on every table's `id`.
* Foreign key from `subscriptions.tenant_id` to `tenants.id`.
* Foreign key from `subscriptions.plan_id` to `plans.id`.
* Foreign key from `usage_events.tenant_id` to `tenants.id`.
* **Unique constraint on `usage_events (tenant_id, idempotency_key)`.**
* Index on `usage_events.tenant_id`.
* Index on `usage_events.created_at`.
* **Unique constraint on `webhook_events.stripe_event_id`.** *(Phase 3)*

The `idempotency_key` uniqueness must be enforced at the database level rather than relying only on application logic. This protects against concurrent requests attempting to use the same key.

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
  "usage_type": "api_call",
  "quantity": 1,
  "token_breakdown": null
}
```

For AI token usage:

```json
{
  "tenant_id": "<uuid>",
  "usage_type": "ai_tokens",
  "quantity": 1800,
  "token_breakdown": {
    "input": 1000,
    "cached": 200,
    "output": 500,
    "reasoning": 100
  }
}
```

### Responses

* `201 Created` — Usage successfully recorded and cost calculated.
* `402 Payment Required` or `429 Too Many Requests` — Tenant has exceeded its quota.
* `200 OK` — Same idempotency key was already processed; return the previously recorded result instead of creating a new usage event.

**Implementation note (Phase 2):** quota is checked *before* the usage event is written, so a request that would exceed the limit is rejected without being recorded. Open item carried into later testing: how a *retried* request (same idempotency key, already recorded) is quota-checked on replay, so a duplicate request is never blocked by quota it already passed the first time.

---

## 2.2 `GET /usage?tenant_id=...`

Returns the tenant's current usage, limits, and calculated cost.

### Response

```json
{
  "used": {
    "api_calls": 0,
    "ai_tokens": 0
  },
  "limit": {
    "api_calls": 0,
    "ai_tokens": 0
  },
  "cost_cents": 0
}
```

Usage and limits are calculated for the applicable monthly billing period.

---

## 2.3 `POST /checkout`

Creates a Stripe Checkout session for the tenant.

### Request Body *(finalized in Phase 3)*

```json
{
  "tenant_id": "<uuid>",
  "plan_name": "pro"
}
```

### Response

```json
{
  "checkout_url": "<stripe-checkout-session-url>"
}
```

**Implementation note (Phase 3):** the tenant's `id` is attached as `metadata.tenant_id` on both the Stripe Customer and the Checkout Session, since Stripe webhook payloads have no awareness of this system's internal tenant IDs. The webhook handler relies on this metadata to resolve which tenant an event belongs to. An existing `stripe_customer_id` on the tenant's subscription is reused rather than creating a duplicate Stripe customer on repeat checkouts.

---

## 2.4 `POST /webhooks/stripe`

Receives Stripe webhook events.

Processing requirements:

1. Receive the webhook request.
2. Verify the Stripe webhook signature.
3. Deduplicate the event.
4. Process the event only once.
5. Update the relevant subscription information.

The webhook endpoint must not trust the request body without verifying its Stripe signature.

### Implementation details (Phase 3)

* Signature verification uses `stripe.Webhook.construct_event()` against `STRIPE_WEBHOOK_SECRET`. An invalid signature returns `400` and no data is changed.
* Deduplication checks `webhook_events.stripe_event_id` before any processing; an already-seen event returns `{"status": "already processed"}` without touching subscription data.
* Handled event types:
  * `checkout.session.completed` → creates or updates the tenant's `subscription` row (plan, `stripe_customer_id`, `stripe_subscription_id`, status `active`).
  * `customer.subscription.updated` → updates `subscription.status`.
  * `customer.subscription.deleted` → sets `subscription.status` to `canceled`.
* Local delivery/testing uses the Stripe CLI (`stripe listen --forward-to localhost:8000/webhooks/stripe`, `stripe trigger <event>`) — no public URL or tunnel required.

---

# 3. Idempotency Strategy

## Question

**What happens if the same idempotency key is sent a second time?**

The same request must not create a second usage event.

### Flow

1. The client sends a request to `POST /generate` with an `Idempotency-Key`.
2. The application checks whether a `usage_event` with that key already exists **for that tenant**.
3. If the key exists:

   * Do not create another usage event.
   * Return the result associated with the existing event.
4. If the key does not exist:

   * Validate the request and quota.
   * Create a new usage event.
   * Calculate the cost.
   * Return the successful result.
5. The database-level `UNIQUE` constraint on `(tenant_id, idempotency_key)` provides protection against race conditions where two concurrent requests use the same key.

### Race Condition Protection

Application-level checking alone is not sufficient.

For example:

```text
Request A → check key → not found
Request B → check key → not found
Request A → insert event
Request B → insert event
```

Without a database constraint, both requests could create duplicate usage records.

With:

```text
UNIQUE(tenant_id, idempotency_key)
```

only one insert can succeed. The database therefore acts as the final protection against duplicate usage events.

### Implementation (Phase 2)

Implemented as a two-layer check in `meter_service.record_usage()`:

1. **Application-level lookup** — query for an existing `(tenant_id, idempotency_key)` row first; if found, raise `DuplicateRequestError` immediately without touching the database further.
2. **Database-level catch** — if two requests race past the lookup simultaneously, the second `INSERT` fails with `IntegrityError` (constraint violation). This is caught, the transaction is rolled back, and the existing row is re-queried and returned as a duplicate — rather than propagating the error to the client.

This guarantees exactly-once recording even under concurrent retries, not just sequential ones.

---

# 4. Webhook Deduplication Strategy *(added in Phase 3)*

Stripe delivers events with at-least-once semantics, so the same `checkout.session.completed` (or other) event may be sent more than once (e.g. after a slow response or timeout on this system's side).

### Flow

1. Verify the event signature. Invalid signature → `400`, nothing recorded, nothing processed.
2. Look up `event["id"]` in `webhook_events`.
3. If found → return `"already processed"` and stop; no subscription changes occur.
4. If not found → insert the event id into `webhook_events` **before** processing, then handle the event and update the relevant `subscription` row.

This mirrors the usage-event idempotency approach: a unique constraint (`webhook_events.stripe_event_id`) is the ultimate guarantee, with an application-level check first to avoid unnecessary work.

---

# 5. Design Decisions Summary

* Use UUIDs for primary keys.
* Store monetary values as integer cents, never floating-point values.
* Store usage as immutable usage events.
* Add an index on `usage_events.tenant_id`.
* Add an index on `usage_events.created_at`.
* Enforce idempotency using a **database-level UNIQUE constraint** on `(tenant_id, idempotency_key)`.
* Return the previously recorded result for duplicate idempotency requests.
* Verify Stripe webhook signatures before processing events.
* Deduplicate Stripe webhook events using a dedicated `webhook_events` table before updating subscriptions.
* Keep token breakdown information in nullable JSON metadata.
* Attach `tenant_id` as Stripe metadata (on Customer and Checkout Session) so webhook payloads can be resolved back to an internal tenant.
* Reuse an existing Stripe customer on repeat checkouts instead of creating duplicates.

---

# 6. Progress Log

| Phase | Status | Notes |
|---|---|---|
| Phase 1 — Design | ✅ Done | Schema, API contract, idempotency strategy documented above |
| Phase 2 — Core Billing Logic | ✅ Done | Idempotent metering (`meter_service.py`) and quota enforcement (`quota_service.py`) implemented; composite unique constraint used instead of global unique key |
| Phase 3 — Stripe Integration | ✅ Done | Checkout session creation, webhook signature verification, and event deduplication implemented; `webhook_events` table added |
| Phase 4 — Cost Calculation & Finalization | ⏳ Not started | AI token pricing rules, cost rollups, full test suite, README + diagram |
| Phase 5 — Demo Prep | ⏳ Not started | — |
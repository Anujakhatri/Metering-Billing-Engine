# Database Schema, API Contract & Idempotency Strategy

## 1. Database Schema Design

The system uses four main tables:

### 1.1 `tenants`

Stores information about each tenant/customer.

| Column       | Type      | Constraints / Notes |
| ------------ | --------- | ------------------- |
| `id`         | UUID      | Primary Key         |
| `name`       | String    | Tenant name         |
| `created_at` | Timestamp | Creation timestamp  |

---

### 1.2 `plans`

Stores the available subscription plans and their usage limits.

| Column           | Type    | Constraints / Notes                                    |
| ---------------- | ------- | ------------------------------------------------------ |
| `id`             | UUID    | Primary Key                                            |
| `name`           | String  | `free` / `pro`                                         |
| `api_call_limit` | Integer | Monthly API call quota                                 |
| `ai_token_limit` | Integer | Monthly AI token quota                                 |
| `price_cents`    | Integer | Price stored in cents; never use floating-point values |

`price_cents` is stored as an integer to avoid floating-point precision issues when calculating monetary values.

---

### 1.3 `subscriptions`

Stores the subscription associated with each tenant.

| Column                   | Type   | Constraints / Notes                |
| ------------------------ | ------ | ---------------------------------- |
| `id`                     | UUID   | Primary Key                        |
| `tenant_id`              | UUID   | Foreign Key → `tenants.id`         |
| `plan_id`                | UUID   | Foreign Key → `plans.id`           |
| `stripe_customer_id`     | String | Nullable                           |
| `stripe_subscription_id` | String | Nullable                           |
| `status`                 | String | `active` / `canceled` / `past_due` |

---

### 1.4 `usage_events`

Stores individual API and AI token usage events.

| Column            | Type      | Constraints / Notes                 |
| ----------------- | --------- | ----------------------------------- |
| `id`              | UUID      | Primary Key                         |
| `tenant_id`       | UUID      | Foreign Key → `tenants.id`; indexed |
| `type`            | String    | `api_call` / `ai_tokens`            |
| `quantity`        | Integer   | Number of API calls or tokens used  |
| `idempotency_key` | String    | **UNIQUE constraint required**      |
| `metadata`        | JSON      | Nullable; stores token breakdown    |
| `created_at`      | Timestamp | Indexed                             |

For AI token usage, `metadata` may contain a breakdown such as:

```json
{
  "input": 1000,
  "cached": 200,
  "output": 500,
  "reasoning": 100
}
```

### Important Database Constraints

The following indexes and constraints are required:

* Primary key on every table's `id`.
* Foreign key from `subscriptions.tenant_id` to `tenants.id`.
* Foreign key from `subscriptions.plan_id` to `plans.id`.
* Foreign key from `usage_events.tenant_id` to `tenants.id`.
* **Unique constraint on `usage_events.idempotency_key`.**
* Index on `usage_events.tenant_id`.
* Index on `usage_events.created_at`.

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

### Response

```json
{
  "checkout_url": "<stripe-checkout-session-url>"
}
```

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

---

# 3. Idempotency Strategy

## Question

**What happens if the same idempotency key is sent a second time?**

The same request must not create a second usage event.

### Flow

1. The client sends a request to `POST /generate` with an `Idempotency-Key`.
2. The application checks whether a `usage_event` with that key already exists.
3. If the key exists:

   * Do not create another usage event.
   * Return the result associated with the existing event.
4. If the key does not exist:

   * Validate the request and quota.
   * Create a new usage event.
   * Calculate the cost.
   * Return the successful result.
5. The database-level `UNIQUE` constraint on `idempotency_key` provides protection against race conditions where two concurrent requests use the same key.

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
UNIQUE(idempotency_key)
```

only one insert can succeed. The database therefore acts as the final protection against duplicate usage events.

---

# 4. Design Decisions Summary

* Use UUIDs for primary keys.
* Store monetary values as integer cents, never floating-point values.
* Store usage as immutable usage events.
* Add an index on `usage_events.tenant_id`.
* Add an index on `usage_events.created_at`.
* Enforce idempotency using a **database-level UNIQUE constraint**.
* Return the previously recorded result for duplicate idempotency requests.
* Verify Stripe webhook signatures before processing events.
* Deduplicate Stripe webhook events before updating subscriptions.
* Keep token breakdown information in nullable JSON metadata.

# Usage Metering & Billing Engine

A high-performance billing engine designed to handle idempotent usage recording, strict quota enforcement, and Stripe-integrated subscription management.

## Architecture

```text
[ Client ] 
    |
    v
[ FastAPI App ]
    |
    +--> [ Quota Service ] ----> [ DB: Subscriptions/Plans ]
    |      (Enforces limits)
    |
    +--> [ Meter Service ] ----> [ DB: Usage Events ]
    |      (Idempotent recording)
    |
    +--> [ Pricing Service ] --> [ Config: Pricing Constants ]
    |      (Calculates micro-cent costs)
    |
    +--> [ Checkout/Webhook ] --> [ Stripe API ]
           (Payment Sync)
```

## Tech Stack
- **Backend**: Python 3.12+ (FastAPI, SQLAlchemy, Pytest)
- **Database**: PostgreSQL (Docker) & SQLite (`test.db` local fallback)
- **Payments**: Stripe API (Test Mode) & Stripe CLI for Webhooks
- **Infrastructure**: Docker & Docker Compose

---

## 🚀 Quickstart & Setup Guide

### 1. Environment Configuration
Copy the example environment file:
```bash
cp .env.example .env
```

### 2. Run the Application

#### Option A: Docker Compose (PostgreSQL)
```bash
docker compose up --build
```

#### Option B: Local Python Environment (SQLite - `test.db`)
```bash
# Install dependencies
pip install -r requirements.txt

# Run server locally
uvicorn app.main:app --reload --port 8000
```

---

## 🧪 Testing & Verification Guide

Follow this step-by-step guide to test the project endpoints with `curl` and inspect the recorded evidence in `test.db`.

### Step 1: Seed Initial Database Data
Initialize the database with the `pro` plan, a test tenant, and an active subscription:

```bash
# Seed initial plan & Stripe price ID
python -m scripts.seed_stripe_price

# Seed a Test Tenant and Subscription
python -c "
from app.database import SessionLocal
from app.models import Tenant, Plan, Subscription

db = SessionLocal()
plan = db.query(Plan).filter(Plan.name == 'pro').first()
tenant = Tenant(id='11111111-1111-1111-1111-111111111111', name='Acme Corp')
db.merge(tenant)
db.commit()

sub = Subscription(tenant_id=tenant.id, plan_id=plan.id, status='active')
db.merge(sub)
db.commit()

print('✅ Seeded Tenant ID: 11111111-1111-1111-1111-111111111111 with Active Pro Subscription')
db.close()
"
```

---

### Step 2: Test Endpoints with `curl`

#### 1. Record API Call Usage (Idempotent Metering)
```bash
curl -X POST "http://localhost:8000/billing/generate" \
     -H "Content-Type: application/json" \
     -H "Idempotency-Key: req-1001" \
     -d '{
       "tenant_id": "11111111-1111-1111-1111-111111111111",
       "usage_type": "api_call",
       "quantity": 10
     }'
```

#### 2. Record AI Token Usage (Token Breakdown)
```bash
curl -X POST "http://localhost:8000/billing/generate" \
     -H "Content-Type: application/json" \
     -H "Idempotency-Key: req-1002" \
     -d '{
       "tenant_id": "11111111-1111-1111-1111-111111111111",
       "usage_type": "ai_tokens",
       "quantity": 1500,
       "token_breakdown": {
         "input_tokens": 1000,
         "output_tokens": 500
       }
     }'
```

#### 3. Test Idempotency Retry (Sending duplicate `Idempotency-Key`)
Re-sending request `req-1001` returns `duplicate: true` without double-counting usage in the database:
```bash
curl -X POST "http://localhost:8000/billing/generate" \
     -H "Content-Type: application/json" \
     -H "Idempotency-Key: req-1001" \
     -d '{
       "tenant_id": "11111111-1111-1111-1111-111111111111",
       "usage_type": "api_call",
       "quantity": 10
     }'
```

#### 4. Retrieve Usage Rollup & Costs
```bash
curl -X GET "http://localhost:8000/billing/usage/api_call?tenant_id=11111111-1111-1111-1111-111111111111"
```

---

### Step 3: View Recorded Evidence in Database (`test.db`)

Run this Python script to inspect all database tables (`plans`, `tenants`, `subscriptions`, `usage_events`):

```bash
python -c "
from app.database import SessionLocal
from app.models import Plan, Tenant, Subscription, UsageEvent

db = SessionLocal()
print('=== 📦 PLANS ===')
for p in db.query(Plan).all():
    print(f'ID: {p.id} | Name: {p.name} | API Limit: {p.api_call_limit} | Stripe Price: {p.stripe_price_id}')

print('\n=== 🏢 TENANTS ===')
for t in db.query(Tenant).all():
    print(f'ID: {t.id} | Name: {t.name}')

print('\n=== 📊 RECORDED USAGE EVENTS ===')
for e in db.query(UsageEvent).all():
    print(f'Event ID: {e.id} | Type: {e.type} | Qty: {e.quantity} | Idempotency Key: {e.idempotency_key}')

db.close()
"
```

Or query SQLite directly:
```bash
sqlite3 test.db "SELECT * FROM usage_events;"
```

---

## ⚡ Running Automated Unit Tests
To run the full Pytest suite (12 tests covering metering, quotas, pricing, and webhooks):
```bash
python -m pytest tests/
```

## Features
- **Idempotent Metering**: Guaranteed single-row recording per request key.
- **Strict Quotas**: Returns 429 Too Many Requests when plan limits are exceeded.
- **Stripe Integration**: Fully automated subscription lifecycle via verified webhooks & checkout endpoints.
- **Precision Pricing**: Token-category based cost calculation using integer micro-units.
- **Multi-Database**: Dockerized PostgreSQL support with local SQLite fallback.

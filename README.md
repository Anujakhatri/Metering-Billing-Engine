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

## Setup & Run

### 1. Environment
Copy the example environment file and fill in your Stripe keys:
```bash
cp .env.example .env
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Seed Data
```bash
python scripts/seed_stripe_price.py
```

### 4. Run Application
```bash
uvicorn app.main:app --reload --port 8000
```

### 5. Run Tests
```bash
export PYTHONPATH=$PYTHONPATH:. && pytest tests/
```

## Features
- **Idempotent Metering**: Guaranteed single-row recording per request key.
- **Strict Quotas**: 429 Too Many Requests when plan limits are exceeded.
- **Stripe Integration**: Fully automated subscription lifecycle via verified webhooks.
- **Precision Pricing**: Token-category based cost calculation using integer micro-units.

## Limitations
- **Plan Schema**: The `Plan` model currently lacks a `stripe_price_id` field in the database schema, which is required for the `/checkout` endpoint to function.
- **Database**: Currently uses SQLite for demonstration; production requires PostgreSQL for full `UUID` and `JSONB` support.
- **Pricing**: Simplified rollup that assumes current month usage.

"""
Pricing configuration for the Metering & Billing Engine.
All currency values are stored as integers to avoid floating point errors.
Standard unit: Micro-cents (1 cent = 1,000,000 micro-cents).
Token rates are expressed as the cost per 1,000,000 tokens in cents.
Because (tokens * cents_per_1M) / 1M = tokens * (cents_per_1M / 1M),
the 'rate_per_1M' value in cents is equivalent to the 'rate_per_token' in micro-cents.
"""

# Token rates (Cents per 1M tokens = Micro-cents per 1 token)
TOKEN_RATES = {
    "input_tokens": 150,          # 0.15$ / 1M tokens
    "cached_input_tokens": 75,    # 0.075$ / 1M tokens (Cheaper)
    "output_tokens": 600,         # 0.60$ / 1M tokens
    "reasoning_tokens": 600,      # Billed at output rate
}

# Plan Monthly Costs (in cents)
PLAN_COSTS = {
    "free": 0,
    "pro": 2000,                  # 20.00$ / month
}

# Plan Quotas (per month)
PLAN_QUOTAS = {
    "free": {
        "api_calls": 100,
        "ai_tokens": 1_000_000,
    },
    "pro": {
        "api_calls": 10_000,
        "ai_tokens": 100_000_000,
    },
}

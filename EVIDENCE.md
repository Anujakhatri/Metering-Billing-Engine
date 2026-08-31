# Evidence of Completion

## Definition of Done Verification

### 1. Monthly usage rolls up into a cost figure per tenant
- **Test**: `tests/test_pricing.py::test_rollup_calculation`
- **Output**:
```text
tests/test_pricing.py::test_rollup_calculation PASSED
```
- **Evidence**: Verified that seeding 10M mixed tokens results in exactly 14250 cents based on the configured rates.

### 2. AI token pricing handles cached input tokens, reasoning tokens, and output pricing correctly
- **Tests**: `tests/test_pricing.py`
- **Output**:
```text
tests/test_pricing.py::test_pricing_pure_input PASSED
tests/test_pricing.py::test_pricing_mixed_input_cached PASSED
tests/test_pricing.py::test_pricing_output_reasoning PASSED
tests/test_pricing.py::test_pricing_realistic_mixed PASSED
```
- **Evidence**: Pinned tests confirm:
    - Pure input: $1000 \times 150 \mu\text{c} = 150,000 \mu\text{c}$
    - Mixed Input/Cached: $1000 \times 150 + 1000 \times 75 = 225,000 \mu\text{c}$
    - Output/Reasoning: $1000 \times 600 + 1000 \times 600 = 1,200,000 \mu\text{c}$

### 3. Pricing constants are pinned and covered by tests
- **Evidence**: Constants are defined in `config/pricing_config.py`:
```python
TOKEN_RATES = {
    "input_tokens": 150,
    "cached_input_tokens": 75,
    "output_tokens": 600,
    "reasoning_tokens": 600,
}
```
- These values are directly asserted in `tests/test_pricing.py`.

### 4. Comprehensive Test Coverage
- **Duplicate Usage Prevention**:
```text
tests/test_metering.py::test_idempotency_single_row PASSED
```
- **Quota Boundary (At/Under/Over)**:
```text
tests/test_metering.py::test_quota_exactly_at_limit PASSED
tests/test_metering.py::test_quota_exceeded PASSED
```
- **Idempotent Retry (Double-count fix)**:
```text
tests/test_metering.py::test_idempotent_retry_double_counting PASSED
```
- **Invalid Webhook Rejection**:
```text
tests/test_webhooks.py::test_webhook_bad_signature PASSED
```
- **Duplicate Webhook Handling**:
```text
tests/test_webhooks.py::test_webhook_duplicate_event_id PASSED
```
- **Cost Calculations**:
```text
tests/test_pricing.py::test_pricing_realistic_mixed PASSED
```

### 5. Submission Pack
- [x] `README.md` - Present
- [x] `capstone.yaml` - Present
- [x] `EVIDENCE.md` - Present
- [x] `BUILDLOG.md` - Present
- [x] `.env.example` - Present

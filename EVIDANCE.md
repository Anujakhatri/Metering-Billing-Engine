Summary

┌─────────────────┬──────────────────────────────────────────────────────────┐
│    Condition    │          Requirement          │ Result │                  Notes                   │
├─────────────────┼──────────────────────────────────────────────────────────┤
│ 1. Idempotency  │ Same key twice $\rightarrow$  │   ✅   │ Enforced by DB unique constraint and     │
│                 │ 1 DB row            ice logic.                           │
├─────────────────┼───────────────────────────────┼────────┼──────────────────────────────────────────┤
│ 2. Quota (At    │ $999 \rightarrow 100ectly handled by > limit logic.      │
│ Limit)          │ $\rightarrow$ Allowed         │        │                                          │
├─────────────────┼──────────────────────────────────────────────────────────┤
│ 3. Quota        │ $1000 \rightarrow 1001$       │   ✅   │ Correctly handled by > limit logic.      │
│ (Exceeded)      │ $\rightarrow$ 429                                        │
├─────────────────┼───────────────────────────────┼────────┼──────────────────────────────────────────┤
│ Edge Case       │ Idempotent Retry    ED. Retry is rejected with 429 if    │
│                 │ $\rightarrow$ No Double-Count │        │ first attempt put usage at limit.

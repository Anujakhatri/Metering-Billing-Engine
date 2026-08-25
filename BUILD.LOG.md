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
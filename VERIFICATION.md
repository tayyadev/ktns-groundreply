# Implementation verification (October 18, 2026)

## Completed in the authoring environment

- The Python backend package and migration Python sources pass bytecode compilation.
- `cd backend && PYTHONPATH=. pytest -q`: **21 passed, 1 skipped**.
- Unit coverage exercises correct grounding/citation behavior, deterministic abstentions, escalation, safety patterns and token/session helpers.
- SQLAlchemy table and PostgreSQL DDL compilation was inspected, including the vector HNSW index.
- Frontend TS and TSX syntax transpilation was checked with the installed TypeScript compiler (not a complete React type-check).
- Source is packaged with CI that includes real PostgreSQL/pgvector integration tests and an npm production build.

## Not completed in the authoring environment

- **No full live service was deployed.** Docker Engine is unavailable here.
- The live PostgreSQL/pgvector integration test is skipped locally (no database server). It is enabled in GitHub Actions.
- React/TypeScript dependency installation and full `npm run build` could not be executed without npm registry access.
- No real OpenAI API calls, email delivery, Stripe events, web security scan, load test, or pen test has run.

## Required user acceptance before selling

1. Follow `README.md` quick-start with Docker Desktop and a separately provisioned OpenAI key.
2. Confirm Compose migrations succeeded, Postgres vector extension is present, and `/api/health/ready` reports OK.
3. Register a trial workspace and add `examples/refund-policy.txt`. Confirm document becomes ready.
4. Create a relevant ticket; confirm the response cites the policy and can be approved and copied.
5. Test an unsupported claim and sensitive account-change request. Confirm each escalates.
6. Confirm separate workspaces cannot read/write each other's data, and viewer cannot approve.
7. Set test Stripe prices and signed webhook endpoint, then verify upgrades and cancellations.
8. Run a vulnerability scan, restore-from-backup drill, privacy review, rate limiting, and HTTPS check before handling external customer data.

**Release category:** pilot-grade source implementation with operational foundation; *not* security-certified, SLA-backed, or deployed-for-sale as delivered.

# KTNS GroundReply

**Sellable, self-hostable, multi-tenant AI support operations platform** built with Python, FastAPI, React, TypeScript, PostgreSQL/pgvector and event-driven workers.

GroundReply turns a company's FAQ/policy documents into **source-cited support reply drafts**. Four specialist AI stages triage the question, retrieve relevant knowledge, compose a draft and independently review factual grounding. Employees must approve every reply; **the application does not send email automatically**.

> **Release status:** Production-oriented pilot implementation (v0.1), not a security-certified or already-deployed service. Backend unit tests have been executed locally; an end-to-end database test is included for CI. Perform the launch checks in `SECURITY.md` before accepting real customers.

## Feature map

| Capability | Shipped implementation |
|---|---|
| Python backend | Asynchronous FastAPI + SQLAlchemy 2, type-annotated domain models, validated schemas |
| Multi-agent workflow | Triage / pgvector research / structured answer / independent grounding review |
| Retrieval | Chunking, `text-embedding-3-small` embeddings, cosine-ranked pgvector HNSW, cited passages |
| Persistent memory | Last three human-approved responses for the same customer, scoped by workspace |
| Background processing | PostgreSQL job queue, atomic `SKIP LOCKED` claims, leases, heartbeats, retries, dead-letter state |
| Product UI | React 19 + TypeScript: overview, inbox, knowledge, evaluation cases, team, plans, audit trail |
| Review guardrails | No uncited autonomously sent answers; escalation for missing evidence, reviewer objections and sensitive data |
| Quality assurance | Offline unit tests, mocked multi-agent tests, Postgres cross-tenant/API integration tests, regression-evaluation UI |
| Multi-tenancy and access | Workspace isolation on every query, owner/agent/viewer roles, one-time team invitations |
| Billing | Optional Stripe Checkout / customer portal / signed, idempotent webhooks, workspace plan quotas |
| Deployment and operations | Docker Compose, Caddy HTTPS production variant, Alembic migration, health checks, CI, manual CD |

## Architecture

```text
Browser (React/TS)
      | session cookie + CSRF
      v
Caddy HTTPS -> Nginx SPA reverse proxy -> FastAPI
                                           |
                                    PostgreSQL / pgvector
                                  /          |          \
                         workspaces     jobs/outbox     documents/chunks
                                           |
                                      Worker fleet
                                           |
                         classify -> retrieve -> draft -> review
                                  \        |          /
                                audit, tokens, citations
                                           |
                                     Approval queue
                                 (human sends reply)
```

The workflow uses [OpenAI Responses Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs) and [pgvector cosine search](https://github.com/pgvector/pgvector-python). They are kept behind a minimal provider interface to support later model comparisons.

## Quick start — local Docker (Windows, macOS or Linux)

**Prerequisites:** Docker Desktop or Docker Engine with Compose; an OpenAI API key with billing enabled. Node and Python are not needed on the host to run the full stack.

```sh
# From the project root:
cp .env.example .env
# Edit .env:
# JWT_SECRET: a random 32+ character value (for example: openssl rand -hex 32)
# OPENAI_API_KEY: your valid key (kept only on the backend)

docker compose up -d --build
```

Open **http://localhost:8080**, create an owner account and choose a workspace name. The API documentation is at **http://localhost:8080/api/docs**; API readiness is at **http://localhost:8080/api/health/ready**. The local Docker configuration binds ports 8080 and 8000 to `127.0.0.1` only.

> Note: `OPENAI_API_KEY` is optional for starting the UI but *required to actually index documents and draft replies*. Background jobs will retry and eventually fail if absent. After supplying the key, restart the worker and use the “Retry” action for failed items.

### First working demo

1. Open **Knowledge base**, select **Add source** and paste the text from `examples/refund-policy.txt`. Give it the title `Returns and Exchanges`. Watch its indexing status change to **Ready**.
2. Open **Ticket inbox**, create a ticket titled `Customer return policy`, and ask: `How many days do I have to return an item?`.
3. Watch **Queued → Processing → Awaiting approval / Needs review**, then read the cited passages, grounding-review notes and agent trace.
4. Approve (and edit if appropriate) the reply, then copy it into your existing support email, CRM or ticketing tool.
5. Add evaluation cases from `examples/evaluation-cases.json` in **AI evaluations**. Run the suite, review failures and compare changes before upgrades.

## Environment settings

| Variable | Purpose |
|---|---|
| `JWT_SECRET` | **Required.** Random 32+ character session-signing key |
| `OPENAI_API_KEY` | **Required for AI features.** Never paste into the React app |
| `OPENAI_MODEL` | Structured-output model, defaults to `gpt-4.1-mini` |
| `EMBEDDING_MODEL` | Must output 1536 dimensions, defaults to `text-embedding-3-small` |
| `POSTGRES_PASSWORD` | Database password; local stack has a development fallback |
| `APP_ORIGIN` | Browser origin for Checkout redirects, set by production Compose |
| `COOKIE_SECURE` | Must be true for HTTPS deployments |
| `STRIPE_SECRET_KEY` | Optional private Stripe API key |
| `STRIPE_WEBHOOK_SECRET` | Optional signature-verification key for `/api/webhooks/stripe` |
| `STRIPE_PRICE_STARTER` | Optional recurring Price ID for 500 monthly drafts |
| `STRIPE_PRICE_GROWTH` | Optional recurring Price ID for 5,000 monthly drafts |
| `PUBLIC_HOSTNAME` | Required for production Caddy TLS, e.g. `support.example.com` |

**Stripe activation:** In your Stripe account, create two recurring prices; copy their `price_...` IDs. Register `https://YOUR_PUBLIC_HOSTNAME/api/webhooks/stripe` with `checkout.session.completed`, `customer.subscription.created`, `customer.subscription.updated`, and `customer.subscription.deleted`. Fill all four Stripe variables in `.env` and redeploy. Only Stripe signs and authorizes subscription events; the frontend never sets its own plan.

## Local engineering workflow

```sh
cd backend
python -m venv .venv
. .venv/bin/activate  # Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -e '.[dev]'
pytest -q
ruff check app tests --select E4,E7,E9,F63,F7,F82

# In another terminal, if the Docker API is running on 127.0.0.1:8000:
cd ../frontend
npm install
npm run dev
npm run build
```

The frontend development server (Vite) is at `http://localhost:5173` and proxies `/api` to `http://localhost:8000`. The browser cookie is same-origin through Vite's proxy.

### Integration tests

A real PostgreSQL/pgvector test (cross-workspace isolation, CSRF, role gates, team invitations and document/ticket APIs) is supplied in `backend/tests/test_api_integration.py`. It runs automatically on GitHub Actions with a temporary pgvector service. To run locally, supply a **disposable database** via `DATABASE_URL`, run `alembic upgrade head`, set `RUN_DB_TESTS=1`, then run `pytest`.

## Production deployment

This repo includes a separate HTTPS/Caddy configuration for a Linux VPS. See **`OPERATIONS.md`** for setup, HTTPS, backups, monitoring and restore procedures. `.github/workflows/deploy.yml` supports manually approved deployment via SSH and rsync. Environment variables and database data are preserved on the server.

**No production launch without** TLS, offsite backups/restore test, rate limiting/WAF, documented data policy, error monitoring, domain/trademark review, tax/payment configuration and customer acceptance testing.

## Business packaging

- **Managed SaaS:** Set up a domain + Stripe prices, onboard individual workspaces and charge a monthly subscription.
- **Dedicated installation:** Deploy a single workspace on a customer's infrastructure and charge one-time implementation plus support.
- **White-label implementation:** Customize branding, policies and integrations for a client under a separate commercial agreement.

For pricing, target customers and a demo script, read **`SELLING.md`**. For architecture tradeoffs, read **`ARCHITECTURE.md`**. For security boundaries, read **`SECURITY.md`**.

## Known pilot limitations

- Data ingestion is currently **pasted plain text**; no PDF, URL crawler, email inbox, CRM sync, or live-chat widget is shipped.
- Replies are drafted and approved in GroundReply, then **copied/sent manually** from the customer's existing channel. No unsupported claims of automatic outbound delivery.
- Workspace owners can invite *new* users via links. Existing users cannot yet join a second workspace. Password reset, SSO and MFA are not included.
- No automatic data retention/deletion schedule, per-tenant encryption keys, dedicated moderation service or SOC 2/ISO compliance evidence. Human review is mandatory.
- AI quality depends on approved document quality, retrieval thresholds and provider behavior. Tests check useful controls but do not guarantee correct answers.
- No actual public production deployment or paid customer has been established by this source package.

## Ownership

Designed as proprietary code intended for commercial use by KTNSINNOVATIONS LLC. Review `LICENSE.txt`, third-party licenses, hosting obligations and relevant trademark issues before distribution.

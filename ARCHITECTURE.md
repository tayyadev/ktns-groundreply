# Architecture and engineering decision record

## Design target

A small B2B support team should be able to paste a short policy, ask a genuine customer question and obtain an attributable draft in a queue where a person can examine citations before anything leaves the system. The platform must provide a path from a one-workspace pilot to multiple tenants without rewriting retrieval, payments or job dispatch.

## Component map

| Component | Main code | Trust boundary |
|---|---|---|
| API and auth | `backend/app/main.py`, `api.py`, `security.py`, `dependencies.py` | Cookies, CSRF, active user membership and per-workspace filters |
| Domain schema | `backend/app/models.py` | Explicit `organization_id` on all tenant-domain tables |
| Durable jobs | `backend/app/jobs.py`, `worker.py` | Queue row reserved using `SELECT ... FOR UPDATE SKIP LOCKED`, lease token, retry state |
| RAG | `backend/app/retrieval.py`, `text_utils.py` | PG vector search filtered by workspace and ready documents |
| Agents | `backend/app/agents.py`, `llm.py` | Structured model output schema and deterministic citation validator |
| Evaluation | `backend/app/worker.py`, `text_utils.py` | Stored regression cases; no model outputs trusted as proof |
| Stripe | `backend/app/billing.py` | HMAC signature via Stripe library, webhook event idempotency |
| UI | `frontend/src/App.tsx`, `api.ts` | No provider keys in browser; user decision gates |
| Deployment | `deploy/compose.prod.yml`, `Caddyfile` | Public HTTPS proxy; API, worker and DB private |

## Four-stage workflow

1. **Triage agent:** classifies category and urgency using a strict JSON schema.
2. **Research agent:** embeds the query, queries a tenant-specific pgvector HNSW index and ranks at most five source excerpts. Embeddings use cosine distance; `MAX_COSINE_DISTANCE` is adjustable.
3. **Draft agent:** receives the question, retrieved passages and up to three human-approved earlier replies to the *same email address*. Earlier replies are context only, not an authority for factual assertions. Produces a structured answer, a list of passage references and abstention status.
4. **Review agent:** separately checks grounding and need for specialist escalation. A deterministic citation validator rejects invented reference IDs, and fixed-pattern sensitive-data guardrails can still escalate even if the review agent approves.

If retrieval finds no relevant sources, the system abstains. On successful drafting, the user sees **Awaiting approval** or **Needs review**; both demand a human decision. The system does **not** auto-send emails.

## Agent outputs, storage and costs

- The `ModelProvider` protocol abstracts `embed` and `structured` to make a second model vendor testable without rewriting business logic.
- The OpenAI adapter uses the Responses API with JSON Schema strict structured output. It records input/output token counts in `UsageEvent` and sets `store=False` for requests; this flag should not be misconstrued as a no-retention contract.
- Documents are chunked into approximately 1100-character windows with 140-character overlap, then embedded in batches of 32.
- All customer statements and document excerpts are **untrusted strings**. They do not become executable tools, shell commands or HTTP requests.
- Unit tests use a deterministic fake model. Separately, the UI evaluation runner uses live-model outputs and can find regressions when a knowledge base or prompt changes.

## Data and concurrency

`Organization` and `Membership` represent tenant boundaries. `Document`, `Chunk`, `Ticket`, `Job`, `EvaluationCase`, `EvaluationRun`, `UsageEvent`, and `AuditEvent` have organization IDs. Routes always include membership validation and organization filters. The retrieval query verifies both chunk and document belong to the same organization. Integration tests exercise negative access between workspaces. Consider PostgreSQL Row Level Security as additional defense-in-depth before enterprise scaling.

API writes enqueue jobs in the same database transaction as the business entity: a crash cannot result in a ticket without a queued draft job. Workers race using row locking plus `SKIP LOCKED`; each job has an expiry, a unique claim token, and a heartbeat. Retried document indexing removes the old chunk set in a single transaction and re-inserts it. Workers are safe to scale horizontally as long as the lease/heartbeat assumptions hold. Downstream external actions are not taken automatically.

## Decision matrix — why this stack

| Decision | Chosen | Alternative | Reason / tradeoff |
|---|---|---|---|
| Orchestration | Explicit typed Python workflow | Large general-purpose agent graph framework | Easier to inspect and unit test; less flexible for arbitrary tools until graph requirements justify one |
| Retrieval | PostgreSQL + pgvector | Managed vector DB | One database, lower early operating overhead; must tune indexes and backup correctly |
| Work queue | PostgreSQL jobs + leases | Redis/Celery, SQS | Transactional enqueue without extra service; grows less efficiently at very high throughput |
| Provider | OpenAI Responses + embeddings | Anthropic, local vLLM | Well-documented structured output and low integration effort; third-party API cost and data-processing terms |
| UI | React + TypeScript | Streamlit, server templates | Sellable modern UI and type-checked frontend; requires Node build pipeline |
| Billing | Hosted Stripe Checkout | Custom payment form | Avoid handling card data and implement signed subscription changes |
| Deployment | Docker Compose + Caddy | Kubernetes | Lowest reasonable pilot overhead; multi-region HA needs a later platform redesign |

## Model evaluation policy

Before any model switch, take a fixed reference dataset and compare: (a) abstention on missing information; (b) citation validation rate; (c) sensitivity escalations; (d) 95th percentile response latency; (e) total token spend per 100 tickets; (f) customer service reviewer acceptance rate. One promising model response is not sufficient evidence.

## Planned extensibility

- Dedicated client-specific model/configuration and retrieval threshold.
- Document ingestion workers for PDFs and URLs with content-type checks, virus scanning, size limits and SSRF prevention.
- Outbound approval connectors for Gmail/Zendesk/Intercom with OAuth and restricted scopes.
- SSO/SAML, SCIM, MFA, self-service data export/retention, formal RLS and full-text hybrid retrieval.
- OpenTelemetry traces, metrics collector, alerting, idempotent webhooks to customer systems.

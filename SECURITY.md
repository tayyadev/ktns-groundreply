# Security, privacy and pilot-to-production checklist

GroundReply is a **production-oriented pilot**. This document is not a claim of audit certification, regulatory compliance, prompt-injection immunity or readiness for unrestricted sensitive customer data. Assign a named technical owner to each launch control below.

## Controls included in this repository

- Passwords hashed using Argon2id (never stored as plaintext), JWT sessions stored in `HttpOnly`, `SameSite=Lax` cookies, configurable `Secure` flag, expiring after 12 hours.
- Anti-CSRF token required on authenticated write requests; frontend avoids localStorage/sessionStorage bearer tokens.
- Active database memberships determine roles, never client-supplied tenant IDs. Owner/agent/viewer permissions.
- Signed, single-use 72-hour team invitation tokens; only SHA-256 digests persisted.
- Explicit `organization_id` query filters for retrieved documents, history and ticket mutations; API integration test verifies isolation.
- Sensitive configuration and provider API key remain backend-side. No arbitrary HTTP tool execution from retrieved text, no automatic email sending or destructive agent tools.
- Citation ID validation and human approval. Reviewer escalation + elementary regex checks for likely SSNs/payment numbers and high-risk account/financial changes.
- Signed Stripe webhooks, event idempotency and server-side plan state. Stripe handles payment-card entry.
- Reverse proxy configuration: TLS via Caddy, anti-clickjacking and CSP headers via nginx, private PostgreSQL/backend network.
- Job lease protection, retry ceiling, migration files, app/db health endpoints and owner-only ops metrics.

## Controls needed before onboarding outside customers

| Priority | Action | Acceptance test |
|---|---|---|
| Critical | Set long random session and DB secrets; store API keys in secure secret manager, restrict server access | Scan build/image/logs for accidental keys; rotate test secrets |
| Critical | Configure real HTTPS DNS and `COOKIE_SECURE=true`; put API behind proxy/WAF | TLS scan, HSTS check, cookie inspection |
| Critical | Add edge abuse protection/rate limits for signup, login, invitations, ticket creation, and document uploads | Burst test + account-lockout policy |
| Critical | Add tested offsite encrypted backups, restore drill and alerts on failures | Restore backup into fresh server successfully |
| Critical | Establish data-processing agreements/privacy policy with customers and model provider | Legal/security signoff |
| Critical | Reject/redact sensitive data and secrets before sending to third-party LLMs where applicable | DLP test corpus; incident escalation plan |
| Critical | Independent penetration test incl. horizontal tenant escape, request forgery, prompt injection, injection of knowledge snippets | Document findings and remedies |
| High | Add password reset, MFA/SSO for paid workspaces, session revocation, login rate alerts | Security acceptance tests |
| High | Add data export, customer deletion and configurable retention with workflow coverage | Deletion removes tickets, vectors, usage data where required |
| High | Add Postgres RLS, audit log integrity/retention policy, immutable backups | Tenant red-team tests, RBAC coverage |
| High | Pin all dependencies and base image digests; install vulnerability and license scanners | Green dependency + container scans |
| High | Monitor request latency, job queue lag, dead jobs, API error rates, model output quality and unusual token burn | Pager/alert drill |
| High | Write incidents, escalation, privacy and SLA playbooks; designate on-call owner | Tabletop exercise |
| High | Enforce spend caps for evaluation/embedding traffic and per-workspace fair usage | Billing load test |
| High | Formal independent accessibility and browser regression checks | WCAG audit |

## Important boundaries

**Prompt injection:** The system separates model instructions from document passages and never grants the LLM arbitrary write/network tools, but retrieved content can still bias output. Grounded citations and an independent model review are not a guarantee of correctness; human review is always required.

**Personal data:** User emails, tickets and past approved replies are stored in PostgreSQL; document text and questions are transmitted to the configured LLM API. `store=False` is only an API request parameter, not proof of zero retention by a provider. Do not process regulated healthcare/financial records without the required contractual, security and privacy work.

**Availability:** A single VPS and one Postgres instance are not highly available. Worker retries cannot eliminate downtime, and migration rollback may require a database restore.

**AI outputs:** Drafts are not sent automatically; even if a draft has citations, the reviewer must check actual source support and business policy.

**Licensing/IP:** Perform a final trademark check for **KTNS GroundReply** and review external model, library and customer content terms before selling. A quick web-name check is not trademark clearance.

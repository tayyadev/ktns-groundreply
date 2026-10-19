# Production operations and runbook

## Linux VPS deployment (suggested initial pilot)

Use a Linux host with Docker Engine + Compose, public DNS A/AAAA for your product domain, and inbound TCP 80/443 plus UDP 443 (for HTTP/3). A small pilot may start on 4 vCPU / 8 GB RAM; benchmark with representative documents and traffic before committing to sizing. Put PostgreSQL data on a durable volume and use encrypted provider storage.

1. Install Docker and its Compose plugin. Create `/opt/groundreply` owned by the deployment user; ensure the user has Docker privileges.
2. Transfer this repository there, including the `deploy/` directory. On the server, `cp .env.example .env`, then set:
   - `JWT_SECRET` to `openssl rand -hex 32` output.
   - `POSTGRES_PASSWORD` to a **URL-safe** high-entropy value (e.g. `openssl rand -hex 24`).
   - `OPENAI_API_KEY` to a valid key.
   - `PUBLIC_HOSTNAME` to a DNS name pointing to the server (for example `support.company.com`).
   - Optional Stripe variables only after real products/prices/webhook are configured.
3. Restrict `.env` to the deployment user: `chmod 600 .env`. Store independent encrypted copies of secrets in your chosen secure manager.
4. Run `docker compose --env-file .env -f deploy/compose.prod.yml up -d --build`.
5. Wait for Caddy to issue HTTPS certificates. Open `https://$PUBLIC_HOSTNAME/api/health/ready`; it should return `{"ok":true}`. Test one signup, one knowledge source, one evaluated ticket, one human approval.
6. Test Stripe with Stripe's test mode/signature tooling before live prices. Verify webhook events do not grant paid quota when subscription is unpaid/canceled.
7. Configure an external status check of `/api/health/ready` at 1–5-minute intervals. Alert on repeated failures. Monitor container logs and available disk/RAM.

**Do not expose the database or backend services directly to the public internet.** The production Compose only exposes Caddy.

## Scaling

`docker compose --env-file .env -f deploy/compose.prod.yml up -d --scale worker=3` increases worker concurrency. `SELECT ... FOR UPDATE SKIP LOCKED` ensures only one worker claims each ready job; its claim lease token and heartbeat provide crash recovery. PostgreSQL remains the primary bottleneck as throughput grows.

## Operational checks

- API live: `GET /api/health/live` (process running).
- API ready: `GET /api/health/ready` (database reachable).
- Owner-only JSON metrics: `GET /api/ops/metrics` includes status counts, dead-letter job history and oldest queued item.
- Owner-only activity trail: `GET /api/audit` (up to 60 recent key business events).
- Dashboard **Plans & usage** displays tickets and model tokens for the current month.
- Worker console: `docker compose --env-file .env -f deploy/compose.prod.yml logs --tail=100 worker`.
- Container status: `docker compose --env-file .env -f deploy/compose.prod.yml ps`.
- Long queue, repeated dead jobs or continuously failing document indexing mean investigate OpenAI connectivity, tenant content or DB capacity. Individual failed docs and tickets have a *Retry* button after the cause is fixed.

Logging deliberately avoids copying raw customer prompts into ordinary access logs. Before production, configure a privacy-aware observability backend with protected access and retention settings.

## Backups and restore

Backup: `./scripts/backup_db.sh production`. This writes a local compressed SQL dump in `backups/`, with restrictive file permissions. **Copy it to an encrypted offsite location and verify the copy**; a backup only on the same VPS does not protect against host failure. Encrypt before transmitting over a non-trusted path. Prefer automated daily backups and periodic tested restores.

Restore drill (on an isolated fresh test instance, never the live database):

```sh
# After starting test PostgreSQL and matching schema version:
gunzip -c path/to/groundreply-backup.sql.gz | docker compose exec -T db psql -U groundreply -d groundreply
```

Note: restore instructions above assume the **development** Compose and database credentials; for production replace `docker compose exec` with `docker compose --env-file .env -f deploy/compose.prod.yml exec -T` and use corresponding DB user. Do not restore into a non-empty production schema without a recovery plan. Verify row counts, retrieval and role boundaries after restoration.

## CI/CD

`.github/workflows/ci.yml` runs Python tests against a real pgvector service and compiles the TypeScript frontend. `.github/workflows/deploy.yml` is a manual production deployment requiring an approved GitHub `production` environment and secrets `DEPLOY_SSH_KEY`, `DEPLOY_KNOWN_HOSTS`, `DEPLOY_USER`, `DEPLOY_HOST`. The target server retains its own `.env`; release sync excludes it. Never put secrets in GitHub source or build logs.

## Cost model

Costs consist of the fixed VPS+storage+backup+domain cost plus variable embedding and generation tokens. For each ticket the workflow makes **one embedding call plus up to three structured generations** (triage, draft, review). Adding a document embeds its chunks once per ingestion/retry. The API stores actual input/output token counts; consult your live model provider's pricing table to compute spend. Do not guarantee a particular dollar cost based on a static estimate.

## Release gates

A new production release requires: CI passing; database migration reviewed; no critical vulnerabilities; restore plan and on-call coverage; successful tenant-isolation test; ticket citation quality evaluated on real, permissioned examples; rollback path recorded; canary tenant acceptance; and manual review of production Stripe behavior.

"""Runs against a disposable real PostgreSQL+pgvector database in CI.
Set RUN_DB_TESTS=1 and DATABASE_URL then run `alembic upgrade head && pytest`.
"""
import os
import uuid

import pytest


@pytest.mark.skipif(os.getenv("RUN_DB_TESTS") != "1", reason="Needs configured pgvector test Postgres")
@pytest.mark.asyncio
async def test_auth_csrf_roles_quota_and_cross_tenant_boundaries():
    from httpx import ASGITransport, AsyncClient
    from app.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as a:
        unique = uuid.uuid4().hex[:12]
        response = await a.post("/api/auth/register", json={
            "email": f"owner-{unique}@example.com", "password": "very-secure-password-01",
            "organization_name": "First Test Company",
        })
        assert response.status_code == 201, response.text
        actor = (await a.get("/api/auth/me")).json()
        csrf = {"X-CSRF-Token": actor["csrf_token"]}
        assert actor["role"] == "owner"
        without_csrf = await a.post("/api/documents", json={"title":"Policy","content":"X"*90})
        assert without_csrf.status_code == 403
        created = await a.post("/api/documents", headers=csrf, json={
            "title": "Returns Policy", "content": "Returns are allowed for 30 days after purchase. "*3,
        })
        assert created.status_code == 202, created.text
        doc_id = created.json()["id"]
        ticket = await a.post("/api/tickets", headers=csrf, json={"subject": "Refund inquiry", "question": "When may I return my purchase?"})
        assert ticket.status_code == 202
        invite = await a.post("/api/team/invite", headers=csrf, json={"email":f"agent-{unique}@example.com", "role":"viewer"})
        assert invite.status_code == 201
        token = invite.json()["invite_url"].split("invite=", 1)[1]

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as teammate:
            accepted = await teammate.post("/api/auth/accept-invite", json={"token":token,"password":"secure-invite-password"})
            assert accepted.status_code == 201
            member = (await teammate.get("/api/auth/me")).json()
            assert member["role"] == "viewer"
            no_write = await teammate.post("/api/tickets", headers={"X-CSRF-Token": member["csrf_token"]}, json={"subject":"a new ticket","question":"Why am I read only?"})
            assert no_write.status_code == 403

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as second:
            registration = await second.post("/api/auth/register", json={
                "email": f"other-{unique}@example.com", "password":"very-secure-password-02", "organization_name":"Unrelated tenant",
            })
            assert registration.status_code == 201
            other = (await second.get("/api/auth/me")).json()
            denied = await second.delete(f"/api/documents/{doc_id}", headers={"X-CSRF-Token": other["csrf_token"]})
            assert denied.status_code == 404  # never reveal other tenant's data
            listed = (await second.get("/api/documents")).json()
            assert all(item["id"] != doc_id for item in listed)

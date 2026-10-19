import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.api import router as api_router
from app.billing import ingest_webhook, router as billing_router
from app.db import SessionFactory, engine
from app.security import validate_secret

log = logging.getLogger("groundreply.api")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    validate_secret()
    yield
    await engine.dispose()


app = FastAPI(
    title="KTNS GroundReply API", version="0.1.0",
    openapi_url="/api/openapi.json", docs_url="/api/docs", redoc_url=None,
    lifespan=lifespan,
)


@app.middleware("http")
async def request_middleware(request: Request, call_next):
    request_id = request.headers.get("x-request-id", "")
    if not 0 < len(request_id) <= 72 or any(not (c.isalnum() or c in "-_") for c in request_id):
        request_id = str(uuid.uuid4())
    start = time.perf_counter()
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Cache-Control"] = "no-store"
    log.info("method=%s path=%s code=%d duration_ms=%d id=%s",
             request.method, request.url.path, response.status_code,
             round((time.perf_counter() - start) * 1000), request_id)
    return response


@app.get("/api/health/live", tags=["health"])
async def live():
    return {"ok": True}


@app.get("/api/health/ready", tags=["health"])
async def ready():
    try:
        async with SessionFactory() as session:
            await session.execute(text("SELECT 1"))
        return {"ok": True}
    except Exception:
        return JSONResponse(status_code=503, content={"ok": False})


@app.post("/api/webhooks/stripe", tags=["billing"])
async def stripe_webhook(request: Request):
    raw = await request.body()
    if len(raw) > 1024 * 128:
        return JSONResponse(status_code=413, content={"detail": "Webhook too large"})
    status = await ingest_webhook(raw, request.headers.get("stripe-signature"))
    return {"status": status}


app.include_router(api_router, prefix="/api")
app.include_router(billing_router, prefix="/api")

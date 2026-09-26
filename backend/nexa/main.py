import json
import logging
import uuid

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from redis import Redis
from sqlalchemy import text

from nexa.config import settings, version
from nexa.db import SessionLocal
from nexa.routes import admin, auth, commerce, content, instagram, notifications, support, webhooks, workspace

logging.getLogger("httpx").setLevel(logging.CRITICAL)
logging.getLogger("httpcore").setLevel(logging.CRITICAL)
log = logging.getLogger("nexa.api")
app = FastAPI(title="Farstar Nexa", version=version(), docs_url=None, redoc_url=None, openapi_url=None)
for router in (
    auth.router,
    workspace.router,
    commerce.router,
    admin.router,
    instagram.router,
    webhooks.router,
    support.router,
    notifications.router,
    content.router,
):
    app.include_router(router)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    request_id = str(uuid.uuid4())
    if request.method not in {"GET", "HEAD", "OPTIONS"} and not request.url.path.startswith("/webhooks/"):
        origin = request.headers.get("origin")
        if origin and origin.rstrip("/") != settings().base_url.rstrip("/") and request.url.path != "/api/telegram/webapp-auth":
            return JSONResponse({"detail": "origin_invalid"}, status_code=403)
    # Read with a hard cap, including chunked requests without Content-Length.
    total, chunks = 0, []
    async for chunk in request.stream():
        total += len(chunk)
        if total > 1024 * 1024:
            return JSONResponse({"detail": "request_too_large"}, status_code=413)
        chunks.append(chunk)
    request._body = b"".join(chunks)
    try:
        response = await call_next(request)
    except Exception as exc:
        log.error(
            json.dumps(
                {"event": "request_failed", "request_id": request_id, "error_type": type(exc).__name__}
            )
        )
        response = JSONResponse({"detail": "internal_error", "request_id": request_id}, status_code=500)
    response.headers.update(
        {
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "Referrer-Policy": "no-referrer",
            "Cache-Control": "no-store",
            "X-Request-ID": request_id,
        }
    )
    return response


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError):
    # Pydantic's default error output can contain rejected passwords and tokens.
    return JSONResponse(
        {"detail": "validation_error", "fields": [list(e["loc"]) for e in exc.errors()]}, status_code=422
    )


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/ready")
def ready():
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
            db.execute(text("SELECT version_num FROM alembic_version"))
        with Redis.from_url(settings().redis_url, socket_timeout=2) as client:
            client.ping()
            if not client.get("nexa:worker:heartbeat"):
                raise RuntimeError("worker_unavailable")
    except Exception:
        return JSONResponse({"status": "unavailable"}, status_code=503)
    return {"status": "ready"}


@app.get("/api/config")
def public_config():
    return {
        "product": "Farstar Nexa",
        "version": version(),
        "mock_mode": settings().mock_mode,
        "registration_enabled": settings().registration_enabled,
    }

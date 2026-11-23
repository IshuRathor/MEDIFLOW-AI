import logging
import time
import json
import uuid

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import CORS_ORIGINS, ENVIRONMENT, validate_startup_config
from app.core.security import get_current_user

from app.api.patients import router as patient_router
from app.api.bills import router as bills_router
from app.api.payments import router as payments_router
from app.api.doctor import router as doctor_router
from app.api.appointment import router as appointment_router
from app.api.availability import router as availability_router

from app.api.triage import router as triage_router
from app.api.auth import router as auth_router
from app.api.dashboard import router as dashboard_router
from app.api.ai import router as ai_router

from app.database.db import SessionLocal
from app.models.audit import AuditLog
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import text
from app.core.config import GEMINI_API_KEY


# ============================================================
# FASTAPI APPLICATION
# ============================================================

app = FastAPI(
    title="Hospital Management AI API",
    description="Backend API for the AI-powered Hospital Management System",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

logger = logging.getLogger(__name__)


@app.on_event("startup")
def validate_production_configuration():
    validate_startup_config()


@app.middleware("http")
async def request_logging(request: Request, call_next):
    started_at = time.perf_counter()
    request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    logger.info(json.dumps({
        "event": "request_complete",
        "request_id": request_id,
        "method": request.method,
        "path": request.url.path,
        "status": response.status_code,
        "duration_ms": round((time.perf_counter() - started_at) * 1000, 2),
    }))
    return response


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Content-Security-Policy"] = "default-src 'self'"
    if ENVIRONMENT == "production":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    return response


@app.middleware("http")
async def audit_mutating_requests(request: Request, call_next):
    response = await call_next(request)
    if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        session_factory = getattr(request.app.state, "audit_session_factory", SessionLocal)
        db = session_factory()
        try:
            actor = getattr(request.state, "current_user", None)
            actor_id = getattr(request.state, "current_user_id", None)
            if actor_id is None and actor is not None:
                actor_id = getattr(actor, "id", None)
            db.add(AuditLog(
                actor_user_id=actor_id,
                action=f"{request.method} {request.url.path}",
                resource=request.url.path.split("/")[2] if len(request.url.path.split("/")) > 2 else "unknown",
                resource_id=request.path_params.get("id"),
                method=request.method,
                path=request.url.path,
                status_code=response.status_code,
            ))
            db.commit()
        except SQLAlchemyError:
            db.rollback()
            logger.exception("Failed to persist audit log for %s %s", request.method, request.url.path)
        finally:
            db.close()
    return response


# ============================================================
# API ROUTERS
# ============================================================

app.include_router(
    auth_router,
    prefix="/api"
)

app.include_router(
    patient_router,
    prefix="/api",
    tags=["Patients"],
    dependencies=[Depends(get_current_user)]
)

app.include_router(
    bills_router,
    prefix="/api",
    tags=["Billing"],
    dependencies=[Depends(get_current_user)]
)

app.include_router(
    payments_router,
    prefix="/api",
    tags=["Payments"],
    dependencies=[Depends(get_current_user)]
)

app.include_router(
    doctor_router,
    prefix="/api",
    tags=["Doctors"],
    dependencies=[Depends(get_current_user)]
)

app.include_router(
    appointment_router,
    prefix="/api",
    tags=["Appointments"],
    dependencies=[Depends(get_current_user)]
)

app.include_router(
    availability_router,
    prefix="/api",
    tags=["Doctor Availability"],
    dependencies=[Depends(get_current_user)]
)

app.include_router(
    triage_router,
    prefix="/api",
    tags=["Triage"],
    dependencies=[Depends(get_current_user)]
)

app.include_router(
    dashboard_router,
    prefix="/api",
    dependencies=[Depends(get_current_user)]
)

app.include_router(
    ai_router,
    prefix="/api",
    dependencies=[Depends(get_current_user)]
)

# ============================================================
# ROOT
# ============================================================

@app.get("/")
def root():
    return {
        "message": "Hospital Management AI API is running"
    }


# ============================================================
# HEALTH CHECK
# ============================================================

@app.get("/health")
def health_check():
    return {
        "status": "healthy"
    }


@app.get("/health/live")
def health_live():
    return {"status": "alive"}


@app.get("/health/ready")
def health_ready():
    db = SessionLocal()
    try:
        db.execute(text("SELECT 1"))
        database_ok = True
    except SQLAlchemyError:
        database_ok = False
    finally:
        db.close()
    ready = database_ok
    return {
        "status": "ready" if ready else "degraded",
        "database": "ready" if database_ok else "unavailable",
        "gemini": "configured" if GEMINI_API_KEY else "not_configured",
    }
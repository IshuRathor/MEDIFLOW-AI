from fastapi import FastAPI

from app.database.db import Base, engine

from app.api.patients import router as patient_router
from app.api.bills import router as bills_router
from app.api.payments import router as payments_router
from app.api.doctor import router as doctor_router
from app.api.appointment import router as appointment_router
from app.api.availability import router as availability_router

from app.models.finance import Bill, BillItem, Payment, Expense
from app.models.doctor import Doctor
from app.models.appointment import Appointment
from app.models.availability import DoctorAvailability
from app.api.triage import router as triage_router

from app.agents.main_agent import main_agent


# ============================================================
# FASTAPI APPLICATION
# ============================================================

app = FastAPI(
    title="Hospital Management AI API",
    description="Backend API for the AI-powered Hospital Management System",
    version="1.0.0"
)


# ============================================================
# DATABASE TABLE CREATION
# ============================================================

Base.metadata.create_all(bind=engine)


# ============================================================
# API ROUTERS
# ============================================================

app.include_router(
    patient_router,
    prefix="/api",
    tags=["Patients"]
)

app.include_router(
    bills_router,
    prefix="/api",
    tags=["Billing"]
)

app.include_router(
    payments_router,
    prefix="/api",
    tags=["Payments"]
)

app.include_router(
    doctor_router,
    prefix="/api",
    tags=["Doctors"]
)

app.include_router(
    appointment_router,
    prefix="/api",
    tags=["Appointments"]
)

app.include_router(
    availability_router,
    prefix="/api",
    tags=["Doctor Availability"]
)

app.include_router(
    triage_router,
    prefix="/api",
    tags=["Triage"]
)

# ============================================================
# MEDIFLOW AI CHAT
# ============================================================

@app.post("/api/ai/chat")
def chat_with_mediflow(user_query: str):
    response = main_agent(user_query)

    return response


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
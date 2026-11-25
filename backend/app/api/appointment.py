from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from sqlalchemy import update
from datetime import datetime, timedelta, timezone
from typing import Literal

from app.database.db import SessionLocal
from app.models.appointment import Appointment, ACTIVE_APPOINTMENT_STATUSES
from app.models.patient import Patient
from app.models.doctor import Doctor
from app.models.availability import DoctorAvailability
from app.schemas.scheduling import (
    AppointmentActionResponse,
    AppointmentCancellationResponse,
    AppointmentResponse
)
from app.core.security import get_current_user, get_linked_doctor
from app.models.user import User
from pydantic import BaseModel, Field
from app.api.availability import generate_slots, _datetime_naive
from app.services.cancellation import PENDING_CANCELLATION, ensure_can_cancel, ensure_no_cancellation, unchanged_appointment


router = APIRouter(
    prefix="/appointments",
    tags=["Appointments"]
)


class DeclineAppointmentRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=500)


class CancellationDecision(BaseModel):
    request_id: str = Field(min_length=1, max_length=64)
    reason: str | None = Field(default=None, max_length=500)


def _appointment_response(item: Appointment):
    return {
        "id": item.id,
        "patient_id": item.patient_id,
        "doctor_id": item.doctor_id,
        "appointment_date": item.appointment_date,
        "reason": item.reason,
        "status": item.status,
        "notes": item.notes,
        "decline_reason": item.decline_reason,
        "created_at": item.created_at,
    }


def get_db():
    db = SessionLocal()

    try:
        yield db
    finally:
        db.close()


# ============================================================
# CREATE APPOINTMENT
# ============================================================

@router.post("/", response_model=AppointmentActionResponse)
def create_appointment(
    patient_id: int,
    doctor_id: int,
    appointment_date: str,
    reason: str | None = None,
    notes: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role not in ("admin", "staff", "clinician", "patient"):
        raise HTTPException(status_code=403, detail="Appointment creation is restricted")
    if current_user.role == "patient":
        patient = db.query(Patient).filter(Patient.user_id == current_user.id).first()
        if not patient:
            raise HTTPException(status_code=403, detail="No patient profile is linked to this account")
        if patient_id not in (0, patient.id):
            raise HTTPException(status_code=403, detail="You can only book appointments for yourself")
        patient_id = patient.id
    else:
        patient = db.query(Patient).filter(Patient.id == patient_id).first()

    if not patient:
        raise HTTPException(
            status_code=404,
            detail="Patient not found"
        )
    if current_user.role == "patient" and patient.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="You can only book appointments for yourself")
    if current_user.role == "clinician":
        linked_doctor = get_linked_doctor(db, current_user)
        if doctor_id != linked_doctor.id:
            raise HTTPException(status_code=403, detail="You can only manage your own appointments")

    # --------------------------------------------------------
    # Check doctor
    # --------------------------------------------------------

    doctor = db.query(Doctor).filter(
        Doctor.id == doctor_id
    ).first()

    if not doctor:
        raise HTTPException(
            status_code=404,
            detail="Doctor not found"
        )

    # --------------------------------------------------------
    # Validate appointment date
    # --------------------------------------------------------

    try:
        appointment_datetime = datetime.fromisoformat(
            appointment_date
        )
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=(
                "Invalid appointment date format. "
                "Use YYYY-MM-DDTHH:MM:SS"
            )
        )

    if appointment_datetime.tzinfo is not None:
        appointment_datetime = appointment_datetime.astimezone(timezone.utc).replace(tzinfo=None)
    now = datetime.now()
    if appointment_datetime <= now:
        raise HTTPException(status_code=409, detail={"message": "Past dates and times cannot be booked.", "alternatives": []})

    locked_doctor = db.query(Doctor).filter(Doctor.id == doctor_id).with_for_update().first()
    if not locked_doctor:
        raise HTTPException(status_code=404, detail="Doctor not found")

    target_date = appointment_datetime.date()
    slot_result = generate_slots(db, doctor_id, target_date)
    duration = max(locked_doctor.appointment_duration_minutes or 30, 5)
    requested_start = appointment_datetime.replace(second=0, microsecond=0)
    requested_end = requested_start + timedelta(minutes=duration)

    matching_slot = next(
        (
            slot for slot in slot_result["slots"]
            if datetime.fromisoformat(slot["start"]) == requested_start
        ),
        None,
    )
    alternatives = [slot["start"] for slot in slot_result["slots"] if slot["status"] == "available"][:5]
    if not alternatives:
        alternatives = slot_result["alternatives"]
    if slot_result["blocked"]:
        raise HTTPException(status_code=409, detail={"message": "The doctor has blocked this date.", "alternatives": alternatives})
    if not matching_slot:
        raise HTTPException(status_code=409, detail={"message": "Doctor is not available at this time.", "alternatives": alternatives})
    if matching_slot["status"] != "available":
        raise HTTPException(status_code=409, detail={"message": "This appointment slot is already booked.", "alternatives": alternatives})

    active_appointments = db.query(Appointment).filter(
        Appointment.status.in_(ACTIVE_APPOINTMENT_STATUSES),
        Appointment.doctor_id == doctor_id,
    ).all()
    for existing in active_appointments:
        existing_start = _datetime_naive(existing.appointment_date)
        existing_duration = max(locked_doctor.appointment_duration_minutes or 30, 5)
        existing_end = existing_start + timedelta(minutes=existing_duration)
        if requested_start < existing_end and requested_end > existing_start:
            raise HTTPException(status_code=409, detail={"message": "This appointment slot is already booked.", "alternatives": alternatives})

    patient_conflict = db.query(Appointment).filter(
        Appointment.patient_id == patient_id,
        Appointment.status.in_(ACTIVE_APPOINTMENT_STATUSES),
    ).all()
    for existing in patient_conflict:
        existing_start = _datetime_naive(existing.appointment_date)
        existing_end = existing_start + timedelta(minutes=duration)
        if requested_start < existing_end and requested_end > existing_start:
            raise HTTPException(status_code=409, detail={"message": "You already have an overlapping appointment.", "alternatives": alternatives})

    # --------------------------------------------------------
    # CREATE APPOINTMENT
    # --------------------------------------------------------

    new_appointment = Appointment(
        patient_id=patient_id,
        doctor_id=doctor_id,
        appointment_date=appointment_datetime,
        reason=reason,
        notes=notes,
        status="Pending Doctor Approval" if current_user.role == "patient" else "Scheduled"
    )

    db.add(new_appointment)
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail={"message": "This appointment slot is already booked.", "alternatives": alternatives},
        ) from error
    db.refresh(new_appointment)

    return {
        "message": "Appointment request submitted and waiting for doctor approval" if current_user.role == "patient" else "Appointment created successfully",
        "appointment": {
            "id": new_appointment.id,
            "patient_id": new_appointment.patient_id,
            "doctor_id": new_appointment.doctor_id,
            "appointment_date": new_appointment.appointment_date,
            "reason": new_appointment.reason,
            "status": new_appointment.status,
            "notes": new_appointment.notes,
            "decline_reason": new_appointment.decline_reason,
            "created_at": new_appointment.created_at
        }
    }


# ============================================================
# GET ALL APPOINTMENTS
# ============================================================

@router.get("/", response_model=list[AppointmentResponse])
def get_appointments(
    status: str | None = Query(default=None, max_length=40),
    patient_id: int | None = Query(default=None, ge=1),
    doctor_id: int | None = Query(default=None, ge=1),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    order: str = Query(default="asc", pattern="^(asc|desc)$"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = db.query(Appointment)
    if current_user.role == "patient":
        owned_patient = db.query(Patient).filter(Patient.user_id == current_user.id).first()
        if not owned_patient:
            return []
        query = query.filter(Appointment.patient_id == owned_patient.id)
    if current_user.role == "clinician":
        linked_doctor = get_linked_doctor(db, current_user)
        query = query.filter(Appointment.doctor_id == linked_doctor.id)
    if status:
        query = query.filter(Appointment.status == status)
    if patient_id:
        query = query.filter(Appointment.patient_id == patient_id)
    if doctor_id:
        query = query.filter(Appointment.doctor_id == doctor_id)
    query = query.order_by(Appointment.appointment_date.asc() if order == "asc" else Appointment.appointment_date.desc())
    appointments = query.offset(offset).limit(limit).all()

    return [
        {
            "id": appointment.id,
            "patient_id": appointment.patient_id,
            "doctor_id": appointment.doctor_id,
            "appointment_date": appointment.appointment_date,
            "reason": appointment.reason,
            "status": appointment.status,
            "notes": appointment.notes,
            "decline_reason": appointment.decline_reason,
            "created_at": appointment.created_at
        }
        for appointment in appointments
    ]


# ============================================================
# GET APPOINTMENT BY ID
# ============================================================

@router.get("/{appointment_id}", response_model=AppointmentResponse)
def get_appointment(
    appointment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    appointment = db.query(Appointment).filter(
        Appointment.id == appointment_id
    ).first()

    if not appointment:
        raise HTTPException(
            status_code=404,
            detail="Appointment not found"
        )
    if current_user.role == "patient":
        owned_patient = db.query(Patient).filter(Patient.user_id == current_user.id).first()
        if not owned_patient or appointment.patient_id != owned_patient.id:
            raise HTTPException(status_code=403, detail="You can only access your own appointments")
    if current_user.role == "clinician":
        linked_doctor = get_linked_doctor(db, current_user)
        if appointment.doctor_id != linked_doctor.id:
            raise HTTPException(status_code=403, detail="You can only access your own appointments")

    return {
        "id": appointment.id,
        "patient_id": appointment.patient_id,
        "doctor_id": appointment.doctor_id,
        "appointment_date": appointment.appointment_date,
        "reason": appointment.reason,
        "status": appointment.status,
        "notes": appointment.notes,
        "decline_reason": appointment.decline_reason,
        "created_at": appointment.created_at
    }


# ============================================================
# UPDATE APPOINTMENT
# ============================================================

@router.put(
    "/{appointment_id}",
    response_model=AppointmentActionResponse
)
def update_appointment(
    appointment_id: int,
    appointment_date: str,
    status: Literal["Scheduled", "Completed", "Cancelled", "No-show", "Declined"],
    reason: str | None = None,
    notes: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    appointment = db.query(Appointment).filter(
        Appointment.id == appointment_id
    ).first()

    if not appointment:
        raise HTTPException(
            status_code=404,
            detail="Appointment not found"
        )
    if current_user.role == "patient":
        owned_patient = db.query(Patient).filter(Patient.user_id == current_user.id).first()
        if not owned_patient or appointment.patient_id != owned_patient.id:
            raise HTTPException(status_code=403, detail="You can only change your own appointments")
        raise HTTPException(status_code=403, detail="Patients cannot change appointment status directly")
    if current_user.role == "clinician":
        linked_doctor = get_linked_doctor(db, current_user)
        if appointment.doctor_id != linked_doctor.id:
            raise HTTPException(status_code=403, detail="You can only change your own appointments")
        if appointment.status == "Pending Doctor Approval":
            raise HTTPException(status_code=409, detail="Use the appointment request accept or decline action")
    ensure_no_cancellation(appointment)
    if status == "Cancelled":
        ensure_can_cancel(appointment)

    # --------------------------------------------------------
    # Validate appointment date
    # --------------------------------------------------------

    try:
        appointment_datetime = datetime.fromisoformat(
            appointment_date
        )
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=(
                "Invalid appointment date format. "
                "Use YYYY-MM-DDTHH:MM:SS"
            )
        )

    # --------------------------------------------------------
    # DOCTOR AVAILABILITY CHECK
    # --------------------------------------------------------

    if status == "Scheduled":

        day_name = appointment_datetime.strftime("%A")
        appointment_time = appointment_datetime.time()

        availability = db.query(
            DoctorAvailability
        ).filter(
            DoctorAvailability.doctor_id == appointment.doctor_id,
            DoctorAvailability.day_of_week == day_name,
            DoctorAvailability.is_available == True
        ).first()

        if not availability:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Doctor is not available on {day_name}."
                )
            )

        if not (
            availability.start_time
            <= appointment_time
            <= availability.end_time
        ):
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Doctor is available on {day_name} "
                    f"only between "
                    f"{availability.start_time.strftime('%H:%M:%S')} "
                    f"and "
                    f"{availability.end_time.strftime('%H:%M:%S')}."
                )
            )

        # ----------------------------------------------------
        # DOCTOR CONFLICT CHECK
        # ----------------------------------------------------

        doctor_conflict = db.query(Appointment).filter(
            Appointment.doctor_id == appointment.doctor_id,
            Appointment.appointment_date == appointment_datetime,
            Appointment.status.in_(ACTIVE_APPOINTMENT_STATUSES),
            Appointment.id != appointment_id
        ).first()

        if doctor_conflict:
            raise HTTPException(
                status_code=409,
                detail=(
                    "Doctor is already booked for this date and time."
                )
            )

        # ----------------------------------------------------
        # PATIENT CONFLICT CHECK
        # ----------------------------------------------------

        patient_conflict = db.query(Appointment).filter(
            Appointment.patient_id == appointment.patient_id,
            Appointment.appointment_date == appointment_datetime,
            Appointment.status.in_(ACTIVE_APPOINTMENT_STATUSES),
            Appointment.id != appointment_id
        ).first()

        if patient_conflict:
            raise HTTPException(
                status_code=409,
                detail=(
                    "Patient already has an appointment "
                    "at this date and time."
                )
            )

    # --------------------------------------------------------
    # UPDATE APPOINTMENT
    # --------------------------------------------------------

    changed = db.execute(
        update(Appointment).where(*unchanged_appointment(appointment)).values(
            appointment_date=appointment_datetime,
            status=status,
            reason=reason,
            notes=notes,
            decline_reason=appointment.decline_reason if status == "Declined" else None,
        )
    )
    if changed.rowcount != 1:
        raise HTTPException(status_code=409, detail="This appointment changed. Refresh and try again.")

    db.commit()
    db.refresh(appointment)

    return {
        "message": "Appointment updated successfully",
        "appointment": {
            "id": appointment.id,
            "patient_id": appointment.patient_id,
            "doctor_id": appointment.doctor_id,
            "appointment_date": appointment.appointment_date,
            "reason": appointment.reason,
            "status": appointment.status,
            "notes": appointment.notes,
            "decline_reason": appointment.decline_reason,
            "created_at": appointment.created_at
        }
    }


# ============================================================
# CANCEL APPOINTMENT
# ============================================================

@router.delete(
    "/{appointment_id}",
    response_model=AppointmentCancellationResponse
)
def cancel_appointment(
    appointment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role == "patient":
        raise HTTPException(status_code=403, detail="Use Ask MediFlow AI to request cancellation")
    appointment = db.query(Appointment).filter(
        Appointment.id == appointment_id
    ).first()

    if not appointment:
        raise HTTPException(
            status_code=404,
            detail="Appointment not found"
        )
    if current_user.role == "clinician":
        linked_doctor = get_linked_doctor(db, current_user)
        if appointment.doctor_id != linked_doctor.id:
            raise HTTPException(status_code=403, detail="You can only cancel your own appointments")

    ensure_can_cancel(appointment)
    changed = db.execute(
        update(Appointment).where(*unchanged_appointment(appointment)).values(status="Cancelled", decline_reason=None)
    )
    if changed.rowcount != 1:
        raise HTTPException(status_code=409, detail="This appointment changed. Refresh and try again.")

    db.commit()
    db.refresh(appointment)

    return {
        "message": "Appointment cancelled successfully",
        "appointment_id": appointment.id,
        "status": appointment.status
    }


@router.post("/{appointment_id}/cancellation/{decision}")
def decide_cancellation(
    appointment_id: int,
    decision: Literal["approve", "reject"],
    payload: CancellationDecision,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role not in ("admin", "clinician"):
        raise HTTPException(status_code=403, detail="Doctor or administrator access is required")
    appointment = db.get(Appointment, appointment_id)
    if not appointment:
        raise HTTPException(status_code=404, detail="Appointment not found")
    if current_user.role == "clinician" and appointment.doctor_id != get_linked_doctor(db, current_user).id:
        raise HTTPException(status_code=403, detail="You can only process your own cancellation requests")

    approved = decision == "approve"
    conditions = [
        Appointment.id == appointment.id,
        Appointment.doctor_id == appointment.doctor_id,
        Appointment.status == "Scheduled",
        Appointment.cancellation_request_id == payload.request_id,
        Appointment.cancellation_status == PENDING_CANCELLATION,
    ]
    if approved:
        conditions.append(Appointment.appointment_date > datetime.now())
    result_status = "Approved" if approved else "Rejected"
    changed = db.execute(
        update(Appointment).where(*conditions).values(
            status="Cancelled" if approved else "Scheduled",
            cancellation_status=result_status,
            cancellation_reason=None if approved else (payload.reason or "").strip() or None,
        ).execution_options(synchronize_session=False)
    )
    if changed.rowcount != 1:
        raise HTTPException(status_code=409, detail="The request was already processed, or the appointment time has passed")
    db.commit()
    return {"status": result_status}


def _owned_pending_appointment(db: Session, appointment_id: int, current_user: User):
    if current_user.role != "clinician":
        raise HTTPException(status_code=403, detail="Doctor access is required")
    doctor = get_linked_doctor(db, current_user)
    appointment = (
        db.query(Appointment)
        .filter(Appointment.id == appointment_id)
        .with_for_update()
        .first()
    )
    if not appointment:
        raise HTTPException(status_code=404, detail="Appointment request not found")
    if appointment.doctor_id != doctor.id:
        raise HTTPException(status_code=403, detail="You can only process your own appointment requests")
    if appointment.status != "Pending Doctor Approval":
        raise HTTPException(status_code=409, detail=f"Appointment request is already {appointment.status}")
    return appointment


@router.post("/{appointment_id}/accept", response_model=AppointmentActionResponse)
def accept_appointment_request(
    appointment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    appointment = _owned_pending_appointment(db, appointment_id, current_user)
    if _datetime_naive(appointment.appointment_date) <= datetime.now():
        raise HTTPException(status_code=409, detail="Appointment request has expired because its requested time has passed")
    doctor = get_linked_doctor(db, current_user)
    try:
        changed = db.execute(
            update(Appointment)
            .where(
                Appointment.id == appointment_id,
                Appointment.doctor_id == doctor.id,
                Appointment.status == "Pending Doctor Approval",
            )
            .values(status="Scheduled", decline_reason=None)
        )
        if changed.rowcount != 1:
            db.rollback()
            raise HTTPException(status_code=409, detail="Appointment request is already processed")
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(status_code=409, detail="The requested slot conflicts with another appointment") from error
    db.refresh(appointment)
    return {"message": "Appointment request accepted", "appointment": _appointment_response(appointment)}


@router.post("/{appointment_id}/decline", response_model=AppointmentActionResponse)
def decline_appointment_request(
    appointment_id: int,
    payload: DeclineAppointmentRequest | None = Body(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    appointment = _owned_pending_appointment(db, appointment_id, current_user)
    doctor = get_linked_doctor(db, current_user)
    changed = db.execute(
        update(Appointment)
        .where(
            Appointment.id == appointment_id,
            Appointment.doctor_id == doctor.id,
            Appointment.status == "Pending Doctor Approval",
        )
        .values(status="Declined", decline_reason=payload.reason.strip() if payload and payload.reason else None)
    )
    if changed.rowcount != 1:
        db.rollback()
        raise HTTPException(status_code=409, detail="Appointment request is already processed")
    db.commit()
    db.refresh(appointment)
    return {"message": "Appointment request declined", "appointment": _appointment_response(appointment)}

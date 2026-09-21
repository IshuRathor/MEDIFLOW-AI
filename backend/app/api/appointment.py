from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime

from app.database.db import SessionLocal
from app.models.appointment import Appointment
from app.models.patient import Patient
from app.models.doctor import Doctor
from app.models.availability import DoctorAvailability


router = APIRouter(
    prefix="/appointments",
    tags=["Appointments"]
)


def get_db():
    db = SessionLocal()

    try:
        yield db
    finally:
        db.close()


# ============================================================
# CREATE APPOINTMENT
# ============================================================

@router.post("/")
def create_appointment(
    patient_id: int,
    doctor_id: int,
    appointment_date: str,
    reason: str | None = None,
    notes: str | None = None,
    db: Session = Depends(get_db)
):
    # --------------------------------------------------------
    # Check patient
    # --------------------------------------------------------

    patient = db.query(Patient).filter(
        Patient.id == patient_id
    ).first()

    if not patient:
        raise HTTPException(
            status_code=404,
            detail="Patient not found"
        )

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

    # --------------------------------------------------------
    # DOCTOR AVAILABILITY CHECK
    # --------------------------------------------------------

    day_name = appointment_datetime.strftime("%A")
    appointment_time = appointment_datetime.time()

    availability = db.query(
        DoctorAvailability
    ).filter(
        DoctorAvailability.doctor_id == doctor_id,
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

    # --------------------------------------------------------
    # DOCTOR CONFLICT CHECK
    # --------------------------------------------------------

    doctor_conflict = db.query(Appointment).filter(
        Appointment.doctor_id == doctor_id,
        Appointment.appointment_date == appointment_datetime,
        Appointment.status == "Scheduled"
    ).first()

    if doctor_conflict:
        raise HTTPException(
            status_code=409,
            detail=(
                "Doctor is already booked for this date and time."
            )
        )

    # --------------------------------------------------------
    # PATIENT CONFLICT CHECK
    # --------------------------------------------------------

    patient_conflict = db.query(Appointment).filter(
        Appointment.patient_id == patient_id,
        Appointment.appointment_date == appointment_datetime,
        Appointment.status == "Scheduled"
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
    # CREATE APPOINTMENT
    # --------------------------------------------------------

    new_appointment = Appointment(
        patient_id=patient_id,
        doctor_id=doctor_id,
        appointment_date=appointment_datetime,
        reason=reason,
        notes=notes,
        status="Scheduled"
    )

    db.add(new_appointment)
    db.commit()
    db.refresh(new_appointment)

    return {
        "message": "Appointment created successfully",
        "appointment": {
            "id": new_appointment.id,
            "patient_id": new_appointment.patient_id,
            "doctor_id": new_appointment.doctor_id,
            "appointment_date": new_appointment.appointment_date,
            "reason": new_appointment.reason,
            "status": new_appointment.status,
            "notes": new_appointment.notes,
            "created_at": new_appointment.created_at
        }
    }


# ============================================================
# GET ALL APPOINTMENTS
# ============================================================

@router.get("/")
def get_appointments(
    db: Session = Depends(get_db)
):
    appointments = db.query(Appointment).all()

    return [
        {
            "id": appointment.id,
            "patient_id": appointment.patient_id,
            "doctor_id": appointment.doctor_id,
            "appointment_date": appointment.appointment_date,
            "reason": appointment.reason,
            "status": appointment.status,
            "notes": appointment.notes,
            "created_at": appointment.created_at
        }
        for appointment in appointments
    ]


# ============================================================
# GET APPOINTMENT BY ID
# ============================================================

@router.get("/{appointment_id}")
def get_appointment(
    appointment_id: int,
    db: Session = Depends(get_db)
):
    appointment = db.query(Appointment).filter(
        Appointment.id == appointment_id
    ).first()

    if not appointment:
        raise HTTPException(
            status_code=404,
            detail="Appointment not found"
        )

    return {
        "id": appointment.id,
        "patient_id": appointment.patient_id,
        "doctor_id": appointment.doctor_id,
        "appointment_date": appointment.appointment_date,
        "reason": appointment.reason,
        "status": appointment.status,
        "notes": appointment.notes,
        "created_at": appointment.created_at
    }


# ============================================================
# UPDATE APPOINTMENT
# ============================================================

@router.put("/{appointment_id}")
def update_appointment(
    appointment_id: int,
    appointment_date: str,
    status: str,
    reason: str | None = None,
    notes: str | None = None,
    db: Session = Depends(get_db)
):
    appointment = db.query(Appointment).filter(
        Appointment.id == appointment_id
    ).first()

    if not appointment:
        raise HTTPException(
            status_code=404,
            detail="Appointment not found"
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
            Appointment.status == "Scheduled",
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
            Appointment.status == "Scheduled",
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

    appointment.appointment_date = appointment_datetime
    appointment.status = status
    appointment.reason = reason
    appointment.notes = notes

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
            "created_at": appointment.created_at
        }
    }


# ============================================================
# CANCEL APPOINTMENT
# ============================================================

@router.delete("/{appointment_id}")
def cancel_appointment(
    appointment_id: int,
    db: Session = Depends(get_db)
):
    appointment = db.query(Appointment).filter(
        Appointment.id == appointment_id
    ).first()

    if not appointment:
        raise HTTPException(
            status_code=404,
            detail="Appointment not found"
        )

    appointment.status = "Cancelled"

    db.commit()
    db.refresh(appointment)

    return {
        "message": "Appointment cancelled successfully",
        "appointment_id": appointment.id,
        "status": appointment.status
    }
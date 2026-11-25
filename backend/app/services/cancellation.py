import re
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import or_, update
from sqlalchemy.orm import Session, joinedload

from app.models.appointment import Appointment
from app.models.patient import Patient


REQUEST_CANCELLATION = "request_appointment_cancellation"
PENDING_CANCELLATION = "Pending Doctor Approval"


def cancellation_intent(query: str) -> bool:
    return bool(re.search(
        r"\bcancel(?:lation|ling|ing)?\b|\b(?:don['’]t want to|do not want to|can['’]t|cannot|won['’]t|will not) attend\b",
        query,
        re.IGNORECASE,
    ) and re.search(r"\b(?:appointments?|bookings?|visits?)\b", query, re.IGNORECASE))


def owned_appointments(db: Session, user):
    return db.query(Appointment).join(Patient).filter(Patient.user_id == user.id)


def eligible_appointments(db: Session, user):
    return owned_appointments(db, user).filter(
        Appointment.status == "Scheduled",
        Appointment.appointment_date > datetime.now(),
        or_(Appointment.cancellation_status.is_(None), Appointment.cancellation_status == "Rejected"),
    )


def appointment_card(appointment):
    return {
        "id": appointment.id,
        "doctor_name": appointment.doctor.name,
        "specialization": appointment.doctor.specialization,
        "appointment_date": appointment.appointment_date.isoformat(),
        "status": appointment.status,
    }


def _doctor_name_words(name: str) -> list[str]:
    words = re.findall(r"[^\W_]+", name.casefold())
    return words[1:] if words and words[0] in ("dr", "doctor") else words


def cancellation_choices(db: Session, user, doctor_filter: str | None = None):
    appointments = eligible_appointments(db, user).options(joinedload(Appointment.doctor)).order_by(Appointment.appointment_date)
    cards = [appointment_card(item) for item in appointments]
    message = "Choose the appointment you want to cancel."
    if not cards:
        message = "You have no upcoming appointments eligible for cancellation."
    elif doctor_filter:
        words = _doctor_name_words(doctor_filter)
        matches = [card for card in cards if words and all(
            word in _doctor_name_words(card["doctor_name"]) for word in words
        )]
        if matches:
            cards = matches
            message = "Select the appointment with the correct date and time." if len(matches) > 1 else message
        else:
            message = "No eligible appointment matches that doctor. Choose from your upcoming appointments below."
    return {
        "status": "clarification_required" if cards else "completed",
        "message": message,
        "data": {"cancellation_options": cards, **({"cancellation_doctor_filter": doctor_filter} if doctor_filter else {})},
    }


def submit_cancellation(db: Session, user, approval):
    if user.role != "patient":
        raise HTTPException(status_code=403, detail="Patient access is required")
    parameters = approval.parameters_json
    appointment = owned_appointments(db, user).filter(Appointment.id == parameters["appointment_id"]).first()
    if not appointment:
        raise HTTPException(status_code=404, detail="Appointment not found")
    if appointment.appointment_date.isoformat() != parameters["appointment_date"]:
        raise HTTPException(status_code=409, detail="The appointment time changed. Select it again to confirm the new time.")
    changed = db.execute(
        update(Appointment).where(
            Appointment.id == appointment.id,
            Appointment.patient_id == appointment.patient_id,
            Appointment.appointment_date == appointment.appointment_date,
            Appointment.appointment_date > datetime.now(),
            Appointment.status == "Scheduled",
            Appointment.cancellation_request_id == parameters["previous_request_id"],
            or_(Appointment.cancellation_status.is_(None), Appointment.cancellation_status == "Rejected"),
        ).values(
            cancellation_request_id=approval.id,
            cancellation_status=PENDING_CANCELLATION,
            cancellation_requested_at=datetime.now(timezone.utc),
            cancellation_reason=None,
        ).execution_options(synchronize_session=False)
    )
    if changed.rowcount != 1:
        raise HTTPException(status_code=409, detail="This appointment is no longer eligible or already has a pending cancellation request")
    return {
        "message": "Cancellation request submitted. Pending Doctor Approval.",
        "status": PENDING_CANCELLATION,
    }


def unchanged_appointment(appointment):
    """Guard legacy status changes against an intervening cancellation request or decision."""
    return (
        Appointment.id == appointment.id,
        Appointment.appointment_date == appointment.appointment_date,
        Appointment.status == appointment.status,
        Appointment.cancellation_request_id == appointment.cancellation_request_id,
        Appointment.cancellation_status == appointment.cancellation_status,
    )


def ensure_no_cancellation(appointment):
    if appointment.cancellation_status in (PENDING_CANCELLATION, "Approved"):
        raise HTTPException(status_code=409, detail="This appointment has a pending or approved cancellation request")


def ensure_can_cancel(appointment):
    ensure_no_cancellation(appointment)
    start = appointment.appointment_date
    if start.tzinfo:
        start = start.astimezone(timezone.utc).replace(tzinfo=None)
    if appointment.status not in ("Scheduled", "Pending Doctor Approval") or start <= datetime.now():
        raise HTTPException(status_code=409, detail="Only upcoming active appointments can be cancelled")

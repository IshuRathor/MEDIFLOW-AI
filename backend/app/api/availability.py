from datetime import date, datetime, time, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.security import get_current_user, get_db, get_linked_doctor
from app.models.appointment import Appointment, ACTIVE_APPOINTMENT_STATUSES
from app.models.availability import DoctorAvailability
from app.models.doctor import Doctor
from app.models.user import User


router = APIRouter(prefix="/availability", tags=["Doctor Availability"])
VALID_DAYS = {"Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"}


def _time(value: str) -> time:
    try:
        return time.fromisoformat(value)
    except ValueError as error:
        raise HTTPException(status_code=400, detail="Invalid time format. Use HH:MM") from error


def _serialize(item: DoctorAvailability):
    return {
        "id": item.id,
        "doctor_id": item.doctor_id,
        "day_of_week": item.day_of_week,
        "specific_date": item.specific_date.isoformat() if item.specific_date else None,
        "start_time": item.start_time.isoformat(),
        "end_time": item.end_time.isoformat(),
        "is_available": item.is_available,
    }


def _datetime_naive(value: datetime) -> datetime:
    if value.tzinfo is not None:
        return value.replace(tzinfo=None)
    return value


def _rules_for_date(db: Session, doctor_id: int, target_date: date):
    exceptions = db.query(DoctorAvailability).filter(
        DoctorAvailability.doctor_id == doctor_id,
        DoctorAvailability.specific_date == target_date,
    ).all()
    if exceptions:
        blocked = [item for item in exceptions if not item.is_available]
        if blocked:
            return [], True
        return [item for item in exceptions if item.is_available], False

    weekday = target_date.strftime("%A")
    recurring = db.query(DoctorAvailability).filter(
        DoctorAvailability.doctor_id == doctor_id,
        DoctorAvailability.specific_date.is_(None),
        DoctorAvailability.day_of_week == weekday,
        DoctorAvailability.is_available == True,
    ).all()
    return recurring, False


def _slots_for_date(db: Session, doctor: Doctor, target_date: date):
    doctor_id = doctor.id
    rules, blocked = _rules_for_date(db, doctor_id, target_date)
    if blocked:
        return [], True

    duration = max(doctor.appointment_duration_minutes or 30, 5)
    appointments = db.query(Appointment).filter(
        Appointment.doctor_id == doctor_id,
        Appointment.status.in_(ACTIVE_APPOINTMENT_STATUSES),
    ).all()

    slots = []
    for rule in rules:
        cursor = datetime.combine(target_date, rule.start_time)
        range_end = datetime.combine(target_date, rule.end_time)
        while cursor + timedelta(minutes=duration) <= range_end:
            slot_end = cursor + timedelta(minutes=duration)
            overlap = False
            for appointment in appointments:
                appointment_start = _datetime_naive(appointment.appointment_date)
                appointment_end = appointment_start + timedelta(minutes=duration)
                if cursor < appointment_end and slot_end > appointment_start:
                    overlap = True
                    break
            slots.append({
                "start": cursor.isoformat(),
                "end": slot_end.isoformat(),
                "status": "booked" if overlap else "available",
            })
            cursor = slot_end

    return slots, False


def generate_slots(db: Session, doctor_id: int, target_date: date):
    doctor = db.query(Doctor).filter(Doctor.id == doctor_id).first()
    if not doctor:
        raise HTTPException(status_code=404, detail="Doctor not found")

    slots, blocked = _slots_for_date(db, doctor, target_date)
    alternatives = _next_available_dates(db, doctor, target_date) if blocked or not slots or all(
        slot["status"] == "booked" for slot in slots
    ) else []
    return {"blocked": blocked, "slots": slots, "alternatives": alternatives}


def _next_available_dates(db: Session, doctor: Doctor, target_date: date, limit: int = 7):
    alternatives = []
    for offset in range(1, 15):
        candidate = target_date + timedelta(days=offset)
        slots, blocked = _slots_for_date(db, doctor, candidate)
        if not blocked and any(slot["status"] == "available" for slot in slots):
            alternatives.append(candidate.isoformat())
            if len(alternatives) >= limit:
                break
    return alternatives


@router.post("/")
def create_availability(
    day_of_week: str,
    start_time: str,
    end_time: str,
    specific_date: date | None = None,
    is_available: bool = True,
    doctor_id: int | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role == "clinician":
        doctor = get_linked_doctor(db, current_user)
        resolved_doctor_id = doctor.id
    elif current_user.role in ("admin", "staff"):
        if doctor_id is None:
            raise HTTPException(status_code=400, detail="doctor_id is required")
        resolved_doctor_id = doctor_id
    else:
        raise HTTPException(status_code=403, detail="You cannot modify doctor availability")

    day_name = day_of_week.capitalize()
    if day_name not in VALID_DAYS:
        raise HTTPException(status_code=400, detail="Invalid day of week")
    if specific_date and specific_date.strftime("%A") != day_name:
        raise HTTPException(status_code=400, detail="specific_date does not match day_of_week")

    start = _time(start_time)
    end = _time(end_time)
    if start >= end:
        raise HTTPException(status_code=400, detail="Start time must be earlier than end time")
    if specific_date and specific_date < date.today():
        raise HTTPException(status_code=400, detail="Past dates cannot be configured")

    doctor = db.query(Doctor).filter(Doctor.id == resolved_doctor_id).first()
    if not doctor:
        raise HTTPException(status_code=404, detail="Doctor not found")

    item = DoctorAvailability(
        doctor_id=resolved_doctor_id,
        day_of_week=day_name,
        specific_date=specific_date,
        start_time=start,
        end_time=end,
        is_available=is_available,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return {"message": "Doctor availability saved successfully", "availability": _serialize(item)}


@router.get("/me")
def get_my_availability(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    doctor = get_linked_doctor(db, current_user)
    items = db.query(DoctorAvailability).filter(DoctorAvailability.doctor_id == doctor.id).order_by(
        DoctorAvailability.specific_date.asc().nulls_last(),
        DoctorAvailability.day_of_week.asc(),
        DoctorAvailability.start_time.asc(),
    ).all()
    return [_serialize(item) for item in items]


@router.get("/slots/{doctor_id}")
def get_available_slots(
    doctor_id: int,
    target_date: date = Query(..., alias="date"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if target_date < date.today():
        raise HTTPException(status_code=400, detail="Past dates cannot be booked")
    return generate_slots(db, doctor_id, target_date)


@router.get("/doctor/{doctor_id}")
def get_doctor_availability(
    doctor_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    items = db.query(DoctorAvailability).filter(DoctorAvailability.doctor_id == doctor_id).order_by(
        DoctorAvailability.specific_date.asc().nulls_last(),
        DoctorAvailability.day_of_week.asc(),
        DoctorAvailability.start_time.asc(),
    ).all()
    return [_serialize(item) for item in items]


@router.put("/{availability_id}")
def update_availability(
    availability_id: int,
    day_of_week: str,
    start_time: str,
    end_time: str,
    specific_date: date | None = None,
    is_available: bool = True,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    item = db.query(DoctorAvailability).filter(DoctorAvailability.id == availability_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Availability record not found")
    if current_user.role == "clinician":
        doctor = get_linked_doctor(db, current_user)
        if item.doctor_id != doctor.id:
            raise HTTPException(status_code=403, detail="You can only modify your own availability")
    elif current_user.role not in ("admin", "staff"):
        raise HTTPException(status_code=403, detail="You cannot modify doctor availability")

    day_name = day_of_week.capitalize()
    start = _time(start_time)
    end = _time(end_time)
    if day_name not in VALID_DAYS or start >= end:
        raise HTTPException(status_code=400, detail="Invalid availability range")
    if specific_date and specific_date.strftime("%A") != day_name:
        raise HTTPException(status_code=400, detail="specific_date does not match day_of_week")

    item.day_of_week = day_name
    item.specific_date = specific_date
    item.start_time = start
    item.end_time = end
    item.is_available = is_available
    db.commit()
    db.refresh(item)
    return {"message": "Doctor availability updated successfully", "availability": _serialize(item)}


@router.delete("/{availability_id}")
def delete_availability(
    availability_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    item = db.query(DoctorAvailability).filter(DoctorAvailability.id == availability_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Availability record not found")
    if current_user.role == "clinician":
        doctor = get_linked_doctor(db, current_user)
        if item.doctor_id != doctor.id:
            raise HTTPException(status_code=403, detail="You can only delete your own availability")
    elif current_user.role not in ("admin", "staff"):
        raise HTTPException(status_code=403, detail="You cannot modify doctor availability")
    db.delete(item)
    db.commit()
    return {"message": "Doctor availability deleted successfully", "availability_id": availability_id}

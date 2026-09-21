from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import time

from app.database.db import SessionLocal
from app.models.availability import DoctorAvailability
from app.models.doctor import Doctor


router = APIRouter(
    prefix="/availability",
    tags=["Doctor Availability"]
)


def get_db():
    db = SessionLocal()

    try:
        yield db
    finally:
        db.close()


# ============================================================
# VALID DAYS
# ============================================================

VALID_DAYS = {
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday"
}


# ============================================================
# CREATE DOCTOR AVAILABILITY
# ============================================================

@router.post("/")
def create_availability(
    doctor_id: int,
    day_of_week: str,
    start_time: str,
    end_time: str,
    is_available: bool = True,
    db: Session = Depends(get_db)
):
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
    # Validate day
    # --------------------------------------------------------

    day_of_week = day_of_week.capitalize()

    if day_of_week not in VALID_DAYS:
        raise HTTPException(
            status_code=400,
            detail=(
                "Invalid day. Use Monday, Tuesday, Wednesday, "
                "Thursday, Friday, Saturday or Sunday."
            )
        )

    # --------------------------------------------------------
    # Validate time
    # --------------------------------------------------------

    try:
        start = time.fromisoformat(start_time)
        end = time.fromisoformat(end_time)

    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Invalid time format. Use HH:MM:SS"
        )

    if start >= end:
        raise HTTPException(
            status_code=400,
            detail="Start time must be earlier than end time."
        )

    # --------------------------------------------------------
    # Check duplicate schedule
    # --------------------------------------------------------

    existing = db.query(DoctorAvailability).filter(
        DoctorAvailability.doctor_id == doctor_id,
        DoctorAvailability.day_of_week == day_of_week
    ).first()

    if existing:
        raise HTTPException(
            status_code=409,
            detail=(
                "Availability already exists for this doctor "
                "on this day."
            )
        )

    # --------------------------------------------------------
    # Create availability
    # --------------------------------------------------------

    availability = DoctorAvailability(
        doctor_id=doctor_id,
        day_of_week=day_of_week,
        start_time=start,
        end_time=end,
        is_available=is_available
    )

    db.add(availability)
    db.commit()
    db.refresh(availability)

    return {
        "message": "Doctor availability created successfully",
        "availability": {
            "id": availability.id,
            "doctor_id": availability.doctor_id,
            "day_of_week": availability.day_of_week,
            "start_time": availability.start_time,
            "end_time": availability.end_time,
            "is_available": availability.is_available
        }
    }


# ============================================================
# GET ALL AVAILABILITIES
# ============================================================

@router.get("/")
def get_all_availability(
    db: Session = Depends(get_db)
):
    availability = db.query(
        DoctorAvailability
    ).all()

    return [
        {
            "id": item.id,
            "doctor_id": item.doctor_id,
            "day_of_week": item.day_of_week,
            "start_time": item.start_time,
            "end_time": item.end_time,
            "is_available": item.is_available
        }
        for item in availability
    ]


# ============================================================
# GET AVAILABILITY BY DOCTOR
# ============================================================

@router.get("/doctor/{doctor_id}")
def get_doctor_availability(
    doctor_id: int,
    db: Session = Depends(get_db)
):
    doctor = db.query(Doctor).filter(
        Doctor.id == doctor_id
    ).first()

    if not doctor:
        raise HTTPException(
            status_code=404,
            detail="Doctor not found"
        )

    availability = db.query(
        DoctorAvailability
    ).filter(
        DoctorAvailability.doctor_id == doctor_id
    ).all()

    return [
        {
            "id": item.id,
            "doctor_id": item.doctor_id,
            "day_of_week": item.day_of_week,
            "start_time": item.start_time,
            "end_time": item.end_time,
            "is_available": item.is_available
        }
        for item in availability
    ]


# ============================================================
# GET AVAILABILITY BY ID
# ============================================================

@router.get("/{availability_id}")
def get_availability(
    availability_id: int,
    db: Session = Depends(get_db)
):
    availability = db.query(
        DoctorAvailability
    ).filter(
        DoctorAvailability.id == availability_id
    ).first()

    if not availability:
        raise HTTPException(
            status_code=404,
            detail="Availability record not found"
        )

    return {
        "id": availability.id,
        "doctor_id": availability.doctor_id,
        "day_of_week": availability.day_of_week,
        "start_time": availability.start_time,
        "end_time": availability.end_time,
        "is_available": availability.is_available
    }


# ============================================================
# UPDATE AVAILABILITY
# ============================================================

@router.put("/{availability_id}")
def update_availability(
    availability_id: int,
    day_of_week: str,
    start_time: str,
    end_time: str,
    is_available: bool = True,
    db: Session = Depends(get_db)
):
    availability = db.query(
        DoctorAvailability
    ).filter(
        DoctorAvailability.id == availability_id
    ).first()

    if not availability:
        raise HTTPException(
            status_code=404,
            detail="Availability record not found"
        )

    # --------------------------------------------------------
    # Validate day
    # --------------------------------------------------------

    day_of_week = day_of_week.capitalize()

    if day_of_week not in VALID_DAYS:
        raise HTTPException(
            status_code=400,
            detail="Invalid day of week."
        )

    # --------------------------------------------------------
    # Validate time
    # --------------------------------------------------------

    try:
        start = time.fromisoformat(start_time)
        end = time.fromisoformat(end_time)

    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Invalid time format. Use HH:MM:SS"
        )

    if start >= end:
        raise HTTPException(
            status_code=400,
            detail="Start time must be earlier than end time."
        )

    # --------------------------------------------------------
    # Check duplicate day
    # --------------------------------------------------------

    existing = db.query(
        DoctorAvailability
    ).filter(
        DoctorAvailability.doctor_id == availability.doctor_id,
        DoctorAvailability.day_of_week == day_of_week,
        DoctorAvailability.id != availability_id
    ).first()

    if existing:
        raise HTTPException(
            status_code=409,
            detail=(
                "Availability already exists for this doctor "
                "on this day."
            )
        )

    # --------------------------------------------------------
    # Update
    # --------------------------------------------------------

    availability.day_of_week = day_of_week
    availability.start_time = start
    availability.end_time = end
    availability.is_available = is_available

    db.commit()
    db.refresh(availability)

    return {
        "message": "Doctor availability updated successfully",
        "availability": {
            "id": availability.id,
            "doctor_id": availability.doctor_id,
            "day_of_week": availability.day_of_week,
            "start_time": availability.start_time,
            "end_time": availability.end_time,
            "is_available": availability.is_available
        }
    }


# ============================================================
# DELETE AVAILABILITY
# ============================================================

@router.delete("/{availability_id}")
def delete_availability(
    availability_id: int,
    db: Session = Depends(get_db)
):
    availability = db.query(
        DoctorAvailability
    ).filter(
        DoctorAvailability.id == availability_id
    ).first()

    if not availability:
        raise HTTPException(
            status_code=404,
            detail="Availability record not found"
        )

    db.delete(availability)
    db.commit()

    return {
        "message": "Doctor availability deleted successfully",
        "availability_id": availability_id
    }
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database.db import SessionLocal
from app.models.doctor import Doctor
from app.schemas.doctor import DoctorCreate, DoctorResponse


router = APIRouter(
    prefix="/doctors",
    tags=["Doctors"]
)


def get_db():
    db = SessionLocal()

    try:
        yield db
    finally:
        db.close()


# CREATE DOCTOR
@router.post("/", response_model=DoctorResponse)
def create_doctor(
    doctor: DoctorCreate,
    db: Session = Depends(get_db)
):
    existing_doctor = db.query(Doctor).filter(
        Doctor.email == doctor.email
    ).first()

    if existing_doctor:
        raise HTTPException(
            status_code=400,
            detail="Doctor with this email already exists"
        )

    new_doctor = Doctor(
        name=doctor.name,
        specialization=doctor.specialization,
        phone=doctor.phone,
        email=doctor.email,
        department=doctor.department,
        experience_years=doctor.experience_years
    )

    db.add(new_doctor)
    db.commit()
    db.refresh(new_doctor)

    return new_doctor


# GET ALL DOCTORS
@router.get("/", response_model=list[DoctorResponse])
def get_doctors(
    db: Session = Depends(get_db)
):
    return db.query(Doctor).all()


# GET DOCTOR BY ID
@router.get("/{doctor_id}", response_model=DoctorResponse)
def get_doctor(
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

    return doctor


# UPDATE DOCTOR
@router.put("/{doctor_id}", response_model=DoctorResponse)
def update_doctor(
    doctor_id: int,
    doctor_data: DoctorCreate,
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

    existing_doctor = db.query(Doctor).filter(
        Doctor.email == doctor_data.email,
        Doctor.id != doctor_id
    ).first()

    if existing_doctor:
        raise HTTPException(
            status_code=400,
            detail="Another doctor already uses this email"
        )

    doctor.name = doctor_data.name
    doctor.specialization = doctor_data.specialization
    doctor.phone = doctor_data.phone
    doctor.email = doctor_data.email
    doctor.department = doctor_data.department
    doctor.experience_years = doctor_data.experience_years

    db.commit()
    db.refresh(doctor)

    return doctor


# DELETE DOCTOR
@router.delete("/{doctor_id}")
def delete_doctor(
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

    db.delete(doctor)
    db.commit()

    return {
        "message": "Doctor deleted successfully"
    }
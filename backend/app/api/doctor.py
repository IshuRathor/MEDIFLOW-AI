from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database.db import SessionLocal
from app.core.security import require_roles
from app.models.doctor import Doctor
from app.schemas.doctor import DoctorCreate, DoctorResponse
from sqlalchemy.exc import IntegrityError


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
@router.post(
    "/",
    response_model=DoctorResponse,
    dependencies=[Depends(require_roles("admin", "staff"))]
)
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
    try:
        db.commit()
        db.refresh(new_doctor)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Doctor with this email already exists")

    return new_doctor


# GET ALL DOCTORS
@router.get("/", response_model=list[DoctorResponse])
def get_doctors(
    search: str | None = Query(default=None, max_length=120),
    specialization: str | None = Query(default=None, max_length=120),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    sort: str = Query(default="created_at"),
    order: str = Query(default="desc", pattern="^(asc|desc)$"),
    db: Session = Depends(get_db)
):
    allowed_sort_fields = {"name": Doctor.name, "created_at": Doctor.created_at, "experience_years": Doctor.experience_years}
    sort_column = allowed_sort_fields.get(sort, Doctor.created_at)
    query = db.query(Doctor)
    if search:
        query = query.filter(Doctor.name.ilike(f"%{search}%") | Doctor.email.ilike(f"%{search}%"))
    if specialization:
        query = query.filter(Doctor.specialization.ilike(f"%{specialization}%"))
    query = query.order_by(sort_column.asc() if order == "asc" else sort_column.desc())
    return query.offset(offset).limit(limit).all()


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
@router.put(
    "/{doctor_id}",
    response_model=DoctorResponse,
    dependencies=[Depends(require_roles("admin", "staff"))]
)
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
@router.delete(
    "/{doctor_id}",
    dependencies=[Depends(require_roles("admin"))]
)
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
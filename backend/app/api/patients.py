from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database.db import SessionLocal
from app.core.security import require_roles
from app.models.patient import Patient
from app.schemas.patient import PatientCreate, PatientResponse
from app.core.security import get_current_user
from app.models.user import User
from sqlalchemy.exc import IntegrityError


router = APIRouter(
    prefix="/patients",
    tags=["Patients"]
)


def get_db():
    db = SessionLocal()

    try:
        yield db
    finally:
        db.close()


# CREATE PATIENT
@router.post(
    "/",
    response_model=PatientResponse,
    dependencies=[Depends(require_roles("admin", "staff", "clinician"))]
)
def create_patient(
    patient: PatientCreate,
    db: Session = Depends(get_db)
):
    new_patient = Patient(
        name=patient.name,
        age=patient.age,
        gender=patient.gender,
        phone=patient.phone,
        email=patient.email
    )

    db.add(new_patient)
    try:
        db.commit()
        db.refresh(new_patient)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Email is already registered")

    return new_patient


# GET ALL PATIENTS
@router.get("/", response_model=list[PatientResponse])
def get_patients(
    search: str | None = Query(default=None, max_length=120),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    sort: str = Query(default="created_at"),
    order: str = Query(default="desc", pattern="^(asc|desc)$"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    allowed_sort_fields = {"name": Patient.name, "created_at": Patient.created_at, "age": Patient.age}
    sort_column = allowed_sort_fields.get(sort, Patient.created_at)
    if search:
        query = db.query(Patient).filter(
            Patient.name.ilike(f"%{search}%") | Patient.email.ilike(f"%{search}%")
        )
    else:
        query = db.query(Patient)
        if current_user.role == "patient":
            owned_patient = db.query(Patient).filter(Patient.user_id == current_user.id).first()
            if not owned_patient:
                return []
            query = query.filter(Patient.id == owned_patient.id)
    query = query.order_by(sort_column.asc() if order == "asc" else sort_column.desc())
    return query.offset(offset).limit(limit).all()


# GET PATIENT BY ID
@router.get("/{patient_id}", response_model=PatientResponse)
def get_patient(
    patient_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    patient = db.query(Patient).filter(
        Patient.id == patient_id
    ).first()

    if not patient:
        raise HTTPException(
            status_code=404,
            detail="Patient not found"
        )
    if current_user.role == "patient" and patient.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="You can only access your own patient record")

    return patient


# UPDATE PATIENT
@router.put(
    "/{patient_id}",
    response_model=PatientResponse,
    dependencies=[Depends(require_roles("admin", "staff", "clinician"))]
)
def update_patient(
    patient_id: int,
    patient_data: PatientCreate,
    db: Session = Depends(get_db)
):
    patient = db.query(Patient).filter(
        Patient.id == patient_id
    ).first()

    if not patient:
        raise HTTPException(
            status_code=404,
            detail="Patient not found"
        )

    patient.name = patient_data.name
    patient.age = patient_data.age
    patient.gender = patient_data.gender
    patient.phone = patient_data.phone
    patient.email = patient_data.email

    db.commit()
    db.refresh(patient)

    return patient


# DELETE PATIENT
@router.delete(
    "/{patient_id}",
    dependencies=[Depends(require_roles("admin", "staff"))]
)
def delete_patient(
    patient_id: int,
    db: Session = Depends(get_db)
):
    patient = db.query(Patient).filter(
        Patient.id == patient_id
    ).first()

    if not patient:
        raise HTTPException(
            status_code=404,
            detail="Patient not found"
        )

    db.delete(patient)
    db.commit()

    return {
        "message": "Patient deleted successfully"
    }
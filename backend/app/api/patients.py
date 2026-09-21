from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database.db import SessionLocal
from app.models.patient import Patient
from app.schemas.patient import PatientCreate, PatientResponse


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
@router.post("/", response_model=PatientResponse)
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
    db.commit()
    db.refresh(new_patient)

    return new_patient


# GET ALL PATIENTS
@router.get("/", response_model=list[PatientResponse])
def get_patients(db: Session = Depends(get_db)):
    return db.query(Patient).all()


# GET PATIENT BY ID
@router.get("/{patient_id}", response_model=PatientResponse)
def get_patient(
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

    return patient


# UPDATE PATIENT
@router.put("/{patient_id}", response_model=PatientResponse)
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
@router.delete("/{patient_id}")
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
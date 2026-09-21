from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database.db import SessionLocal
from app.models.finance import Bill
from app.models.patient import Patient


router = APIRouter(
    prefix="/bills",
    tags=["Billing"]
)


def get_db():
    db = SessionLocal()

    try:
        yield db
    finally:
        db.close()


# ============================================================
# CREATE BILL
# ============================================================

@router.post("/")
def create_bill(
    patient_id: int,
    bill_number: str,
    total_amount: float,
    status: str = "Pending",
    db: Session = Depends(get_db)
):
    # Check patient exists
    patient = db.query(Patient).filter(
        Patient.id == patient_id
    ).first()

    if not patient:
        raise HTTPException(
            status_code=404,
            detail="Patient not found"
        )

    # Check duplicate bill number
    existing_bill = db.query(Bill).filter(
        Bill.bill_number == bill_number
    ).first()

    if existing_bill:
        raise HTTPException(
            status_code=400,
            detail="Bill number already exists"
        )

    new_bill = Bill(
        patient_id=patient_id,
        bill_number=bill_number,
        total_amount=total_amount,
        status=status
    )

    db.add(new_bill)
    db.commit()
    db.refresh(new_bill)

    return {
        "message": "Bill created successfully",
        "bill": {
            "id": new_bill.id,
            "patient_id": new_bill.patient_id,
            "bill_number": new_bill.bill_number,
            "total_amount": float(new_bill.total_amount),
            "status": new_bill.status,
            "created_at": new_bill.created_at
        }
    }


# ============================================================
# GET ALL BILLS
# ============================================================

@router.get("/")
def get_bills(
    db: Session = Depends(get_db)
):
    bills = db.query(Bill).all()

    return [
        {
            "id": bill.id,
            "patient_id": bill.patient_id,
            "bill_number": bill.bill_number,
            "total_amount": float(bill.total_amount),
            "status": bill.status,
            "created_at": bill.created_at
        }
        for bill in bills
    ]


# ============================================================
# GET BILL BY ID
# ============================================================

@router.get("/{bill_id}")
def get_bill(
    bill_id: int,
    db: Session = Depends(get_db)
):
    bill = db.query(Bill).filter(
        Bill.id == bill_id
    ).first()

    if not bill:
        raise HTTPException(
            status_code=404,
            detail="Bill not found"
        )

    return {
        "id": bill.id,
        "patient_id": bill.patient_id,
        "bill_number": bill.bill_number,
        "total_amount": float(bill.total_amount),
        "status": bill.status,
        "created_at": bill.created_at
    }


# ============================================================
# UPDATE BILL
# ============================================================

@router.put("/{bill_id}")
def update_bill(
    bill_id: int,
    total_amount: float,
    status: str,
    db: Session = Depends(get_db)
):
    bill = db.query(Bill).filter(
        Bill.id == bill_id
    ).first()

    if not bill:
        raise HTTPException(
            status_code=404,
            detail="Bill not found"
        )

    bill.total_amount = total_amount
    bill.status = status

    db.commit()
    db.refresh(bill)

    return {
        "message": "Bill updated successfully",
        "bill": {
            "id": bill.id,
            "patient_id": bill.patient_id,
            "bill_number": bill.bill_number,
            "total_amount": float(bill.total_amount),
            "status": bill.status,
            "created_at": bill.created_at
        }
    }


# ============================================================
# DELETE BILL
# ============================================================

@router.delete("/{bill_id}")
def delete_bill(
    bill_id: int,
    db: Session = Depends(get_db)
):
    bill = db.query(Bill).filter(
        Bill.id == bill_id
    ).first()

    if not bill:
        raise HTTPException(
            status_code=404,
            detail="Bill not found"
        )

    db.delete(bill)
    db.commit()

    return {
        "message": "Bill deleted successfully"
    }
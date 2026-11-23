from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database.db import SessionLocal
from app.core.security import require_roles
from app.models.finance import Bill
from app.models.patient import Patient
from app.schemas.finance import BillActionResponse, BillResponse, DeletionResponse
from app.core.security import get_current_user
from app.models.user import User


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

@router.post(
    "/",
    response_model=BillActionResponse,
    dependencies=[Depends(require_roles("admin", "staff"))]
)
def create_bill(
    patient_id: int,
    bill_number: str,
    total_amount: float = Query(..., gt=0),
    status: Literal["Pending", "Partially Paid", "Paid", "Cancelled"] = "Pending",
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

@router.get("/", response_model=list[BillResponse])
def get_bills(
    search: str | None = Query(default=None, max_length=120),
    status: str | None = Query(default=None, max_length=40),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    order: str = Query(default="desc", pattern="^(asc|desc)$"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = db.query(Bill)
    if current_user.role == "patient":
        owned_patient = db.query(Patient).filter(Patient.user_id == current_user.id).first()
        if not owned_patient:
            return []
        query = query.filter(Bill.patient_id == owned_patient.id)
    if search:
        query = query.filter(Bill.bill_number.ilike(f"%{search}%"))
    if status:
        query = query.filter(Bill.status == status)
    query = query.order_by(Bill.created_at.asc() if order == "asc" else Bill.created_at.desc())
    bills = query.offset(offset).limit(limit).all()

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

@router.get("/{bill_id}", response_model=BillResponse)
def get_bill(
    bill_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    bill = db.query(Bill).filter(
        Bill.id == bill_id
    ).first()

    if not bill:
        raise HTTPException(
            status_code=404,
            detail="Bill not found"
        )
    if current_user.role == "patient":
        owned_patient = db.query(Patient).filter(Patient.user_id == current_user.id).first()
        if not owned_patient or bill.patient_id != owned_patient.id:
            raise HTTPException(status_code=403, detail="You can only access your own bills")

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

@router.put(
    "/{bill_id}",
    response_model=BillActionResponse,
    dependencies=[Depends(require_roles("admin", "staff"))]
)
def update_bill(
    bill_id: int,
    total_amount: float = Query(..., gt=0),
    status: Literal["Pending", "Partially Paid", "Paid", "Cancelled"] = Query(...),
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

@router.delete(
    "/{bill_id}",
    response_model=DeletionResponse,
    dependencies=[Depends(require_roles("admin"))]
)
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
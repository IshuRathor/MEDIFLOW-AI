from typing import Literal
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database.db import SessionLocal
from app.core.security import require_roles
from app.models.finance import Payment, Bill
from app.schemas.finance import (
    DeletionResponse,
    PaymentActionResponse,
    PaymentResponse
)
from app.core.security import get_current_user
from app.models.patient import Patient
from app.models.user import User


router = APIRouter(
    prefix="/payments",
    tags=["Payments"]
)


def get_db():
    db = SessionLocal()

    try:
        yield db
    finally:
        db.close()


# ============================================================
# CREATE PAYMENT
# ============================================================

@router.post(
    "/",
    response_model=PaymentActionResponse,
    dependencies=[Depends(require_roles("admin", "staff"))]
)
def create_payment(
    bill_id: int,
    amount: float = Query(..., gt=0),
    payment_method: Literal["Cash", "Card", "Bank Transfer", "Insurance", "Other"] = Query(...),
    payment_status: Literal["Pending", "Completed", "Failed", "Refunded"] = "Completed",
    transaction_reference: str | None = None,
    db: Session = Depends(get_db)
):
    # Check bill exists
    bill = db.query(Bill).filter(
        Bill.id == bill_id
    ).first()

    if not bill:
        raise HTTPException(
            status_code=404,
            detail="Bill not found"
        )

    if bill.status == "Cancelled":
        raise HTTPException(
            status_code=409,
            detail="Payments cannot be recorded against a cancelled bill"
        )

    completed_total = sum(
        (payment.amount for payment in bill.payments if payment.payment_status == "Completed"),
        Decimal("0")
    )
    if payment_status == "Completed" and Decimal(str(amount)) > bill.total_amount - completed_total:
        raise HTTPException(
            status_code=409,
            detail="Payment exceeds the bill's outstanding balance"
        )

    # Check duplicate transaction reference
    if transaction_reference:
        existing_payment = db.query(Payment).filter(
            Payment.transaction_reference == transaction_reference
        ).first()

        if existing_payment:
            raise HTTPException(
                status_code=400,
                detail="Transaction reference already exists"
            )

    # Create payment
    new_payment = Payment(
        bill_id=bill_id,
        amount=amount,
        payment_method=payment_method,
        payment_status=payment_status,
        transaction_reference=transaction_reference
    )

    db.add(new_payment)
    db.commit()
    db.refresh(new_payment)

    # Automatically update bill status
    if payment_status == "Completed":

        total_paid = (
            db.query(Payment)
            .filter(
                Payment.bill_id == bill_id,
                Payment.payment_status == "Completed"
            )
            .all()
        )

        paid_amount = sum(
            float(payment.amount)
            for payment in total_paid
        )

        if paid_amount >= float(bill.total_amount):
            bill.status = "Paid"

        elif paid_amount > 0:
            bill.status = "Partially Paid"

        db.commit()
        db.refresh(bill)

    return {
        "message": "Payment created successfully",
        "payment": {
            "id": new_payment.id,
            "bill_id": new_payment.bill_id,
            "amount": float(new_payment.amount),
            "payment_method": new_payment.payment_method,
            "payment_status": new_payment.payment_status,
            "transaction_reference": new_payment.transaction_reference,
            "paid_at": new_payment.paid_at
        },
        "bill_status": bill.status
    }


# ============================================================
# GET ALL PAYMENTS
# ============================================================

@router.get("/", response_model=list[PaymentResponse])
def get_payments(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role == "clinician":
        raise HTTPException(status_code=403, detail="Finance record access is restricted")
    if current_user.role not in ("patient", "staff", "admin"):
        raise HTTPException(status_code=403, detail="Finance record access is restricted")

    query = db.query(Payment)
    if current_user.role == "patient":
        owned_patient = db.query(Patient).filter(Patient.user_id == current_user.id).first()
        if not owned_patient:
            return []
        query = query.join(Bill, Payment.bill_id == Bill.id).filter(Bill.patient_id == owned_patient.id)
    payments = query.all()

    return [
        {
            "id": payment.id,
            "bill_id": payment.bill_id,
            "amount": float(payment.amount),
            "payment_method": payment.payment_method,
            "payment_status": payment.payment_status,
            "transaction_reference": payment.transaction_reference,
            "paid_at": payment.paid_at
        }
        for payment in payments
    ]


# ============================================================
# GET PAYMENT BY ID
# ============================================================

@router.get("/{payment_id}", response_model=PaymentResponse)
def get_payment(
    payment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role == "clinician":
        raise HTTPException(status_code=403, detail="Finance record access is restricted")
    if current_user.role not in ("patient", "staff", "admin"):
        raise HTTPException(status_code=403, detail="Finance record access is restricted")

    query = db.query(Payment).filter(Payment.id == payment_id)
    if current_user.role == "patient":
        owned_patient = db.query(Patient).filter(Patient.user_id == current_user.id).first()
        if not owned_patient:
            raise HTTPException(status_code=404, detail="Payment not found")
        query = query.join(Bill, Payment.bill_id == Bill.id).filter(Bill.patient_id == owned_patient.id)
    payment = query.first()

    if not payment:
        raise HTTPException(
            status_code=404,
            detail="Payment not found"
        )
    return {
        "id": payment.id,
        "bill_id": payment.bill_id,
        "amount": float(payment.amount),
        "payment_method": payment.payment_method,
        "payment_status": payment.payment_status,
        "transaction_reference": payment.transaction_reference,
        "paid_at": payment.paid_at
    }


# ============================================================
# DELETE PAYMENT
# ============================================================

@router.delete(
    "/{payment_id}",
    response_model=DeletionResponse,
    dependencies=[Depends(require_roles("admin"))]
)
def delete_payment(
    payment_id: int,
    db: Session = Depends(get_db)
):
    payment = db.query(Payment).filter(
        Payment.id == payment_id
    ).first()

    if not payment:
        raise HTTPException(
            status_code=404,
            detail="Payment not found"
        )

    db.delete(payment)
    db.commit()

    return {
        "message": "Payment deleted successfully"
    }

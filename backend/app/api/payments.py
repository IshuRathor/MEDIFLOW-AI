from typing import Literal
from decimal import Decimal
from secrets import token_urlsafe

from sqlalchemy.exc import IntegrityError

from app.ai.orchestrator import _create_pending_approval
from app.services.billing import BILLING_REVIEW_PREFIX, record_payment, review_payment

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database.db import SessionLocal
from app.core.security import require_roles
from app.models.finance import Payment, Bill
from app.schemas.finance import (
    DeletionResponse,
    PaymentActionResponse,
    PaymentResponse, PaymentDraft, FinanceReview
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
    response_model=PaymentActionResponse | FinanceReview,
    dependencies=[Depends(require_roles("admin", "staff"))]
)
def create_payment(
    bill_id: int | None = None,
    amount: Decimal | None = Query(default=None, gt=0),
    payment_method: Literal["Cash", "Card", "Bank Transfer", "Insurance", "Other"] | None = None,
    payment_status: Literal["Pending", "Completed", "Failed", "Refunded"] = "Completed",
    transaction_reference: str | None = None,
    draft: PaymentDraft | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if draft is not None:
        review_payment(db, draft.bill_id, draft.amount, draft.transaction_reference)
        approval = _create_pending_approval(db, current_user, BILLING_REVIEW_PREFIX + token_urlsafe(18), "record_payment", draft.model_dump(mode="json"))
        return {"approval_id": approval.id, "total_amount": draft.amount}
    if bill_id is None or amount is None or payment_method is None:
        raise HTTPException(422, "Bill, amount and payment method are required")
    try:
        bill, payment = record_payment(db, bill_id, amount, payment_method, transaction_reference, payment_status)
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(409, "Payment conflicts with an existing record") from error
    return {
        "message": "Payment created successfully",
        "payment": PaymentResponse.model_validate(payment, from_attributes=True),
        "bill_status": bill.status,
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
            "transaction_reference": payment.transaction_reference if current_user.role != "patient" else None,
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
        "transaction_reference": payment.transaction_reference if current_user.role != "patient" else None,
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

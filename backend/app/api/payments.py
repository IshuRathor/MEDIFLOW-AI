from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database.db import SessionLocal
from app.models.finance import Payment, Bill


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

@router.post("/")
def create_payment(
    bill_id: int,
    amount: float,
    payment_method: str,
    payment_status: str = "Completed",
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

@router.get("/")
def get_payments(
    db: Session = Depends(get_db)
):
    payments = db.query(Payment).all()

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

@router.get("/{payment_id}")
def get_payment(
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

@router.delete("/{payment_id}")
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
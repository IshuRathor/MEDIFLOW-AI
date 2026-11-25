from decimal import Decimal

from fastapi import HTTPException
from pydantic import TypeAdapter, ValidationError
from sqlalchemy import func, update

from app.models.finance import Bill, BillItem, Payment
from app.models.patient import Patient
from app.schemas.finance import BillDraft, PositiveMoney, PaymentMethod
from app.services.finance_analytics import bill_balances, recorded_total

BILLING_REVIEW_PREFIX = "billing-review:"


def valid_amount(value):
    try:
        return TypeAdapter(PositiveMoney).validate_python(value)
    except ValidationError as error:
        raise HTTPException(400, "Enter a positive INR amount with at most two decimal places") from error


def calculate_bill(db, patient_id, bill_number, items=None, total_amount=None):
    if not db.get(Patient, patient_id):
        raise HTTPException(404, "Patient not found")
    if db.query(Bill.id).filter(Bill.bill_number == bill_number).first():
        raise HTTPException(409, "Bill number already exists")
    lines = []
    if items is not None:
        draft = BillDraft(patient_id=patient_id, bill_number=bill_number, items=items)
        lines = [
            BillItem(description=line.description, quantity=line.quantity,
                     unit_price=line.unit_price, amount=line.unit_price * line.quantity)
            for line in draft.items
        ]
        total_amount = sum((line.amount for line in lines), Decimal("0"))
    return valid_amount(total_amount), lines


def generate_bill(db, patient_id, bill_number, items=None, total_amount=None, status="Pending"):
    amount, lines = calculate_bill(db, patient_id, bill_number, items, total_amount)
    bill = Bill(patient_id=patient_id, bill_number=bill_number, total_amount=amount, status=status, items=lines)
    db.add(bill)
    db.flush()
    return bill


def completed_payment_total(db, bill_id):
    return db.query(func.sum(Payment.amount)).filter(
        Payment.bill_id == bill_id, Payment.payment_status == "Completed",
    ).scalar() or Decimal("0")


def review_payment(db, bill_id, amount, reference=None, status="Completed"):
    amount = valid_amount(amount)
    bill = db.get(Bill, bill_id)
    if not bill:
        raise HTTPException(404, "Bill not found")
    if bill.status == "Cancelled":
        raise HTTPException(409, "Payments cannot be recorded against a cancelled bill")
    if reference and db.query(Payment.id).filter(Payment.transaction_reference == reference).first():
        raise HTTPException(400, "Transaction reference already exists")
    paid = completed_payment_total(db, bill_id)
    if status == "Completed" and amount > bill.total_amount - paid:
        raise HTTPException(409, "Payment exceeds the bill's outstanding balance")
    return bill, amount, paid


def record_payment(db, bill_id, amount, method, reference=None, status="Completed"):
    try:
        method = TypeAdapter(PaymentMethod).validate_python(method)
    except ValidationError as error:
        raise HTTPException(400, "Invalid payment method") from error
    # Acquire a write lock before reading the balance on PostgreSQL and SQLite.
    db.execute(update(Bill).where(Bill.id == bill_id).values(status=Bill.status))
    bill, amount, paid = review_payment(db, bill_id, amount, reference, status)
    payment = Payment(bill_id=bill_id, amount=amount, payment_method=method,
                      transaction_reference=reference, payment_status=status)
    db.add(payment)
    if status == "Completed":
        bill.status = "Paid" if paid + amount >= bill.total_amount else "Partially Paid"
    db.flush()
    return bill, payment


def bill_summary(bill, paid):
    outstanding = Decimal("0") if bill.status == "Cancelled" else max(bill.total_amount - paid, Decimal("0"))
    status = bill.status if bill.status == "Cancelled" else (
        "Paid" if outstanding == 0 else "Partially Paid" if paid else "Pending"
    )
    return {
        "id": bill.id, "patient_id": bill.patient_id, "patient_name": bill.patient.name,
        "bill_number": bill.bill_number, "total_amount": bill.total_amount,
        "status": status, "created_at": bill.created_at, "amount_paid": paid,
        "outstanding": outstanding,
    }


def billing_overview(db, *, patient_id=None, recent=False):
    bills = db.query(Bill)
    if patient_id is not None:
        bills = bills.filter(Bill.patient_id == patient_id)
    balances = bill_balances(db, patient_id=patient_id)
    count, billed = bills.with_entities(func.count(Bill.id), func.sum(Bill.total_amount)).one()
    return {
        "generated": count, "billed": billed or Decimal("0"),
        "collected": recorded_total(db, patient_id=patient_id),
        "outstanding": balances["outstanding"], "unpaid": balances["unpaid"],
        "partial": balances["partial"], "paid": balances["count"] - balances["unpaid"] - balances["partial"],
        "recent": [
            {"reference": bill.bill_number, "date": bill.created_at, "amount": bill.total_amount}
            for bill in bills.order_by(Bill.created_at.desc(), Bill.id.desc()).limit(5)
        ] if recent else [],
    }

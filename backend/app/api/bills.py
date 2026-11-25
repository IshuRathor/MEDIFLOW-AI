from typing import Literal
from decimal import Decimal
from secrets import token_urlsafe

from sqlalchemy import case, func, or_, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload, selectinload

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database.db import SessionLocal
from app.core.security import require_roles
from app.ai.orchestrator import _create_pending_approval
from app.models.finance import Bill, Payment
from app.services.billing import BILLING_REVIEW_PREFIX, bill_summary, calculate_bill, completed_payment_total, generate_bill, valid_amount
from app.models.patient import Patient
from app.schemas.finance import BillActionResponse, BillDetail, BillDraft, BillResponse, DeletionResponse, FinanceReview
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
    response_model=BillActionResponse | FinanceReview,
    dependencies=[Depends(require_roles("admin", "staff"))]
)
def create_bill(
    patient_id: int | None = None,
    bill_number: str | None = None,
    total_amount: Decimal | None = Query(default=None, gt=0),
    status: Literal["Pending", "Partially Paid", "Paid", "Cancelled"] = "Pending",
    draft: BillDraft | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if draft is not None:
        amount, _ = calculate_bill(db, draft.patient_id, draft.bill_number, draft.items)
        approval = _create_pending_approval(db, current_user, BILLING_REVIEW_PREFIX + token_urlsafe(18), "generate_bill", draft.model_dump(mode="json"))
        return {"approval_id": approval.id, "total_amount": amount}
    if patient_id is None or not bill_number or total_amount is None:
        raise HTTPException(422, "Patient, bill reference and amount are required")
    try:
        bill = generate_bill(db, patient_id, bill_number, total_amount=total_amount, status=status)
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(409, "Bill number already exists") from error
    return {"message": "Bill created successfully", "bill": bill_summary(bill, Decimal("0"))}


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
    if current_user.role == "clinician":
        raise HTTPException(status_code=403, detail="Finance record access is restricted")
    if current_user.role not in ("patient", "staff", "admin"):
        raise HTTPException(status_code=403, detail="Finance record access is restricted")

    query = db.query(Bill)
    if current_user.role == "patient":
        owned_patient = db.query(Patient).filter(Patient.user_id == current_user.id).first()
        if not owned_patient:
            return []
        query = query.filter(Bill.patient_id == owned_patient.id)
    paid_totals = db.query(Payment.bill_id, func.sum(Payment.amount).label("paid")).filter(
        Payment.payment_status == "Completed",
    ).group_by(Payment.bill_id).subquery()
    paid = func.coalesce(paid_totals.c.paid, 0)
    query = query.outerjoin(paid_totals, Bill.id == paid_totals.c.bill_id).options(joinedload(Bill.patient))
    if search:
        query = query.join(Patient, Bill.patient_id == Patient.id).filter(or_(
            Bill.bill_number.ilike(f"%{search}%"), Patient.name.ilike(f"%{search}%"),
        ))
    if status:
        calculated = case(
            (Bill.status == "Cancelled", "Cancelled"),
            (Bill.total_amount <= paid, "Paid"),
            (paid > 0, "Partially Paid"),
            else_="Pending",
        )
        query = query.filter(calculated == status)
    query = query.order_by(
        Bill.created_at.asc() if order == "asc" else Bill.created_at.desc(),
        Bill.id.asc() if order == "asc" else Bill.id.desc(),
    )
    return [bill_summary(bill, amount) for bill, amount in query.add_columns(paid).offset(offset).limit(limit)]


# ============================================================
# GET BILL BY ID
# ============================================================

@router.get("/{bill_id}", response_model=BillDetail)
def get_bill(
    bill_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role == "clinician":
        raise HTTPException(status_code=403, detail="Finance record access is restricted")
    if current_user.role not in ("patient", "staff", "admin"):
        raise HTTPException(status_code=403, detail="Finance record access is restricted")

    query = db.query(Bill).filter(Bill.id == bill_id)
    if current_user.role == "patient":
        owned_patient = db.query(Patient).filter(Patient.user_id == current_user.id).first()
        if not owned_patient:
            raise HTTPException(status_code=404, detail="Bill not found")
        query = query.filter(Bill.patient_id == owned_patient.id)
    bill = query.options(joinedload(Bill.patient), selectinload(Bill.items), selectinload(Bill.payments)).first()

    if not bill:
        raise HTTPException(
            status_code=404,
            detail="Bill not found"
        )
    return {
        **bill_summary(bill, completed_payment_total(db, bill.id)),
        "items": [
            {"description": item.description, "quantity": item.quantity, "unit_price": item.unit_price, "amount": item.amount}
            for item in sorted(bill.items, key=lambda item: item.id)
        ],
        "payments": [
            {"amount": payment.amount, "payment_method": payment.payment_method,
             "payment_status": payment.payment_status, "paid_at": payment.paid_at}
            for payment in sorted(bill.payments, key=lambda payment: (payment.paid_at, payment.id), reverse=True)
        ],
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
    total_amount: Decimal = Query(..., gt=0),
    status: Literal["Pending", "Partially Paid", "Paid", "Cancelled"] = Query(...),
    db: Session = Depends(get_db)
):
    db.execute(update(Bill).where(Bill.id == bill_id).values(status=Bill.status))
    bill = db.query(Bill).filter(
        Bill.id == bill_id
    ).first()

    if not bill:
        raise HTTPException(
            status_code=404,
            detail="Bill not found"
        )

    total_amount = valid_amount(total_amount)
    if bill.items and total_amount != bill.total_amount:
        raise HTTPException(409, "An itemized bill total must match its line items")
    paid = completed_payment_total(db, bill.id)
    if total_amount < paid:
        raise HTTPException(409, "Bill total cannot be below completed payments")
    bill.total_amount = total_amount
    bill.status = status

    db.commit()
    db.refresh(bill)

    return {
        "message": "Bill updated successfully",
        "bill": bill_summary(bill, paid)
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

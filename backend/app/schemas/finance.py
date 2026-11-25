from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

Money = Annotated[Decimal, Field(ge=0, max_digits=12, decimal_places=2)]
PositiveMoney = Annotated[Decimal, Field(gt=0, max_digits=12, decimal_places=2)]
PaymentMethod = Literal["Cash", "Card", "Bank Transfer", "Insurance", "Other"]
Reference = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]


class BillLine(BaseModel):
    description: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=250)]
    quantity: int = Field(strict=True, gt=0, le=100000)
    unit_price: Money


class BillDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")
    patient_id: int = Field(gt=0)
    bill_number: Reference
    items: list[BillLine] = Field(min_length=1, max_length=50)


class PaymentDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")
    bill_id: int = Field(gt=0)
    amount: PositiveMoney
    payment_method: PaymentMethod
    transaction_reference: Reference


class FinanceReview(BaseModel):
    approval_id: str
    total_amount: Decimal


BillStatus = Literal[
    "Pending",
    "Partially Paid",
    "Paid",
    "Cancelled"
]

PaymentStatus = Literal[
    "Pending",
    "Completed",
    "Failed",
    "Refunded"
]


class BillResponse(BaseModel):
    id: int
    patient_id: int
    bill_number: str
    total_amount: Decimal
    status: BillStatus
    created_at: datetime
    patient_name: str | None = None
    amount_paid: Decimal = Decimal("0")
    outstanding: Decimal = Decimal("0")


class BillActionResponse(BaseModel):
    message: str
    bill: BillResponse


class PaymentResponse(BaseModel):
    id: int
    bill_id: int
    amount: Decimal
    payment_method: str
    payment_status: PaymentStatus
    transaction_reference: str | None = None
    paid_at: datetime


class PaymentActionResponse(BaseModel):
    message: str
    payment: PaymentResponse
    bill_status: BillStatus


class BillLineResponse(BillLine):
    amount: Decimal


class BillPayment(BaseModel):
    amount: Decimal
    payment_method: str
    payment_status: PaymentStatus
    paid_at: datetime


class BillDetail(BillResponse):
    items: list[BillLineResponse]
    payments: list[BillPayment]


class DeletionResponse(BaseModel):
    message: str

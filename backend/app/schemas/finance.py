from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel


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


class DeletionResponse(BaseModel):
    message: str
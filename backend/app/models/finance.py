from sqlalchemy import (
    Column,
    Integer,
    String,
    Numeric,
    DateTime,
    Date,
    ForeignKey
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database.db import Base


# ============================================================
# BILL
# ============================================================

class Bill(Base):
    __tablename__ = "bills"

    id = Column(Integer, primary_key=True, index=True)

    patient_id = Column(
        Integer,
        ForeignKey("patients.id"),
        nullable=False,
        index=True
    )

    bill_number = Column(
        String,
        unique=True,
        nullable=False,
        index=True
    )

    total_amount = Column(
        Numeric(12, 2),
        nullable=False,
        default=0
    )

    status = Column(
        String,
        nullable=False,
        default="Pending"
    )

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now()
    )

    # Relationship with Patient
    patient = relationship("Patient")

    # Relationship with Bill Items
    items = relationship(
        "BillItem",
        back_populates="bill",
        cascade="all, delete-orphan"
    )

    # Relationship with Payments
    payments = relationship(
        "Payment",
        back_populates="bill",
        cascade="all, delete-orphan"
    )


# ============================================================
# BILL ITEM
# ============================================================

class BillItem(Base):
    __tablename__ = "bill_items"

    id = Column(Integer, primary_key=True, index=True)

    bill_id = Column(
        Integer,
        ForeignKey("bills.id"),
        nullable=False,
        index=True
    )

    description = Column(
        String,
        nullable=False
    )

    quantity = Column(
        Integer,
        nullable=False,
        default=1
    )

    unit_price = Column(
        Numeric(12, 2),
        nullable=False
    )

    amount = Column(
        Numeric(12, 2),
        nullable=False
    )

    # Relationship with Bill
    bill = relationship(
        "Bill",
        back_populates="items"
    )


# ============================================================
# PAYMENT
# ============================================================

class Payment(Base):
    __tablename__ = "payments"

    id = Column(Integer, primary_key=True, index=True)

    bill_id = Column(
        Integer,
        ForeignKey("bills.id"),
        nullable=False,
        index=True
    )

    amount = Column(
        Numeric(12, 2),
        nullable=False
    )

    payment_method = Column(
        String,
        nullable=False
    )

    payment_status = Column(
        String,
        nullable=False,
        default="Completed"
    )

    transaction_reference = Column(
        String,
        nullable=True,
        unique=True
    )

    paid_at = Column(
        DateTime(timezone=True),
        server_default=func.now()
    )

    # Relationship with Bill
    bill = relationship(
        "Bill",
        back_populates="payments"
    )


# ============================================================
# EXPENSE
# ============================================================

class Expense(Base):
    __tablename__ = "expenses"

    id = Column(Integer, primary_key=True, index=True)

    description = Column(
        String,
        nullable=False
    )

    category = Column(
        String,
        nullable=False
    )

    amount = Column(
        Numeric(12, 2),
        nullable=False
    )

    payment_method = Column(
        String,
        nullable=False
    )

    expense_date = Column(
        Date,
        nullable=False
    )

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now()
    )
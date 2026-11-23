from sqlalchemy import CheckConstraint, Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database.db import Base


class Patient(Base):
    __tablename__ = "patients"

    __table_args__ = (
        CheckConstraint("age IS NULL OR age BETWEEN 0 AND 130", name="ck_patient_age_valid"),
    )

    id = Column(Integer, primary_key=True, index=True)

    name = Column(String, nullable=False)
    age = Column(Integer)
    gender = Column(String)
    phone = Column(String)
    email = Column(String, unique=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), unique=True, nullable=True, index=True)
    user = relationship("User", back_populates="patient")

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now()
    )
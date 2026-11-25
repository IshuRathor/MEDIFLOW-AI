from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String, text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database.db import Base


ACTIVE_APPOINTMENT_STATUSES = ("Pending Doctor Approval", "Scheduled")


class Appointment(Base):
    __tablename__ = "appointments"

    __table_args__ = (
        Index(
            "uq_active_doctor_slot",
            "doctor_id",
            "appointment_date",
            unique=True,
            sqlite_where=text("status IN ('Pending Doctor Approval', 'Scheduled')"),
            postgresql_where=text("status IN ('Pending Doctor Approval', 'Scheduled')")
        ),
        Index(
            "uq_active_patient_slot",
            "patient_id",
            "appointment_date",
            unique=True,
            sqlite_where=text("status IN ('Pending Doctor Approval', 'Scheduled')"),
            postgresql_where=text("status IN ('Pending Doctor Approval', 'Scheduled')")
        )
    )

    id = Column(Integer, primary_key=True, index=True)

    patient_id = Column(
        Integer,
        ForeignKey("patients.id"),
        nullable=False,
        index=True
    )

    doctor_id = Column(
        Integer,
        ForeignKey("doctors.id"),
        nullable=False,
        index=True
    )

    appointment_date = Column(
        DateTime(timezone=True),
        nullable=False
    )

    reason = Column(String, nullable=True)

    status = Column(
        String,
        nullable=False,
        default="Scheduled"
    )

    notes = Column(String, nullable=True)

    decline_reason = Column(String, nullable=True)

    cancellation_request_id = Column(String(64), nullable=True)
    cancellation_status = Column(String(32), nullable=True)
    cancellation_requested_at = Column(DateTime(timezone=True), nullable=True)
    cancellation_reason = Column(String(500), nullable=True)

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now()
    )

    patient = relationship("Patient")
    doctor = relationship("Doctor")

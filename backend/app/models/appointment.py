from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String, text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database.db import Base


class Appointment(Base):
    __tablename__ = "appointments"

    __table_args__ = (
        Index(
            "uq_scheduled_doctor_slot",
            "doctor_id",
            "appointment_date",
            unique=True,
            sqlite_where=text("status = 'Scheduled'"),
            postgresql_where=text("status = 'Scheduled'")
        ),
        Index(
            "uq_scheduled_patient_slot",
            "patient_id",
            "appointment_date",
            unique=True,
            sqlite_where=text("status = 'Scheduled'"),
            postgresql_where=text("status = 'Scheduled'")
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

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now()
    )

    patient = relationship("Patient")
    doctor = relationship("Doctor")
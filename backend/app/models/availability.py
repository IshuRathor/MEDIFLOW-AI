from sqlalchemy import (
    Column,
    Integer,
    String,
    Time,
    Boolean,
    ForeignKey
)

from sqlalchemy.orm import relationship

from app.database.db import Base


class DoctorAvailability(Base):
    __tablename__ = "doctor_availability"

    id = Column(
        Integer,
        primary_key=True,
        index=True
    )

    doctor_id = Column(
        Integer,
        ForeignKey("doctors.id"),
        nullable=False,
        index=True
    )

    day_of_week = Column(
        String,
        nullable=False
    )

    start_time = Column(
        Time,
        nullable=False
    )

    end_time = Column(
        Time,
        nullable=False
    )

    is_available = Column(
        Boolean,
        default=True,
        nullable=False
    )

    doctor = relationship(
        "Doctor"
    )
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from app.database.db import Base


class Doctor(Base):
    __tablename__ = "doctors"

    id = Column(Integer, primary_key=True, index=True)

    name = Column(String, nullable=False)
    specialization = Column(String, nullable=False)
    phone = Column(String)
    email = Column(String, unique=True, index=True)
    department = Column(String)
    experience_years = Column(Integer, default=0)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), unique=True, nullable=True, index=True)
    appointment_duration_minutes = Column(Integer, nullable=False, default=30)

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now()
    )
    user = relationship("User", back_populates="doctor", uselist=False)
from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.sql import func

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

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now()
    )
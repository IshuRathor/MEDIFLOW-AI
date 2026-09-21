from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.sql import func
from app.database.db import Base


class Patient(Base):
    __tablename__ = "patients"

    id = Column(Integer, primary_key=True, index=True)

    name = Column(String, nullable=False)
    age = Column(Integer)
    gender = Column(String)
    phone = Column(String)
    email = Column(String, unique=True, index=True)

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now()
    )
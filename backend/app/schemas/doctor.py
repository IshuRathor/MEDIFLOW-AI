from pydantic import BaseModel, EmailStr
from datetime import datetime
from typing import Optional


class DoctorCreate(BaseModel):
    name: str
    specialization: str
    phone: Optional[str] = None
    email: EmailStr
    department: Optional[str] = None
    experience_years: int = 0
    appointment_duration_minutes: int = 30


class DoctorResponse(DoctorCreate):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True
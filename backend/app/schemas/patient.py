from pydantic import BaseModel, EmailStr
from datetime import datetime
from typing import Optional


class PatientCreate(BaseModel):
    name: str
    age: int
    gender: Optional[str] = None
    phone: Optional[str] = None
    email: EmailStr


class PatientResponse(PatientCreate):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True
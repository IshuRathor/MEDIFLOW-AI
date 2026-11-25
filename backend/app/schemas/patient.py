from pydantic import BaseModel, EmailStr
from datetime import datetime
from typing import Optional


class PatientCreate(BaseModel):
    name: str
    age: int
    gender: Optional[str] = None
    phone: Optional[str] = None
    email: EmailStr


class PatientResponse(BaseModel):
    id: int
    name: str
    age: Optional[int] = None
    gender: Optional[str] = None
    phone: Optional[str] = None
    email: EmailStr | None = None
    user_id: int | None = None
    created_at: datetime

    class Config:
        from_attributes = True

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator


class RegisterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    full_name: str = Field(..., min_length=2, max_length=120)
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)


class PatientRegisterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    full_name: str = Field(..., min_length=2, max_length=120)
    email: EmailStr
    phone: str = Field(default="", max_length=30)
    password: str = Field(..., min_length=8, max_length=128)
    confirm_password: str = Field(..., min_length=8, max_length=128)

    @model_validator(mode="after")
    def passwords_match(self):
        if self.password != self.confirm_password:
            raise ValueError("Passwords do not match")
        return self


class PublicRegisterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    full_name: str = Field(..., min_length=2, max_length=120)
    email: EmailStr
    phone: str = Field(default="", max_length=30)
    password: str = Field(..., min_length=8, max_length=128)
    confirm_password: str = Field(default="", min_length=0, max_length=128)
    role: Literal["patient", "clinician", "staff"] | None = None
    specialization: str | None = Field(default=None, min_length=2, max_length=120)
    department: str | None = Field(default=None, max_length=120)
    experience_years: int = Field(default=0, ge=0, le=80)

    @model_validator(mode="after")
    def validate_registration(self):
        if self.role is None and "role" in self.model_fields_set:
            raise ValueError("Select a supported account role")
        if self.confirm_password and self.password != self.confirm_password:
            raise ValueError("Passwords do not match")
        if self.role is not None and len(self.phone.strip()) < 7:
            raise ValueError("Phone number is required")
        if self.role == "clinician" and not self.specialization:
            raise ValueError("Specialization is required for doctor registration")
        return self


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=1, max_length=128)
    role: Literal["admin", "staff", "clinician", "patient"] = "admin"


class UserResponse(BaseModel):
    id: int
    full_name: str
    email: EmailStr
    role: Literal["admin", "staff", "clinician", "patient"]
    is_active: bool
    approval_status: str = "approved"
    created_at: datetime

    class Config:
        from_attributes = True


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


class CreateUserRequest(BaseModel):
    full_name: str = Field(..., min_length=2, max_length=120)
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)
    role: Literal["staff", "clinician", "patient"]
    patient_id: int | None = Field(default=None, ge=1)

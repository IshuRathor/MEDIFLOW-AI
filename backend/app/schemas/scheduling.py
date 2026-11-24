from datetime import date, datetime, time
from typing import Literal

from pydantic import BaseModel


AppointmentStatus = Literal[
    "Pending Doctor Approval",
    "Scheduled",
    "Declined",
    "Completed",
    "Cancelled",
    "No-show"
]


class AppointmentResponse(BaseModel):
    id: int
    patient_id: int
    doctor_id: int
    appointment_date: datetime
    reason: str | None = None
    status: AppointmentStatus
    notes: str | None = None
    decline_reason: str | None = None
    created_at: datetime


class AppointmentActionResponse(BaseModel):
    message: str
    appointment: AppointmentResponse


class AppointmentCancellationResponse(BaseModel):
    message: str
    appointment_id: int
    status: Literal["Cancelled"]


class AvailabilityResponse(BaseModel):
    id: int
    doctor_id: int
    day_of_week: str
    specific_date: date | None = None
    start_time: time
    end_time: time
    is_available: bool


class AvailabilityActionResponse(BaseModel):
    message: str
    availability: AvailabilityResponse


class AvailabilityDeletionResponse(BaseModel):
    message: str
    availability_id: int

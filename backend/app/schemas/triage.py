from pydantic import BaseModel, Field
from typing import Literal


class TriageRequest(BaseModel):
    symptoms: str = Field(
        ...,
        min_length=3,
        max_length=500,
        description="Patient symptoms"
    )


class TriageDoctor(BaseModel):
    id: int
    name: str
    specialization: str
    department: str | None
    experience_years: int | None
    availability: Literal["available", "no_slots", "unverified"]
    upcoming_slots: list[str] = Field(default_factory=list)
    matching_explanation: str


class TriageResponse(BaseModel):
    urgency: Literal[
        "Low",
        "Medium",
        "High",
        "Emergency"
    ]

    recommended_department: str

    symptoms_summary: str

    recommended_action: str
    recommended_doctors: list[TriageDoctor] = Field(default_factory=list)
    availability_window_days: int | None = None

    disclaimer: str = (
        "This is an AI-assisted triage recommendation "
        "and not a medical diagnosis."
    )
    safety_notice: str = (
        "If symptoms are severe, rapidly worsening, or life-threatening, "
        "call local emergency services or seek immediate medical care."
    )

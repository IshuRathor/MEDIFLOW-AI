from pydantic import BaseModel, Field
from typing import Literal


class TriageRequest(BaseModel):
    symptoms: str = Field(
        ...,
        min_length=3,
        description="Patient symptoms"
    )


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

    disclaimer: str = (
        "This is an AI-assisted triage recommendation "
        "and not a medical diagnosis."
    )
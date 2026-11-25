from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.schemas.finance_analytics import FinanceReport


class ChatRequest(BaseModel):
    query: str = Field(..., min_length=3, max_length=2000)
    conversation_id: str | None = Field(default=None, max_length=64)
    doctor_patient_id: int | None = Field(default=None, gt=0)


class AITraceItem(BaseModel):
    tool: str
    status: Literal["success", "error", "skipped", "approval_required"]
    duration_ms: float


class AIChatResponse(BaseModel):
    conversation_id: str
    agent: str
    status: Literal["completed", "clarification_required", "approval_required", "error"]
    message: str
    data: dict = Field(default_factory=dict)
    trace: list[AITraceItem] = Field(default_factory=list)
    approval_id: str | None = None

    @field_validator("data")
    @classmethod
    def validate_finance_report(cls, value):
        if "finance_report" in value:
            report = FinanceReport.model_validate(value["finance_report"])
            return {**value, "finance_report": report.model_dump(mode="json")}
        return value


class ApprovalResponse(BaseModel):
    approval_id: str
    status: Literal["pending", "approved", "rejected", "expired", "executed"]
    action: str
    parameters: dict
    result: dict | None = None

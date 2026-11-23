from typing import Literal

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    query: str = Field(..., min_length=3, max_length=2000)
    conversation_id: str | None = Field(default=None, max_length=64)


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


class ApprovalResponse(BaseModel):
    approval_id: str
    status: Literal["pending", "approved", "rejected", "expired", "executed"]
    action: str
    parameters: dict
    result: dict | None = None

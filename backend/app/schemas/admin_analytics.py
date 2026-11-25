from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.finance_analytics import FinanceChart, FinanceMetric


class OperationalQueue(BaseModel):
    title: str
    source: str
    status: str
    count: int = Field(ge=0)
    oldest_at: datetime | None
    oldest_age_hours: int | None = Field(ge=0)


class AdminReport(BaseModel):
    title: str
    timezone: Literal["Asia/Kolkata"] = "Asia/Kolkata"
    start_date: date | None = None
    end_date: date
    cutoff: datetime
    metrics: list[FinanceMetric] = Field(default_factory=list)
    charts: list[FinanceChart] = Field(default_factory=list)
    queues: list[OperationalQueue] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)

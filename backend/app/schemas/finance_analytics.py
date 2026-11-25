from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class FinanceSeries(BaseModel):
    label: str
    values: list[Decimal]


class FinanceChart(BaseModel):
    title: str
    kind: Literal["line", "bar"]
    labels: list[str] = Field(max_length=100)
    series: list[FinanceSeries] = Field(min_length=1, max_length=4)
    has_activity: bool
    unit: Literal["INR", "count"] = "INR"

    @model_validator(mode="after")
    def check_alignment(self):
        if any(len(series.values) != len(self.labels) for series in self.series):
            raise ValueError("Each series must supply a value for every label")
        if self.unit == "count" and any(
            value < 0 or value != value.to_integral_value()
            for series in self.series for value in series.values
        ):
            raise ValueError("Chart counts must be non-negative integers")
        return self


class FinanceMetric(BaseModel):
    label: str
    value: Decimal | None
    unit: Literal["INR", "count", "percent"] = "INR"


class FinanceReport(BaseModel):
    title: str
    currency: Literal["INR"] = "INR"
    timezone: Literal["Asia/Kolkata"] = "Asia/Kolkata"
    start_date: date | None = None
    end_date: date
    notes: list[str] = Field(default_factory=list)
    metrics: list[FinanceMetric] = Field(default_factory=list)
    charts: list[FinanceChart] = Field(default_factory=list)

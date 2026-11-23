from decimal import Decimal

from pydantic import BaseModel


class DashboardMetrics(BaseModel):
    appointments_today: int
    patients_registered: int
    doctors_registered: int
    recorded_billing: Decimal
    outstanding_bills: int

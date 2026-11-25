from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.security import get_db, require_roles
from app.schemas.triage import TriageRequest, TriageResponse
from app.services.triage_service import assess_patient_with_doctors


router = APIRouter(
    prefix="/triage",
    tags=["Triage"]
)


@router.post(
    "/",
    response_model=TriageResponse,
    dependencies=[Depends(require_roles("patient"))],
)
def perform_triage(
    request: TriageRequest,
    db: Session = Depends(get_db),
):
    return assess_patient_with_doctors(db, request.symptoms)

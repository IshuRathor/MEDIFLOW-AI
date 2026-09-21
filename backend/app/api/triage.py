from fastapi import APIRouter
from app.schemas.triage import TriageRequest, TriageResponse
from app.services.triage_service import triage_patient


router = APIRouter(
    prefix="/triage",
    tags=["Triage"]
)


@router.post(
    "/",
    response_model=TriageResponse
)
def perform_triage(
    request: TriageRequest
):
    return triage_patient(request.symptoms)
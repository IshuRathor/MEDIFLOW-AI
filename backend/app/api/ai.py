from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy import select, update
from app.infrastructure.rate_limit import enforce_rate_limit

from app.ai.orchestrator import run_orchestrator
from app.core.security import get_current_user, get_db, get_linked_doctor
from app.models.ai import AIApproval, AIConversationMessage
from app.models.appointment import Appointment
from app.models.availability import DoctorAvailability
from app.api.availability import generate_slots
from app.models.doctor import Doctor
from app.models.patient import Patient
from app.models.user import User
from app.schemas.ai import AIChatResponse, ApprovalResponse, ChatRequest


router = APIRouter(prefix="/ai", tags=["AI"])

MAX_CHAT_REQUESTS_PER_MINUTE = 20


@router.post("/chat", response_model=AIChatResponse)
def chat(
    request: ChatRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    enforce_rate_limit(
        "ai_chat",
        str(current_user.id),
        MAX_CHAT_REQUESTS_PER_MINUTE,
    )
    if request.conversation_id:
        foreign_owner = db.query(AIConversationMessage).filter(
            AIConversationMessage.conversation_id == request.conversation_id,
            AIConversationMessage.user_id != current_user.id,
        ).first()
        if foreign_owner:
            raise HTTPException(
                status_code=403,
                detail="Conversation belongs to another user",
            )
    return run_orchestrator(
        db=db,
        user=current_user,
        query=request.query,
        conversation_id=request.conversation_id,
    )


@router.post("/approvals/{approval_id}/{decision}", response_model=ApprovalResponse)
def decide_approval(
    approval_id: str,
    decision: Literal["approve", "reject"],
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    approval = (
        db.query(AIApproval)
        .filter(AIApproval.id == approval_id)
        .with_for_update()
        .first()
    )
    if not approval:
        raise HTTPException(status_code=404, detail="Approval request not found")
    if approval.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="This approval belongs to another user")
    if current_user.role not in ("admin", "staff", "clinician", "patient"):
        raise HTTPException(status_code=403, detail="Your role cannot execute this operation")

    if approval.status != "pending":
        raise HTTPException(status_code=409, detail=f"Approval is already {approval.status}")

    expires_at = approval.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at <= datetime.now(timezone.utc):
        approval.status = "expired"
        db.commit()
        raise HTTPException(status_code=410, detail="Approval request has expired")

    try:
        if decision == "reject":
            guarded = db.execute(
                update(AIApproval)
                .where(
                    AIApproval.id == approval_id,
                    AIApproval.status == "pending",
                )
                .values(status="rejected")
            )
            if guarded.rowcount != 1:
                db.rollback()
                raise HTTPException(status_code=409, detail="Approval is already processed")
            db.commit()
            return ApprovalResponse(
                approval_id=approval.id,
                status="rejected",
                action=approval.action,
                parameters=approval.parameters_json,
                result={"message": "Operation rejected by the user."},
            )

        guarded = db.execute(
            update(AIApproval)
            .where(
                AIApproval.id == approval_id,
                AIApproval.status == "pending",
            )
            .values(status="approved")
        )
        if guarded.rowcount != 1:
            db.rollback()
            raise HTTPException(status_code=409, detail="Approval is already processed")

        if approval.action == "cancel_appointment":
            appointment_id = int(approval.parameters_json["appointment_id"])
            appointment = (
                db.query(Appointment)
                .filter(Appointment.id == appointment_id)
                .with_for_update()
                .first()
            )
            if not appointment:
                raise HTTPException(status_code=404, detail="Appointment not found")
            if current_user.role == "patient":
                owned_patient = db.query(Patient).filter(Patient.user_id == current_user.id).first()
                if not owned_patient or appointment.patient_id != owned_patient.id:
                    raise HTTPException(status_code=403, detail="You can only cancel your own appointments")
            if current_user.role == "clinician":
                linked_doctor = get_linked_doctor(db, current_user)
                if appointment.doctor_id != linked_doctor.id:
                    raise HTTPException(status_code=403, detail="You can only cancel your own appointments")
            if appointment.status == "Cancelled":
                raise HTTPException(status_code=409, detail="Appointment is already cancelled")

            appointment.status = "Cancelled"
            approval.status = "executed"
            approval.executed_at = datetime.now(timezone.utc)
            approval.execution_result_json = {
                "message": "Appointment cancelled successfully",
                "appointment_id": appointment.id,
                "status": appointment.status,
            }
            db.commit()
            result = approval.execution_result_json

        elif approval.action == "reschedule_appointment":
            parameters = approval.parameters_json
            appointment = (
                db.query(Appointment)
                .filter(Appointment.id == int(parameters["appointment_id"]))
                .with_for_update()
                .first()
            )
            if not appointment:
                raise HTTPException(status_code=404, detail="Appointment not found")
            if current_user.role == "patient":
                owned_patient = db.query(Patient).filter(Patient.user_id == current_user.id).first()
                if not owned_patient or appointment.patient_id != owned_patient.id:
                    raise HTTPException(status_code=403, detail="You can only reschedule your own appointments")
            if current_user.role == "clinician":
                linked_doctor = get_linked_doctor(db, current_user)
                if appointment.doctor_id != linked_doctor.id:
                    raise HTTPException(status_code=403, detail="You can only reschedule your own appointments")
            if appointment.status == "Cancelled":
                raise HTTPException(status_code=409, detail="A cancelled appointment cannot be rescheduled")

            try:
                appointment_datetime = datetime.strptime(
                    f"{parameters['appointment_date']} {parameters['appointment_time']}",
                    "%Y-%m-%d %H:%M",
                )
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid reschedule date or time")

            day_name = appointment_datetime.strftime("%A")
            availability = db.query(DoctorAvailability).filter(
                DoctorAvailability.doctor_id == appointment.doctor_id,
                DoctorAvailability.day_of_week == day_name,
                DoctorAvailability.is_available == True,
            ).first()
            if not availability:
                raise HTTPException(status_code=409, detail=f"Doctor is not available on {day_name}")
            if not availability.start_time <= appointment_datetime.time() <= availability.end_time:
                raise HTTPException(status_code=409, detail="Requested time is outside doctor working hours")

            conflict = (
                db.query(Appointment)
                .filter(
                    Appointment.status == "Scheduled",
                    Appointment.appointment_date == appointment_datetime,
                    Appointment.id != appointment.id,
                    (
                        (Appointment.doctor_id == appointment.doctor_id)
                        | (Appointment.patient_id == appointment.patient_id)
                    ),
                )
                .with_for_update()
                .first()
            )
            if conflict:
                raise HTTPException(status_code=409, detail="The patient or doctor already has an appointment at that time")

            appointment.appointment_date = appointment_datetime
            appointment.status = "Scheduled"
            approval.status = "executed"
            approval.executed_at = datetime.now(timezone.utc)
            approval.execution_result_json = {
                "message": "Appointment rescheduled successfully",
                "appointment_id": appointment.id,
                "appointment_date": appointment.appointment_date.isoformat(),
                "status": appointment.status,
            }
            db.commit()
            result = approval.execution_result_json

        elif approval.action == "create_appointment":
            parameters = approval.parameters_json
            patient = (
                db.query(Patient)
                .filter(Patient.id == int(parameters["patient_id"]))
                .with_for_update()
                .first()
            )
            if not patient:
                raise HTTPException(status_code=404, detail="Patient not found")
            if current_user.role == "patient" and patient.user_id != current_user.id:
                raise HTTPException(status_code=403, detail="You can only book appointments for yourself")

            doctor = (
                db.query(Doctor)
                .filter(Doctor.id == int(parameters["doctor_id"]))
                .with_for_update()
                .first()
            )
            if not doctor:
                raise HTTPException(status_code=404, detail="Doctor not found")
            if current_user.role == "clinician":
                linked_doctor = get_linked_doctor(db, current_user)
                if doctor.id != linked_doctor.id:
                    raise HTTPException(status_code=403, detail="You can only create appointments for yourself")

            try:
                appointment_datetime = datetime.strptime(
                    f"{parameters['appointment_date']} {parameters['appointment_time']}",
                    "%Y-%m-%d %H:%M",
                )
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid appointment date or time")

            slot_result = generate_slots(db, doctor.id, appointment_datetime.date())
            matching_slot = next(
                (
                    slot for slot in slot_result["slots"]
                    if slot["status"] == "available"
                    and slot["start"] == appointment_datetime.isoformat()
                ),
                None,
            )
            if slot_result["blocked"]:
                raise HTTPException(status_code=409, detail="Doctor is not available at this time.")
            if not matching_slot:
                raise HTTPException(status_code=409, detail="This appointment slot is already booked.")

            conflict = (
                db.query(Appointment)
                .filter(
                    Appointment.status == "Scheduled",
                    Appointment.appointment_date == appointment_datetime,
                    (
                        (Appointment.doctor_id == doctor.id)
                        | (Appointment.patient_id == patient.id)
                    ),
                )
                .with_for_update()
                .first()
            )
            if conflict:
                raise HTTPException(status_code=409, detail="The patient or doctor already has an appointment at that time")

            appointment = Appointment(
                patient_id=patient.id,
                doctor_id=doctor.id,
                appointment_date=appointment_datetime,
                reason="AI-assisted booking",
                status="Scheduled",
            )
            db.add(appointment)
            approval.status = "executed"
            approval.executed_at = datetime.now(timezone.utc)
            db.flush()
            approval.execution_result_json = {
                "message": "Appointment booked successfully",
                "appointment_id": appointment.id,
                "patient_id": appointment.patient_id,
                "doctor_id": appointment.doctor_id,
                "appointment_date": appointment.appointment_date.isoformat(),
                "status": appointment.status,
            }
            db.commit()
            result = approval.execution_result_json

        else:
            raise HTTPException(status_code=400, detail="Unsupported approval action")

        return ApprovalResponse(
            approval_id=approval.id,
            status="executed",
            action=approval.action,
            parameters=approval.parameters_json,
            result=result,
        )
    except HTTPException:
        db.rollback()
        raise
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="The operation is already executed or conflicts with another appointment")
    except SQLAlchemyError:
        db.rollback()
        try:
            current_status = db.execute(
                select(AIApproval.status).where(AIApproval.id == approval_id)
            ).scalar_one_or_none()
        except SQLAlchemyError:
            current_status = None
        if current_status in ("approved", "executed"):
            raise HTTPException(status_code=409, detail="Approval is already processed")
        raise HTTPException(status_code=503, detail="The operation could not be committed safely")


@router.delete("/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
def clear_conversation(
    conversation_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    db.query(AIConversationMessage).filter(
        AIConversationMessage.user_id == current_user.id,
        AIConversationMessage.conversation_id == conversation_id,
    ).delete(synchronize_session=False)
    db.query(AIApproval).filter(
        AIApproval.user_id == current_user.id,
        AIApproval.conversation_id == conversation_id,
    ).delete(synchronize_session=False)
    db.commit()

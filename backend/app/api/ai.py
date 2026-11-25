from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy import select, update
from app.infrastructure.rate_limit import enforce_rate_limit

from app.ai.orchestrator import DOCTOR_INTELLIGENCE_TOOLS, REGISTRY, run_orchestrator, _create_pending_approval
from app.core.security import get_current_user, get_db, get_linked_doctor
from app.models.ai import AIApproval, AIConversationMessage
from app.models.appointment import Appointment, ACTIVE_APPOINTMENT_STATUSES
from app.models.availability import DoctorAvailability
from app.api.availability import generate_slots
from app.models.doctor import Doctor
from app.models.patient import Patient
from app.models.user import User
from app.schemas.ai import AIChatResponse, ApprovalResponse, ChatRequest
from app.services.billing import BILLING_REVIEW_PREFIX, generate_bill, record_payment
from app.services.finance_analytics import FINANCE_ROLES
from app.services.cancellation import (
    REQUEST_CANCELLATION, appointment_card, cancellation_choices, eligible_appointments,
    ensure_can_cancel, ensure_no_cancellation, submit_cancellation, unchanged_appointment,
)


router = APIRouter(prefix="/ai", tags=["AI"])

MAX_CHAT_REQUESTS_PER_MINUTE = 20


def _restorable_chat_data(data: dict) -> dict:
    """Persist UI context needed to resume appointment workflows."""
    if not isinstance(data, dict):
        return {}
    restored = {}
    if isinstance(data.get("admin_view"), dict):
        restored["admin_view"] = data["admin_view"]
    if isinstance(data.get("finance_view"), dict):
        restored["finance_view"] = data["finance_view"]
    if isinstance(data.get("doctor_view"), dict):
        restored["doctor_view"] = data["doctor_view"]
    if isinstance(data.get("doctor_patient_id"), int):
        restored["doctor_patient_id"] = data["doctor_patient_id"]
    if "cancellation_options" in data:
        restored["cancellation_picker"] = True
        if isinstance(data.get("cancellation_doctor_filter"), str):
            restored["cancellation_doctor_filter"] = data["cancellation_doctor_filter"]
    doctors = data.get("doctors")
    if isinstance(doctors, list):
        restored["doctors"] = [
            {key: doctor[key] for key in ("id", "name", "specialization", "department") if key in doctor}
            for doctor in doctors
            if isinstance(doctor, dict)
        ]
    doctor = data.get("doctor")
    if isinstance(doctor, dict):
        restored["doctor"] = {
            key: doctor[key]
            for key in ("id", "name", "specialization", "department")
            if key in doctor
        }
    for key in ("available_slots", "alternatives"):
        value = data.get(key)
        if isinstance(value, list) and all(isinstance(item, str) for item in value):
            restored[key] = value[:30]
    date_value = data.get("date", data.get("appointment_date"))
    if isinstance(date_value, str):
        restored["date"] = date_value
    if isinstance(data.get("appointment_time"), str):
        restored["time"] = data["appointment_time"]
    return restored


def _add_approval_outcome_message(db: Session, approval: AIApproval, user_id: int, message: str):
    if approval.action in {"generate_bill", "record_payment"} and approval.conversation_id.startswith(BILLING_REVIEW_PREFIX):
        return
    db.add(AIConversationMessage(
        user_id=user_id,
        conversation_id=approval.conversation_id,
        role="assistant",
        content=message,
    ))


@router.post("/chat", response_model=AIChatResponse)
def chat(
    request: ChatRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if request.doctor_patient_id is not None and current_user.role != "clinician":
        raise HTTPException(status_code=403, detail="Doctor access is required")
    enforce_rate_limit(
        "ai_chat",
        str(current_user.id),
        MAX_CHAT_REQUESTS_PER_MINUTE,
    )
    if request.conversation_id:
        owned_message = db.query(AIConversationMessage.id).filter(
            AIConversationMessage.conversation_id == request.conversation_id,
            AIConversationMessage.user_id == current_user.id,
        ).first()
        if not owned_message:
            foreign_owner = db.query(AIConversationMessage.id).filter(
                AIConversationMessage.conversation_id == request.conversation_id,
                AIConversationMessage.user_id != current_user.id,
            ).first()
            if foreign_owner:
                raise HTTPException(status_code=403, detail="Conversation belongs to another user")
            raise HTTPException(status_code=404, detail="Conversation is no longer available")

    response = run_orchestrator(
        db=db,
        user=current_user,
        query=request.query,
        conversation_id=request.conversation_id,
        doctor_patient_id=request.doctor_patient_id,
    )
    assistant_message = db.query(AIConversationMessage).filter(
        AIConversationMessage.user_id == current_user.id,
        AIConversationMessage.conversation_id == response["conversation_id"],
        AIConversationMessage.role == "assistant",
    ).order_by(AIConversationMessage.created_at.desc(), AIConversationMessage.id.desc()).first()
    if assistant_message:
        assistant_message.trace_json = {
            "trace": response.get("trace", []),
            "restore": {
                "status": response["status"],
                "agent": response["agent"],
                "data": _restorable_chat_data(response.get("data", {})),
            },
        }
        db.commit()
    return response


class CancellationSelection(BaseModel):
    appointment_id: int = Field(gt=0)


@router.post("/conversations/{conversation_id}/cancellation-selection", response_model=AIChatResponse)
def select_cancellation(
    conversation_id: str,
    request: CancellationSelection,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != "patient":
        raise HTTPException(status_code=403, detail="Patient access is required")
    enforce_rate_limit("ai_chat", str(current_user.id), MAX_CHAT_REQUESTS_PER_MINUTE)
    assistants = db.query(AIConversationMessage).filter(
        AIConversationMessage.user_id == current_user.id,
        AIConversationMessage.conversation_id == conversation_id,
        AIConversationMessage.role == "assistant",
    ).order_by(AIConversationMessage.id.desc())
    last_assistant = assistants.first()
    if not last_assistant:
        raise HTTPException(status_code=404, detail="Conversation is no longer available")
    metadata = last_assistant.trace_json or {}
    if not (isinstance(metadata, dict) and metadata.get("restore", {}).get("data", {}).get("cancellation_picker")):
        raise HTTPException(status_code=409, detail="Ask to cancel an appointment before selecting it")
    # Serialize selection and deletion on the persisted picker, including on SQLite.
    locked = db.execute(
        update(AIConversationMessage).where(
            AIConversationMessage.id == last_assistant.id,
            AIConversationMessage.user_id == current_user.id,
        ).values(content=AIConversationMessage.content)
    )
    if locked.rowcount != 1 or assistants.first().id != last_assistant.id:
        raise HTTPException(status_code=409, detail="The cancellation selection changed. Reopen the conversation.")
    pending = db.query(AIApproval.id).filter(
        AIApproval.conversation_id == conversation_id,
        AIApproval.user_id == current_user.id,
        AIApproval.status == "pending",
        AIApproval.expires_at > datetime.now(timezone.utc),
    ).first()
    if pending:
        raise HTTPException(status_code=409, detail="Resolve the pending confirmation first")
    appointment = eligible_appointments(db, current_user).filter(Appointment.id == request.appointment_id).first()
    if not appointment:
        raise HTTPException(status_code=404, detail="No eligible appointment found")

    card = appointment_card(appointment)
    approval = _create_pending_approval(
        db, current_user, conversation_id, REQUEST_CANCELLATION,
        {
            "appointment_id": appointment.id,
            "appointment_date": card["appointment_date"],
            "previous_request_id": appointment.cancellation_request_id,
            "card": card,
        },
        commit=False,
    )
    response = {
        "conversation_id": conversation_id,
        "agent": "Hospital Operations Agent",
        "status": "approval_required",
        "message": "Do you want to send a cancellation request to your doctor?",
        "data": {"cancellation_selection": card},
        "trace": [{"tool": REQUEST_CANCELLATION, "status": "approval_required", "duration_ms": 0}],
        "approval_id": approval.id,
    }
    db.add(AIConversationMessage(
        user_id=current_user.id,
        conversation_id=conversation_id,
        role="assistant",
        content=response["message"],
        trace_json={"trace": response["trace"], "restore": {
            "status": response["status"], "agent": response["agent"], "data": {},
        }},
    ))
    db.commit()
    return response


@router.get("/conversations/latest")
def latest_conversation(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    latest = db.query(AIConversationMessage).filter(
        AIConversationMessage.user_id == current_user.id,
    ).order_by(AIConversationMessage.created_at.desc(), AIConversationMessage.id.desc()).first()
    if not latest:
        return {
            "conversation_id": None,
            "messages": [],
            "last_response": None,
            "pending_approval": None,
            "expired_approval": False,
        }

    conversation_id = latest.conversation_id
    messages = db.query(AIConversationMessage).filter(
        AIConversationMessage.user_id == current_user.id,
        AIConversationMessage.conversation_id == conversation_id,
    ).order_by(AIConversationMessage.created_at.desc(), AIConversationMessage.id.desc()).limit(50).all()
    messages.reverse()
    restored_messages = [{"role": item.role, "content": item.content} for item in messages]
    last_assistant = next((item for item in reversed(messages) if item.role == "assistant"), None)
    metadata = last_assistant.trace_json if last_assistant and isinstance(last_assistant.trace_json, dict) else {}
    last_response = metadata.get("restore") if isinstance(metadata.get("restore"), dict) else None
    if last_response is not None:
        last_response = {**last_response, "trace": metadata.get("trace", [])}
        admin_view = last_response.get("data", {}).get("admin_view")
        if current_user.role == "admin" and isinstance(admin_view, dict):
            result, trace = REGISTRY.execute("admin_analytics", current_user, db, admin_view)
            last_response.update(
                status="error" if result["status"] == "error" else "completed",
                data={"admin_report": result["admin_report"]} if "admin_report" in result else {},
                trace=[trace],
            )
            restored_messages[messages.index(last_assistant)] = {"role": "assistant", "content": result["message"]}
        finance_view = last_response.get("data", {}).get("finance_view")
        if current_user.role in FINANCE_ROLES and isinstance(finance_view, dict):
            result, trace = REGISTRY.execute("finance_analytics", current_user, db, finance_view)
            last_response.update(
                status="error" if result["status"] == "error" else "completed",
                data={"finance_report": result["finance_report"]} if "finance_report" in result else {},
                trace=[trace],
            )
            restored_messages[messages.index(last_assistant)] = {"role": "assistant", "content": result["message"]}
        doctor_view = last_response.get("data", {}).get("doctor_view")
        if current_user.role == "clinician" and doctor_view and doctor_view.get("tool") in DOCTOR_INTELLIGENCE_TOOLS:
            result, trace = REGISTRY.execute(doctor_view["tool"], current_user, db, doctor_view["arguments"])
            last_response.update(
                status={"success": "completed", "error": "error", "clarification_required": "clarification_required"}[result["status"]],
                data={key: result[key] for key in ("doctor_intelligence", "doctor_patient_id") if key in result},
                trace=[trace],
            )
            restored_messages[messages.index(last_assistant)] = {"role": "assistant", "content": result["message"]}
        if current_user.role == "patient" and last_response.get("data", {}).get("cancellation_picker"):
            choices = cancellation_choices(db, current_user, last_response["data"].get("cancellation_doctor_filter"))
            restored_messages[messages.index(last_assistant)] = {"role": "assistant", "content": choices["message"]}
            last_response.update(status=choices["status"], data=choices["data"])

    approval = db.query(AIApproval).filter(
        AIApproval.user_id == current_user.id,
        AIApproval.conversation_id == conversation_id,
        AIApproval.status == "pending",
    ).order_by(AIApproval.created_at.desc(), AIApproval.id.desc()).first()
    expired_approval = False
    pending_approval = None
    if approval:
        expires_at = approval.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at <= datetime.now(timezone.utc):
            approval.status = "expired"
            approval.execution_result_json = {"message": "This confirmation expired. Start a new conversation to continue."}
            expired_message = approval.execution_result_json["message"]
            db.add(AIConversationMessage(
                user_id=current_user.id,
                conversation_id=conversation_id,
                role="assistant",
                content=expired_message,
            ))
            db.commit()
            messages = db.query(AIConversationMessage).filter(
                AIConversationMessage.user_id == current_user.id,
                AIConversationMessage.conversation_id == conversation_id,
            ).order_by(AIConversationMessage.created_at.desc(), AIConversationMessage.id.desc()).limit(50).all()
            messages.reverse()
            restored_messages = [{"role": item.role, "content": item.content} for item in messages]
            last_response = {"status": "error", "agent": "Hospital Operations Agent", "data": {}}
            expired_approval = True
        else:
            pending_approval = {
                "id": approval.id,
                "action": approval.action,
                "expires_at": expires_at.isoformat(),
            }
            if approval.action == REQUEST_CANCELLATION:
                last_response = {
                    "status": "approval_required",
                    "agent": "Hospital Operations Agent",
                    "data": {"cancellation_selection": approval.parameters_json["card"]},
                    "trace": [{"tool": REQUEST_CANCELLATION, "status": "approval_required", "duration_ms": 0}],
                }
            elif approval.action in {"create_appointment", "reschedule_appointment"}:
                parameters = approval.parameters_json or {}
                restored_data = dict((last_response or {}).get("data") or {})
                doctor_id = parameters.get("doctor_id")
                if doctor_id is None and parameters.get("appointment_id") is not None:
                    appointment = db.query(Appointment).filter(Appointment.id == int(parameters["appointment_id"])).first()
                    doctor_id = appointment.doctor_id if appointment else None
                doctor = db.query(Doctor).filter(Doctor.id == int(doctor_id)).first() if doctor_id is not None else None
                if doctor:
                    restored_data["doctor"] = {
                        "id": doctor.id,
                        "name": doctor.name,
                        "specialization": doctor.specialization,
                        "department": doctor.department,
                    }
                appointment_date = parameters.get("appointment_date")
                if appointment_date:
                    restored_data["date"] = appointment_date
                appointment_time = parameters.get("appointment_time")
                if appointment_time:
                    restored_data["time"] = appointment_time
                last_response = {**(last_response or {}), "data": restored_data}

    latest_approval = db.query(AIApproval).filter(
        AIApproval.user_id == current_user.id,
        AIApproval.conversation_id == conversation_id,
    ).order_by(AIApproval.created_at.desc(), AIApproval.id.desc()).first()
    if latest_approval and latest_approval.status == "expired":
        expired_approval = True
    has_pending_confirmation_message = bool(last_response and last_response.get("status") == "approval_required")
    if latest_approval and latest_approval.status in {"executed", "rejected", "expired"} and has_pending_confirmation_message:
        outcome_message = (latest_approval.execution_result_json or {}).get("message")
        if outcome_message and (not last_assistant or last_assistant.content != outcome_message):
            restored_messages.append({"role": "assistant", "content": outcome_message})
        last_response = {
            "status": "error" if latest_approval.status == "expired" else "completed",
            "agent": (last_response or {}).get("agent", "MediFlow AI"),
            "data": {},
        }

    return {
        "conversation_id": conversation_id,
        "messages": restored_messages,
        "last_response": last_response,
        "pending_approval": pending_approval,
        "expired_approval": expired_approval,
    }


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
        approval.execution_result_json = {"message": "This confirmation expired. Start a new conversation to continue."}
        _add_approval_outcome_message(db, approval, current_user.id, approval.execution_result_json["message"])
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
            result = {
                "message": "Appointment kept." if approval.action == REQUEST_CANCELLATION else "Operation rejected by the user."
            }
            approval.execution_result_json = result
            _add_approval_outcome_message(db, approval, current_user.id, approval.execution_result_json["message"])
            db.commit()
            return ApprovalResponse(
                approval_id=approval.id,
                status="rejected",
                action=approval.action,
                parameters={} if approval.action == REQUEST_CANCELLATION else approval.parameters_json,
                result=result,
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

        if approval.action == REQUEST_CANCELLATION:
            result = submit_cancellation(db, current_user, approval)
            approval.status = "executed"
            approval.executed_at = datetime.now(timezone.utc)
            approval.execution_result_json = result
            _add_approval_outcome_message(db, approval, current_user.id, result["message"])
            db.commit()

        elif approval.action == "cancel_appointment":
            if current_user.role == "patient":
                raise HTTPException(status_code=403, detail="Select an appointment to request cancellation")
            appointment_id = int(approval.parameters_json["appointment_id"])
            appointment = (
                db.query(Appointment)
                .filter(Appointment.id == appointment_id)
                .with_for_update()
                .first()
            )
            if not appointment:
                raise HTTPException(status_code=404, detail="Appointment not found")
            if current_user.role == "clinician":
                linked_doctor = get_linked_doctor(db, current_user)
                if appointment.doctor_id != linked_doctor.id:
                    raise HTTPException(status_code=403, detail="You can only cancel your own appointments")
            ensure_can_cancel(appointment)
            changed = db.execute(
                update(Appointment).where(*unchanged_appointment(appointment)).values(status="Cancelled")
            )
            if changed.rowcount != 1:
                raise HTTPException(status_code=409, detail="This appointment changed. Refresh and try again.")
            approval.status = "executed"
            approval.executed_at = datetime.now(timezone.utc)
            approval.execution_result_json = {
                "message": "Appointment cancelled successfully",
                "appointment_id": appointment.id,
                "status": appointment.status,
            }
            _add_approval_outcome_message(db, approval, current_user.id, approval.execution_result_json["message"])
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
            ensure_no_cancellation(appointment)

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
                    Appointment.status.in_(ACTIVE_APPOINTMENT_STATUSES),
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

            reschedule_status = "Pending Doctor Approval" if current_user.role == "patient" else "Scheduled"
            changed = db.execute(
                update(Appointment).where(*unchanged_appointment(appointment)).values(
                    appointment_date=appointment_datetime, status=reschedule_status,
                )
            )
            if changed.rowcount != 1:
                raise HTTPException(status_code=409, detail="This appointment changed. Refresh and try again.")
            approval.status = "executed"
            approval.executed_at = datetime.now(timezone.utc)
            approval.execution_result_json = {
                "message": "Appointment reschedule request submitted and waiting for doctor approval" if current_user.role == "patient" else "Appointment rescheduled successfully",
                "appointment_id": appointment.id,
                "appointment_date": appointment_datetime.isoformat(),
                "status": reschedule_status,
            }
            _add_approval_outcome_message(db, approval, current_user.id, approval.execution_result_json["message"])
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
                    Appointment.status.in_(ACTIVE_APPOINTMENT_STATUSES),
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
                reason=parameters.get("reason") or "AI-assisted booking",
                status="Pending Doctor Approval" if current_user.role == "patient" else "Scheduled",
            )
            db.add(appointment)
            approval.status = "executed"
            approval.executed_at = datetime.now(timezone.utc)
            db.flush()
            approval.execution_result_json = {
                "message": "Appointment request submitted and waiting for doctor approval" if current_user.role == "patient" else "Appointment booked successfully",
                "appointment_id": appointment.id,
                "patient_id": appointment.patient_id,
                "doctor_id": appointment.doctor_id,
                "appointment_date": appointment.appointment_date.isoformat(),
                "status": appointment.status,
            }
            _add_approval_outcome_message(db, approval, current_user.id, approval.execution_result_json["message"])
            db.commit()
            result = approval.execution_result_json

        elif approval.action == "generate_bill":
            if current_user.role not in ("admin", "staff"):
                raise HTTPException(status_code=403, detail="Only administrators or finance staff can generate bills")
            parameters = approval.parameters_json
            bill = generate_bill(
                db, int(parameters["patient_id"]), str(parameters["bill_number"]),
                items=parameters.get("items"), total_amount=parameters.get("total_amount"),
            )
            approval.status = "executed"
            approval.executed_at = datetime.now(timezone.utc)
            db.flush()
            approval.execution_result_json = {
                "message": "Bill generated successfully",
                "bill_id": bill.id,
                "bill_number": bill.bill_number,
                "patient_id": bill.patient_id,
                "total_amount": float(bill.total_amount),
                "status": bill.status,
            }
            _add_approval_outcome_message(db, approval, current_user.id, approval.execution_result_json["message"])
            db.commit()
            result = approval.execution_result_json

        elif approval.action == "record_payment":
            if current_user.role not in ("admin", "staff"):
                raise HTTPException(status_code=403, detail="Only administrators or finance staff can record payments")
            parameters = approval.parameters_json
            bill, payment = record_payment(
                db, int(parameters["bill_id"]), parameters["amount"],
                parameters["payment_method"], parameters.get("transaction_reference"),
            )
            approval.status = "executed"
            approval.executed_at = datetime.now(timezone.utc)
            approval.execution_result_json = {
                "message": "Payment recorded successfully",
                "payment_id": payment.id,
                "bill_id": bill.id,
                "amount": float(payment.amount),
                "bill_status": bill.status,
            }
            _add_approval_outcome_message(db, approval, current_user.id, approval.execution_result_json["message"])
            db.commit()
            result = approval.execution_result_json

        else:
            raise HTTPException(status_code=400, detail="Unsupported approval action")

        return ApprovalResponse(
            approval_id=approval.id,
            status="executed",
            action=approval.action,
            parameters={} if approval.action == REQUEST_CANCELLATION else approval.parameters_json,
            result=result,
        )
    except HTTPException:
        db.rollback()
        raise
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="The operation is already executed or conflicts with an existing record")
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

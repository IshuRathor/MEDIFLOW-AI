from datetime import date, datetime, time, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.security import get_db
from app.models.appointment import Appointment
from app.models.doctor import Doctor
from app.models.finance import Bill, Payment
from app.models.patient import Patient
from app.schemas.dashboard import DashboardMetrics
from app.core.security import get_current_user, get_linked_doctor
from app.models.patient import Patient
from app.models.user import User
from app.models.availability import DoctorAvailability
from app.models.audit import AuditLog


router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


def _as_naive_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _appointment_item(appointment: Appointment, db: Session):
    patient = db.query(Patient).filter(Patient.id == appointment.patient_id).first()
    doctor = db.query(Doctor).filter(Doctor.id == appointment.doctor_id).first()
    return {
        "id": appointment.id,
        "patient_id": appointment.patient_id,
        "patient_name": patient.name if patient else f"Patient #{appointment.patient_id}",
        "doctor_id": appointment.doctor_id,
        "doctor_name": doctor.name if doctor else f"Doctor #{appointment.doctor_id}",
        "appointment_date": appointment.appointment_date.isoformat(),
        "reason": appointment.reason,
        "status": appointment.status,
        "notes": appointment.notes,
    }


@router.get("/metrics", response_model=DashboardMetrics)
def get_dashboard_metrics(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    today = date.today()
    today_start = datetime.combine(today, time.min)
    tomorrow_start = today_start + timedelta(days=1)
    month_start = today.replace(day=1)

    appointment_query = db.query(func.count(Appointment.id)).filter(
        Appointment.appointment_date >= today_start,
        Appointment.appointment_date < tomorrow_start,
        Appointment.status != "Cancelled",
    )
    bill_query = db.query(func.coalesce(func.sum(Bill.total_amount), 0)).filter(
        Bill.created_at >= month_start
    )
    outstanding_query = db.query(func.count(Bill.id)).filter(
        Bill.status.in_(("Pending", "Partially Paid"))
    )
    if current_user.role == "patient":
        owned_patient = db.query(Patient).filter(Patient.user_id == current_user.id).first()
        if owned_patient:
            appointment_query = appointment_query.filter(Appointment.patient_id == owned_patient.id)
            bill_query = bill_query.filter(Bill.patient_id == owned_patient.id)
            outstanding_query = outstanding_query.filter(Bill.patient_id == owned_patient.id)
            patient_count = 1
        else:
            appointment_query = appointment_query.filter(Appointment.id == -1)
            bill_query = bill_query.filter(Bill.id == -1)
            outstanding_query = outstanding_query.filter(Bill.id == -1)
            patient_count = 0
    elif current_user.role == "clinician":
        linked_doctor = get_linked_doctor(db, current_user)
        appointment_query = appointment_query.filter(Appointment.doctor_id == linked_doctor.id)
        patient_count = db.query(func.count(func.distinct(Appointment.patient_id))).filter(
            Appointment.doctor_id == linked_doctor.id
        ).scalar() or 0
        doctors_registered = 1
        recorded_billing = 0
        outstanding_bills = 0
    else:
        patient_count = db.query(func.count(Patient.id)).scalar() or 0
        recorded_billing = bill_query.scalar() or 0
        outstanding_bills = outstanding_query.scalar() or 0
        doctors_registered = db.query(func.count(Doctor.id)).scalar() or 0

    appointments_today = appointment_query.scalar() or 0
    patients_registered = patient_count

    return DashboardMetrics(
        appointments_today=appointments_today,
        patients_registered=patients_registered,
        doctors_registered=doctors_registered,
        recorded_billing=recorded_billing,
        outstanding_bills=outstanding_bills,
    )


@router.get("/doctor")
def doctor_dashboard(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if current_user.role != "clinician":
        raise HTTPException(status_code=403, detail="Doctor dashboard access is required")
    doctor = get_linked_doctor(db, current_user)

    today = date.today()
    today_start = datetime.combine(today, time.min)
    tomorrow_start = today_start + timedelta(days=1)

    all_appointments = db.query(Appointment).filter(Appointment.doctor_id == doctor.id).all()
    today_appointments = [
        appointment for appointment in all_appointments
        if today_start <= _as_naive_utc(appointment.appointment_date) < tomorrow_start
    ]
    upcoming = [
        appointment for appointment in all_appointments
        if _as_naive_utc(appointment.appointment_date) >= tomorrow_start
        and appointment.status == "Scheduled"
    ]
    upcoming.sort(key=lambda item: item.appointment_date)
    recent = db.query(Appointment).filter(
        Appointment.doctor_id == doctor.id,
        Appointment.status.in_(("Completed", "Scheduled", "No-show", "Cancelled")),
    ).order_by(Appointment.appointment_date.desc()).limit(8).all()
    availability = db.query(DoctorAvailability).filter(
        DoctorAvailability.doctor_id == doctor.id
    ).order_by(DoctorAvailability.day_of_week.asc(), DoctorAvailability.start_time.asc()).all()

    assigned_patient_ids = {
        appointment.patient_id for appointment in all_appointments
    }
    assigned_patients = db.query(Patient).filter(Patient.id.in_(assigned_patient_ids)).all() if assigned_patient_ids else []

    return {
        "role": "clinician",
        "doctor": {
            "id": doctor.id,
            "name": doctor.name,
            "specialization": doctor.specialization,
            "department": doctor.department,
        },
        "stats": {
            "todays_appointments": len(today_appointments),
            "upcoming_appointments": len(upcoming),
            "assigned_patients": len(assigned_patient_ids),
            "completed_consultations": sum(1 for item in all_appointments if item.status == "Completed"),
            "pending_consultations": sum(1 for item in all_appointments if item.status == "Scheduled"),
            "cancelled_appointments": sum(1 for item in all_appointments if item.status == "Cancelled"),
        },
        "today_schedule": [_appointment_item(item, db) for item in sorted(today_appointments, key=lambda item: item.appointment_date)],
        "upcoming_appointments": [_appointment_item(item, db) for item in upcoming],
        "recent_visits": [_appointment_item(item, db) for item in recent],
        "assigned_patients": [
            {"id": patient.id, "name": patient.name, "email": patient.email, "phone": patient.phone}
            for patient in assigned_patients
        ],
        "availability": [
            {
                "day": item.day_of_week,
                "start_time": item.start_time.isoformat(),
                "end_time": item.end_time.isoformat(),
                "is_available": item.is_available,
            }
            for item in availability
        ],
    }


@router.get("/patient")
def patient_dashboard(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if current_user.role != "patient":
        raise HTTPException(status_code=403, detail="Patient dashboard access is required")
    patient = db.query(Patient).filter(Patient.user_id == current_user.id).first()
    if not patient:
        raise HTTPException(status_code=403, detail="No patient profile is linked to this account")

    now = datetime.now()
    appointments = db.query(Appointment).filter(Appointment.patient_id == patient.id).order_by(Appointment.appointment_date.desc()).all()
    upcoming = [item for item in appointments if _as_naive_utc(item.appointment_date) >= now and item.status == "Scheduled"]
    previous = [item for item in appointments if _as_naive_utc(item.appointment_date) < now or item.status in ("Completed", "Cancelled", "No-show")]

    bills = db.query(Bill).filter(Bill.patient_id == patient.id).order_by(Bill.created_at.desc()).all()
    bill_ids = [bill.id for bill in bills]
    payments = db.query(Payment).filter(Payment.bill_id.in_(bill_ids)).order_by(Payment.paid_at.desc()).all() if bill_ids else []

    assigned_doctor = None
    if appointments:
        latest = appointments[0]
        doctor = db.query(Doctor).filter(Doctor.id == latest.doctor_id).first()
        if doctor:
            assigned_doctor = {"id": doctor.id, "name": doctor.name, "specialization": doctor.specialization}

    return {
        "role": "patient",
        "stats": {
            "total_appointments": len(appointments),
            "upcoming_appointments": len(upcoming),
            "previous_appointments": len(previous),
            "bills": len(bills),
            "pending_payments": sum(1 for bill in bills if bill.status in ("Pending", "Partially Paid")),
        },
        "upcoming": [_appointment_item(item, db) for item in sorted(upcoming, key=lambda item: item.appointment_date)],
        "previous": [_appointment_item(item, db) for item in previous[:8]],
        "assigned_doctor": assigned_doctor,
        "bills": [
            {"id": bill.id, "bill_number": bill.bill_number, "total_amount": float(bill.total_amount), "status": bill.status, "created_at": bill.created_at.isoformat()}
            for bill in bills
        ],
        "payments": [
            {"id": payment.id, "bill_id": payment.bill_id, "amount": float(payment.amount), "payment_method": payment.payment_method, "payment_status": payment.payment_status, "paid_at": payment.paid_at.isoformat()}
            for payment in payments
        ],
        "prescriptions": {"supported": False, "items": []},
        "medical_records": {"supported": False, "items": []},
    }


@router.get("/finance")
def finance_dashboard(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if current_user.role != "staff":
        raise HTTPException(status_code=403, detail="Finance staff dashboard access is required")

    today = date.today()
    today_start = datetime.combine(today, time.min)
    tomorrow_start = today_start + timedelta(days=1)
    month_start = today.replace(day=1)
    month_start_datetime = datetime.combine(month_start, time.min)

    completed_payments = db.query(Payment).filter(Payment.payment_status == "Completed").all()
    today_payments = [payment for payment in completed_payments if today_start <= _as_naive_utc(payment.paid_at) < tomorrow_start]
    month_payments = [payment for payment in completed_payments if _as_naive_utc(payment.paid_at) >= month_start_datetime]
    bills = db.query(Bill).order_by(Bill.created_at.desc()).all()
    outstanding_bills = [bill for bill in bills if bill.status in ("Pending", "Partially Paid")]

    recent_payments = db.query(Payment).order_by(Payment.paid_at.desc()).limit(10).all()
    return {
        "role": "staff",
        "stats": {
            "total_revenue": float(sum((payment.amount for payment in completed_payments), 0)),
            "todays_collections": float(sum((payment.amount for payment in today_payments), 0)),
            "monthly_revenue": float(sum((payment.amount for payment in month_payments), 0)),
            "pending_payments": sum(1 for bill in bills if bill.status in ("Pending", "Partially Paid")),
            "outstanding_bills": float(sum((bill.total_amount for bill in outstanding_bills), 0)),
            "total_bills_generated": len(bills),
            "completed_payments": len(completed_payments),
        },
        "recent_transactions": [
            {
                "id": payment.id,
                "bill_id": payment.bill_id,
                "amount": float(payment.amount),
                "payment_method": payment.payment_method,
                "payment_status": payment.payment_status,
                "transaction_reference": payment.transaction_reference,
                "paid_at": payment.paid_at.isoformat(),
            }
            for payment in recent_payments
        ],
    }


@router.get("/admin")
def admin_dashboard(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Administrator dashboard access is required")

    today = date.today()
    today_start = datetime.combine(today, time.min)
    tomorrow_start = today_start + timedelta(days=1)

    patients = db.query(Patient).all()
    doctors = db.query(Doctor).all()
    appointments = db.query(Appointment).all()
    bills = db.query(Bill).all()
    payments = db.query(Payment).filter(Payment.payment_status == "Completed").all()
    pending_users = db.query(User).filter(User.approval_status == "pending").all()
    today_appointments = [
        item for item in appointments
        if today_start <= _as_naive_utc(item.appointment_date) < tomorrow_start
    ]
    pending_bills = [bill for bill in bills if bill.status in ("Pending", "Partially Paid")]
    department_counts = {}
    for doctor in doctors:
        department = doctor.department or "Department not assigned"
        department_counts[department] = department_counts.get(department, 0) + 1

    recent_appointments = db.query(Appointment).order_by(Appointment.appointment_date.desc()).limit(8).all()
    recent_audit = db.query(AuditLog).order_by(AuditLog.created_at.desc()).limit(10).all()

    return {
        "role": "admin",
        "stats": {
            "total_patients": len(patients),
            "total_doctors": len(doctors),
            "total_appointments": len(appointments),
            "todays_appointments": len(today_appointments),
            "hospital_occupancy": None,
            "revenue": float(sum((payment.amount for payment in payments), 0)),
            "pending_bills": len(pending_bills),
            "pending_staff_approvals": len(pending_users),
        },
        "department_statistics": [
            {"department": department, "doctor_count": count}
            for department, count in sorted(department_counts.items())
        ],
        "recent_appointments": [_appointment_item(item, db) for item in recent_appointments],
        "recent_activity": [
            {
                "id": item.id,
                "action": item.action,
                "resource": item.resource,
                "resource_id": item.resource_id,
                "status_code": item.status_code,
                "created_at": item.created_at.isoformat(),
            }
            for item in recent_audit
        ],
    }

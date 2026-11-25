import re
from datetime import datetime, timedelta

from sqlalchemy import func
from sqlalchemy.orm import joinedload

from app.core.security import get_linked_doctor
from app.models.appointment import Appointment
from app.models.patient import Patient
from app.services.cancellation import PENDING_CANCELLATION


ROW_LIMIT = 20
WEEK_LENGTH = timedelta(days=7)


def _appointments(db, user):
    doctor = get_linked_doctor(db, user)
    return db.query(Appointment).filter(Appointment.doctor_id == doctor.id)


def _between(query, start, end):
    return query.filter(Appointment.appointment_date >= start, Appointment.appointment_date < end)


def _day_and_week():
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    return today, today - timedelta(days=today.weekday())


def _week_dates(start):
    return {
        "start": start.date().isoformat(),
        "end": (start + WEEK_LENGTH - timedelta(days=1)).date().isoformat(),
    }


def _visit_section(title, query, *, latest_first=False):
    order = Appointment.appointment_date.desc() if latest_first else Appointment.appointment_date.asc()
    visits = query.options(joinedload(Appointment.patient)).order_by(order, Appointment.id).limit(ROW_LIMIT + 1).all()
    return {
        "title": title,
        "has_more": len(visits) > ROW_LIMIT,
        "visits": [
            {
                "patient_name": item.patient.name,
                "appointment_date": item.appointment_date.isoformat(),
                "status": item.status,
                "cancellation_status": item.cancellation_status,
                "reason": item.reason,
            }
            for item in visits[:ROW_LIMIT]
        ],
    }


def doctor_daily_briefing(db, user, view="daily"):
    visits = _appointments(db, user)
    today, week = _day_and_week()
    tomorrow = today + timedelta(days=1)
    today_visits = _between(visits, today, tomorrow)
    scheduled = visits.filter(Appointment.status == "Scheduled")
    completed = today_visits.filter(Appointment.status == "Completed")
    section_queries = {
        "today": ("Scheduled today", today_visits.filter(Appointment.status == "Scheduled")),
        "booking": ("Pending booking requests", visits.filter(Appointment.status == "Pending Doctor Approval")),
        "cancellation": ("Pending cancellation requests", visits.filter(Appointment.cancellation_status == PENDING_CANCELLATION)),
        "completed": ("Completed visits today", completed),
        "upcoming": ("Upcoming scheduled visits", scheduled.filter(Appointment.appointment_date >= tomorrow)),
        "week": ("Appointments this week", _between(visits, week, week + WEEK_LENGTH)),
    }
    if view != "daily" and view not in section_queries:
        return {"status": "error", "message": "Unknown doctor briefing view."}
    selected = ("today", "booking", "cancellation", "completed", "upcoming") if view == "daily" else (view,)
    result = {
        "title": "Doctor daily briefing" if view == "daily" else section_queries[view][0],
        "date": today.date().isoformat(),
        "sections": [_visit_section(*section_queries[key]) for key in selected],
    }
    if view == "week":
        result["period"] = _week_dates(week)
    if view in ("daily", "completed"):
        result["metrics"] = [
            {"label": "Completed visits today", "value": completed.count()},
            {"label": "Distinct patients seen today", "value": completed.with_entities(func.count(func.distinct(Appointment.patient_id))).scalar()},
        ]
    return {"message": "Here is your recorded appointment activity.", "doctor_intelligence": result}


def doctor_weekly_workload(db, user):
    visits = _appointments(db, user)
    _, week = _day_and_week()
    periods = []
    for title, start in (("This week", week), ("Last week", week - WEEK_LENGTH)):
        end = start + WEEK_LENGTH
        counts = dict(_between(visits, start, end).with_entities(
            Appointment.status, func.count(Appointment.id)
        ).group_by(Appointment.status).all())
        periods.append({
            "title": title,
            **_week_dates(start),
            "scheduled": counts.get("Scheduled", 0),
            "completed": counts.get("Completed", 0),
            "cancelled": counts.get("Cancelled", 0),
        })
    return {
        "message": "Counts use the appointment date and each appointment’s current recorded status.",
        "doctor_intelligence": {"title": "Weekly appointment workload", "periods": periods},
    }


def doctor_patient_timeline(db, user, patient_id=None, patient_name=None, list_patients=False):
    visits = _appointments(db, user)
    patients = db.query(Patient).filter(Patient.id.in_(visits.with_entities(Appointment.patient_id)))
    if patient_id is not None:
        patients = patients.filter(Patient.id == patient_id)
    elif patient_name:
        patients = patients.filter(func.lower(Patient.name) == patient_name.strip().lower())
    matches = patients.order_by(Patient.name, Patient.id).limit(ROW_LIMIT + 1).all()
    if (patient_id is not None or patient_name) and not matches:
        return {"status": "error", "message": "No matching patient is assigned to your appointments."}
    if len(matches) == 1 and (patient_id is not None or patient_name):
        patient = matches[0]
        history = visits.filter(Appointment.patient_id == patient.id, Appointment.appointment_date < datetime.now())
        return {
            "message": "Previous appointments recorded with you.",
            "doctor_patient_id": patient.id,
            "doctor_intelligence": {
                "title": f"Appointment history for {patient.name}",
                "sections": [_visit_section("Previous appointment records", history, latest_first=True)],
            },
        }
    return {
        "status": "success" if list_patients else "clarification_required",
        "message": "Choose an assigned patient to view their appointment records." if matches else "No patients are associated with your appointments.",
        "doctor_intelligence": {
            "title": "Assigned patients",
            "patients": [{"id": patient.id, "name": patient.name} for patient in matches[:ROW_LIMIT]],
            "has_more": len(matches) > ROW_LIMIT,
        },
    }


def doctor_intelligence_call(query):
    text = query.lower().replace("’", "'")
    if re.search(r"\b(appointment history|previous visits|past visits)\b", text):
        name = re.search(r"\b(?:for|with|of)\s+(?:patient\s+)?(.+?)[.!?]*$", query, re.IGNORECASE)
        if name and name[1].strip().lower() not in ("this patient", "the patient", "my patient"):
            return "doctor_patient_timeline", {"patient_name": name[1].strip()}
        return "doctor_patient_timeline", {}
    if "assigned patients" in text or "my upcoming patients" in text:
        return "doctor_patient_timeline", {"list_patients": True}
    if re.search(r"\b(workload|appointment trends|last week|appointments (?:were|have been) cancel(?:l)?ed)\b", text):
        return "doctor_weekly_workload", {}
    if re.search(r"\b(daily briefing|summarize my day|summarise my day)\b", text):
        view = "daily"
    elif "pending" in text and "cancellation" in text:
        view = "cancellation"
    elif re.search(r"\bpending (?:appointment|booking) requests?\b", text):
        view = "booking"
    elif "today" in text and re.search(r"\b(seen|completed visits)\b", text):
        view = "completed"
    elif "this week" in text and "appointments" in text:
        view = "week"
    elif "today" in text and re.search(r"\b(schedule|appointments)\b", text):
        view = "today"
    else:
        return None
    return "doctor_daily_briefing", {"view": view}

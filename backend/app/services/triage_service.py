import logging
import re
from datetime import datetime, timedelta

from sqlalchemy import and_, or_
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.availability import _slots_for_date
from app.models.availability import DoctorAvailability
from app.models.doctor import Doctor
from app.schemas.triage import TriageDoctor, TriageResponse


AVAILABILITY_WINDOW_DAYS = 14
logger = logging.getLogger(__name__)
CHEST_WARNING = re.compile(
    r"\b(?:chest (?:pain|pressure|tightness|discomfort)|"
    r"(?:pain|pressure|tightness|discomfort) (?:in|across|around|on) "
    r"(?:(?:the|my|your|his|her|their) )?(?:left |right |upper |center of the )?chest)\b"
)
EMERGENCY_PHRASES = (
    "difficulty breathing", "trouble breathing", "breathing difficulty",
    "shortness of breath", "can t breathe", "cant breathe", "cannot breathe",
    "struggling to breathe", "gasping for air", "unconscious", "loss of consciousness",
    "lost consciousness", "fainting", "fainted", "passed out", "passing out",
    "stroke", "facial droop", "facial drooping", "face droop", "face drooping",
    "arm weakness", "weakness in one arm", "slurred speech", "speech difficulty",
    "difficulty speaking", "trouble speaking", "severe bleeding", "heavy bleeding",
    "uncontrolled bleeding", "bleeding won t stop", "bleeding that will not stop",
    "seizure", "seizures", "convulsion", "convulsions",
)
SPECIALTY_RULES = (
    # Specialty, reported terms, accepted directory labels.
    ("General Medicine", ("fever", "viral symptoms", "general illness"), ("general medicine", "internal medicine", "general physician", "family medicine", "general practice")),
    ("Cardiology", ("palpitations", "irregular heartbeat", "heart pain", "heart related"), ("cardiology", "cardiologist", "interventional cardiology", "interventional cardiologist", "general cardiology")),
    ("Oncology", ("cancer", "oncology"), ("oncology", "oncologist", "medical oncology", "surgical oncology", "radiation oncology")),
    ("Orthopedics", ("bone pain", "joint pain", "fracture"), ("orthopedics", "orthopaedics", "orthopedic surgery", "orthopaedic surgery")),
    ("Dermatology", ("skin rash", "rash", "itching", "acne"), ("dermatology", "dermatologist")),
    ("Ophthalmology", ("eye pain", "eye irritation", "eye problems"), ("ophthalmology", "ophthalmologist")),
    ("ENT", ("ear pain", "earache", "sore throat", "nasal congestion", "sinus"), ("ent", "otolaryngology", "ear nose and throat", "ear nose throat", "ent specialist")),
    ("Neurology", ("migraine", "numbness", "tingling", "dizziness", "memory loss"), ("neurology", "neurologist")),
    ("Gynecology/Obstetrics", ("pregnancy", "pregnant", "prenatal"), ("gynecology", "gynaecology", "obstetrics", "obstetrics and gynecology", "obstetrics and gynaecology", "gynecology obstetrics", "ob gyn", "obgyn")),
)


def _normalize(text: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", text.lower()))


def emergency_assessment(symptoms: str) -> TriageResponse | None:
    query = f" {_normalize(symptoms)} "
    chest_warning = bool(CHEST_WARNING.search(query))
    if not chest_warning and not any(f" {phrase} " in query for phrase in EMERGENCY_PHRASES):
        return None
    return TriageResponse(
        urgency="Emergency",
        recommended_department="Emergency / Cardiology" if chest_warning else "Emergency",
        symptoms_summary=symptoms,
        recommended_action=(
            "Call local emergency services now for immediate medical evaluation. "
            "Do not wait for an appointment."
        ),
    )


def assess_patient_with_doctors(db: Session, symptoms: str, *, now: datetime | None = None) -> TriageResponse:
    result = triage_patient(symptoms)
    if result.urgency == "Emergency":
        if result.recommended_department == "Emergency / Cardiology":
            try:
                _add_matching_doctors(db, result, "Cardiology", now=now)
            except SQLAlchemyError:
                logger.warning("Emergency triage directory lookup unavailable")
                result.recommended_doctors.clear()
                result.availability_window_days = None
        return result

    if result.recommended_department == "General Medicine" and result.urgency != "High":
        query = f" {_normalize(symptoms)} "
        matches = [
            specialty for specialty, terms, _ in SPECIALTY_RULES
            if any(f" {term} " in query for term in terms)
        ]
        if len(matches) == 1 and matches[0] != "General Medicine":
            result.recommended_department = matches[0]
            result.recommended_action = "Consult a healthcare professional to discuss your concern and the appropriate next step."

    _add_matching_doctors(db, result, result.recommended_department, now=now)
    return result


def _add_matching_doctors(db: Session, result: TriageResponse, specialty: str, *, now: datetime | None) -> None:
    labels = next(labels for name, _, labels in SPECIALTY_RULES if name == specialty)
    doctors = [
        doctor for doctor in db.query(Doctor).order_by(Doctor.name, Doctor.id)
        if _normalize(doctor.specialization) in labels
    ]
    now = now or datetime.now()
    start = now.date()
    end = start + timedelta(days=AVAILABILITY_WINDOW_DAYS - 1)
    result.availability_window_days = AVAILABILITY_WINDOW_DAYS
    configured = {
        doctor_id for (doctor_id,) in db.query(DoctorAvailability.doctor_id).filter(
            DoctorAvailability.doctor_id.in_([doctor.id for doctor in doctors]),
            or_(
                and_(DoctorAvailability.specific_date.is_(None), DoctorAvailability.is_available.is_(True)),
                DoctorAvailability.specific_date.between(start, end),
            ),
        ).distinct()
    }
    for doctor in doctors:
        slots = []
        if doctor.id in configured:
            for offset in range(AVAILABILITY_WINDOW_DAYS):
                day_slots, _ = _slots_for_date(db, doctor, start + timedelta(days=offset))
                slots = sorted(set(slots).union(
                    slot["start"] for slot in day_slots
                    if slot["status"] == "available" and datetime.fromisoformat(slot["start"]) > now
                ))[:3]
                if len(slots) == 3:
                    break
        result.recommended_doctors.append(TriageDoctor(
            id=doctor.id,
            name=doctor.name,
            specialization=doctor.specialization,
            department=doctor.department,
            experience_years=doctor.experience_years,
            availability="available" if slots else "no_slots" if doctor.id in configured else "unverified",
            upcoming_slots=slots,
            matching_explanation=f"This doctor's registered specialization matches {specialty}.",
        ))
    result.recommended_doctors.sort(key=lambda doctor: (
        {"available": 0, "no_slots": 1, "unverified": 2}[doctor.availability],
        doctor.upcoming_slots[0] if doctor.upcoming_slots else "",
    ))


def triage_patient(symptoms: str) -> TriageResponse:
    """
    Performs basic AI-assisted symptom triage.

    This service does not provide a medical diagnosis.
    It only estimates urgency and suggests a department
    based on symptom keywords.
    """

    query = symptoms.lower().strip()

    # ========================================================
    # EMERGENCY SYMPTOMS
    # ========================================================

    emergency = emergency_assessment(symptoms)
    if emergency:
        return emergency

    # ========================================================
    # HIGH URGENCY
    # ========================================================

    high_keywords = [
        "high fever",
        "persistent vomiting",
        "severe abdominal pain",
        "severe headache",
        "blood in stool",
        "blood in urine"
    ]

    if any(keyword in query for keyword in high_keywords):
        return TriageResponse(
            urgency="High",
            recommended_department="General Medicine",
            symptoms_summary=symptoms,
            recommended_action=(
                "Arrange medical evaluation as soon as possible."
            )
        )

    # ========================================================
    # CARDIOLOGY
    # ========================================================

    cardiology_keywords = [
        "palpitations",
        "irregular heartbeat",
        "heart pain",
    ]

    if any(keyword in query for keyword in cardiology_keywords):
        return TriageResponse(
            urgency="High",
            recommended_department="Cardiology",
            symptoms_summary=symptoms,
            recommended_action=(
                "Consult a doctor for cardiovascular evaluation."
            )
        )

    # ========================================================
    # NEUROLOGY
    # ========================================================

    neurology_keywords = [
        "migraine",
        "numbness",
        "tingling",
        "dizziness",
        "memory loss"
    ]

    if any(keyword in query for keyword in neurology_keywords):
        return TriageResponse(
            urgency="Medium",
            recommended_department="Neurology",
            symptoms_summary=symptoms,
            recommended_action=(
                "Schedule a medical consultation for evaluation."
            )
        )

    # ========================================================
    # DERMATOLOGY
    # ========================================================

    dermatology_keywords = [
        "skin rash",
        "rash",
        "itching",
        "acne",
        "skin irritation"
    ]

    if any(keyword in query for keyword in dermatology_keywords):
        return TriageResponse(
            urgency="Low",
            recommended_department="Dermatology",
            symptoms_summary=symptoms,
            recommended_action=(
                "Schedule a routine dermatology consultation."
            )
        )

    # ========================================================
    # GENERAL MEDICINE
    # ========================================================

    general_keywords = [
        "cold",
        "cough",
        "fever",
        "headache",
        "stomach pain",
        "fatigue",
        "weakness"
    ]

    if any(keyword in query for keyword in general_keywords):
        return TriageResponse(
            urgency="Medium",
            recommended_department="General Medicine",
            symptoms_summary=symptoms,
            recommended_action=(
                "Schedule a consultation with a general physician."
            )
        )

    # ========================================================
    # DEFAULT
    # ========================================================

    return TriageResponse(
        urgency="Low",
        recommended_department="General Medicine",
        symptoms_summary=symptoms,
        recommended_action=(
            "Consult a healthcare professional for proper evaluation."
        )
    )

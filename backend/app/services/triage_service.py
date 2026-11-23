from app.schemas.triage import TriageResponse


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

    emergency_keywords = [
        "severe chest pain",
        "difficulty breathing",
        "can't breathe",
        "cannot breathe",
        "unconscious",
        "loss of consciousness",
        "severe bleeding",
        "heavy bleeding",
        "stroke",
        "seizure",
        "convulsion"

    ]

    if any(keyword in query for keyword in emergency_keywords):
        department = "Emergency"

        if (
            "chest pain" in query
            or "breathing" in query
        ):
            department = "Emergency / Cardiology"

        return TriageResponse(
            urgency="Emergency",
            recommended_department=department,
            symptoms_summary=symptoms,
            recommended_action=(
                "Call local emergency services now or go to the nearest "
                "emergency department. Do not wait for an appointment."
            )
        )

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
        "chest discomfort"
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
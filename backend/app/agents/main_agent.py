import os
from datetime import date, datetime, timedelta

from dotenv import load_dotenv
from google import genai

from app.agents.hospital_agent import hospital_agent
from app.agents.finance_agent import finance_agent
from app.agents.support_agent import support_agent
from app.services.triage_service import triage_patient


load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

client = genai.Client(
    api_key=GEMINI_API_KEY
)


def get_next_working_day(schedule):
    """
    Finds the next valid working date based on the doctor's
    weekly schedule and the current time.

    If today is a working day but the doctor's working hours
    have already ended, today's date is skipped.
    """

    if not schedule:
        return None

    today = date.today()
    current_time = datetime.now().time()

    weekday_numbers = {
        "Monday": 0,
        "Tuesday": 1,
        "Wednesday": 2,
        "Thursday": 3,
        "Friday": 4,
        "Saturday": 5,
        "Sunday": 6
    }

    available_days = {}

    for item in schedule:

        if item.get("is_available") is not True:
            continue

        day_name = item.get("day_of_week")

        if day_name not in weekday_numbers:
            continue

        try:
            start_time = datetime.strptime(
                item.get("start_time"),
                "%H:%M:%S"
            ).time()

            end_time = datetime.strptime(
                item.get("end_time"),
                "%H:%M:%S"
            ).time()

        except (TypeError, ValueError):
            continue

        available_days[
            weekday_numbers[day_name]
        ] = {
            "start_time": start_time,
            "end_time": end_time
        }

    if not available_days:
        return None

    # ---------------------------------------------------------
    # Check today first
    # ---------------------------------------------------------

    today_weekday = today.weekday()

    if today_weekday in available_days:

        today_schedule = available_days[
            today_weekday
        ]

        start_time = today_schedule["start_time"]
        end_time = today_schedule["end_time"]

        # If working hours have not started yet,
        # today is still a valid appointment date.
        if current_time < start_time:
            return today

        # If the doctor is currently working,
        # today is still a valid appointment date.
        if start_time <= current_time < end_time:
            return today

        # If current time is equal to or after the
        # doctor's closing time, skip today.

    # ---------------------------------------------------------
    # Search the next 6 days
    # ---------------------------------------------------------

    for offset in range(1, 7):

        candidate_date = (
            today + timedelta(days=offset)
        )

        if candidate_date.weekday() in available_days:

            return candidate_date

    return None


def route_triage_to_hospital(triage_result):
    """
    Takes the triage result and routes the patient to the
    appropriate hospital department, doctor and available
    appointment slots.
    """

    if hasattr(triage_result, "model_dump"):
        triage_data = triage_result.model_dump()
    else:
        triage_data = triage_result.dict()

    department = triage_data.get(
        "recommended_department",
        "General Medicine"
    )

    # ---------------------------------------------------------
    # Determine department query
    # ---------------------------------------------------------

    if "cardiology" in department.lower():
        hospital_query = "Show me Cardiology doctors"

    elif "dermatology" in department.lower():
        hospital_query = "Show me Dermatology doctors"

    elif "neurology" in department.lower():
        hospital_query = "Show me Neurology doctors"

    elif "orthopedic" in department.lower():
        hospital_query = "Show me Orthopedic doctors"

    elif "pediatrics" in department.lower():
        hospital_query = "Show me Pediatrics doctors"

    elif "gynecology" in department.lower():
        hospital_query = "Show me Gynecology doctors"

    else:
        hospital_query = "Show me General Medicine doctors"

    # ---------------------------------------------------------
    # Find matching doctors
    # ---------------------------------------------------------

    doctor_result = hospital_agent(
        hospital_query
    )

    doctors = doctor_result.get(
        "doctors",
        []
    )

    if not doctors:

        return {
            "agent": "Main AI Agent",
            "triage": triage_data,
            "hospital_routing": {
                "recommended_department": department,
                "doctor_search": doctor_result,
                "availability": None,
                "appointment_slots": None
            }
        }

    # ---------------------------------------------------------
    # Select first matching doctor
    # ---------------------------------------------------------

    selected_doctor = doctors[0]

    doctor_name = selected_doctor.get(
        "name"
    )

    # ---------------------------------------------------------
    # Get doctor's weekly availability
    # ---------------------------------------------------------

    availability_query = (
        f"Show me {doctor_name}'s availability"
    )

    availability_result = hospital_agent(
        availability_query
    )

    schedule = availability_result.get(
        "schedule",
        []
    )

    # ---------------------------------------------------------
    # Find next valid working date
    # ---------------------------------------------------------

    next_working_date = get_next_working_day(
        schedule
    )

    slot_result = None

    # ---------------------------------------------------------
    # Get appointment slots
    # ---------------------------------------------------------

    if next_working_date:

        day_name = next_working_date.strftime(
            "%A"
        )

        slot_query = (
            f"What appointment slots are available "
            f"for {doctor_name} on {day_name}?"
        )

        slot_result = hospital_agent(
            slot_query
        )

    return {
        "agent": "Main AI Agent",

        "triage": triage_data,

        "hospital_routing": {
            "recommended_department": department,

            "doctor_search": doctor_result,

            "selected_doctor": selected_doctor,

            "availability": availability_result,

            "next_available_date": (
                str(next_working_date)
                if next_working_date
                else None
            ),

            "appointment_slots": slot_result
        }
    }


def main_agent(user_query: str):

    prompt = f"""
You are the Main AI Agent of MEDIFLOW AI,
an AI-powered Hospital Management System.

Your job is to classify the user's query and decide
which specialized agent or service should handle it.

Available agents/services:

1. Hospital Agent
   Handles:
   - Patients
   - Doctors
   - Appointments
   - Medical information
   - Hospital operations
   - Admissions
   - Doctor availability
   - Appointment slots

2. Finance Agent
   Handles:
   - Revenue
   - Income
   - Expenses
   - Billing
   - Payments
   - Financial information

3. Customer Support Agent
   Handles:
   - Help
   - Support
   - Problems
   - Issues
   - Complaints

4. Triage Service
   Handles:
   - Patient symptom assessment
   - Urgency estimation
   - Emergency symptom identification
   - Recommended medical department
   - Initial triage assistance

Important routing rule:

If the user describes symptoms, asks how urgent
their symptoms are, asks which department they
should visit, or asks for symptom-based medical
guidance, select TRIAGE.

Examples:

"I have severe chest pain"
"I have difficulty breathing"
"I have skin rash and itching"
"I have dizziness"
"How urgent are my symptoms?"
"Which department should I visit for these symptoms?"

User Query:
"{user_query}"

Respond with ONLY one of these exact values:

HOSPITAL
FINANCE
SUPPORT
TRIAGE
"""

    try:

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt
        )

        selected_agent = response.text.strip().upper()

        if selected_agent == "HOSPITAL":

            return hospital_agent(
                user_query
            )

        elif selected_agent == "FINANCE":

            return finance_agent(
                user_query
            )

        elif selected_agent == "SUPPORT":

            return support_agent(
                user_query
            )

        elif selected_agent == "TRIAGE":

            triage_result = triage_patient(
                user_query
            )

            return route_triage_to_hospital(
                triage_result
            )

        else:

            return {
                "agent": "Main AI Agent",
                "message": (
                    "I could not determine the "
                    "appropriate agent."
                )
            }

    except Exception as e:

        return {
            "agent": "Main AI Agent",
            "message": (
                "An error occurred while processing "
                "the AI request."
            ),
            "error": str(e)
        }
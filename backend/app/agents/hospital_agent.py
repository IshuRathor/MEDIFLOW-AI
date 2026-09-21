from datetime import datetime, date, timedelta, time
import re

from app.database.db import SessionLocal
from app.models.patient import Patient
from app.models.doctor import Doctor
from app.models.appointment import Appointment
from app.models.availability import DoctorAvailability


def hospital_agent(user_query: str):
    """
    Handles hospital-related queries and retrieves
    actual patient, doctor and appointment data from PostgreSQL.
    """

    query = user_query.lower().strip()

    db = SessionLocal()

    try:

        # =====================================================
        # APPOINTMENT BOOKING
        # =====================================================

        if (
            "book appointment" in query
            or "book an appointment" in query
            or "schedule appointment" in query
            or "schedule an appointment" in query
            or "make appointment" in query
            or "make an appointment" in query
            or "appointment booking" in query
            or "book my appointment" in query
        ):

            # -------------------------------------------------
            # Find patient
            # -------------------------------------------------

            patient = None

            patient_id_match = re.search(
                r"\bpatient\s*(?:id\s*)?#?\s*(\d+)\b",
                query
            )

            if patient_id_match:
                patient = db.query(Patient).filter(
                    Patient.id == int(patient_id_match.group(1))
                ).first()

            if not patient:
                patients = db.query(Patient).all()

                for item in patients:
                    patient_name = item.name.lower().strip()
                    name_parts = (
                        patient_name.replace("dr.", "").split()
                    )

                    if patient_name in query:
                        patient = item
                        break

                    if (
                        len(name_parts) >= 2
                        and all(part in query for part in name_parts)
                    ):
                        patient = item
                        break

            if not patient:
                return {
                    "agent": "Hospital Agent",
                    "metric": "Appointment Booking",
                    "message": (
                        "Please provide a valid patient ID or patient name. "
                        "For example: Book an appointment for patient 1 "
                        "with Dr. Amit Verma on Monday at 10:30 AM."
                    )
                }

            # -------------------------------------------------
            # Find doctor
            # -------------------------------------------------

            doctors = db.query(Doctor).all()
            selected_doctor = None

            for doctor in doctors:
                doctor_name = doctor.name.lower()

                if doctor_name in query:
                    selected_doctor = doctor
                    break

                name_parts = doctor_name.replace("dr.", "").split()

                if (
                    len(name_parts) >= 2
                    and all(part in query for part in name_parts)
                ):
                    selected_doctor = doctor
                    break

            if not selected_doctor:
                return {
                    "agent": "Hospital Agent",
                    "metric": "Appointment Booking",
                    "patient_id": patient.id,
                    "patient_name": patient.name,
                    "message": (
                        "Please provide the doctor's name. "
                        "For example: Book an appointment for patient 1 "
                        "with Dr. Amit Verma on Monday at 10:30 AM."
                    )
                }

            # -------------------------------------------------
            # Parse date
            # -------------------------------------------------

            target_date = None

            if "today" in query:
                target_date = date.today()

            if not target_date:
                date_match = re.search(
                    r"\b(20\d{2})-(\d{2})-(\d{2})\b",
                    query
                )

                if date_match:
                    try:
                        target_date = datetime.strptime(
                            date_match.group(0),
                            "%Y-%m-%d"
                        ).date()
                    except ValueError:
                        target_date = None

            if not target_date:
                month_pattern = (
                    r"\b(\d{1,2})\s+"
                    r"(january|february|march|april|may|june|july|"
                    r"august|september|october|november|december)"
                    r"\s+(20\d{2})\b"
                )

                date_match = re.search(month_pattern, query)

                if date_match:
                    try:
                        target_date = datetime.strptime(
                            date_match.group(0),
                            "%d %B %Y"
                        ).date()
                    except ValueError:
                        target_date = None

            weekday_numbers = {
                "monday": 0,
                "tuesday": 1,
                "wednesday": 2,
                "thursday": 3,
                "friday": 4,
                "saturday": 5,
                "sunday": 6
            }

            weekday_match = re.search(
                r"\b(monday|tuesday|wednesday|thursday|friday|"
                r"saturday|sunday)\b",
                query
            )

            if not target_date and weekday_match:
                requested_weekday = weekday_match.group(1)
                days_ahead = (
                    weekday_numbers[requested_weekday]
                    - date.today().weekday()
                ) % 7

                target_date = date.today() + timedelta(days=days_ahead)

            if not target_date:
                return {
                    "agent": "Hospital Agent",
                    "metric": "Appointment Booking",
                    "patient_id": patient.id,
                    "patient_name": patient.name,
                    "doctor_id": selected_doctor.id,
                    "doctor_name": selected_doctor.name,
                    "message": (
                        "Please provide the appointment date or day. "
                        "For example: Monday or 2026-09-21."
                    )
                }

            # -------------------------------------------------
            # Parse appointment time
            # -------------------------------------------------

            requested_time = None

            time_match = re.search(
                r"\b([01]\d|2[0-3]):([0-5]\d)\b",
                query
            )

            if time_match:
                requested_time = datetime.strptime(
                    time_match.group(0),
                    "%H:%M"
                ).time()

            if not requested_time:
                time_12h_match = re.search(
                    r"\b(1[0-2]|[1-9])(?:[:.]([0-5]\d))?\s*(am|pm)\b",
                    query
                )

                if time_12h_match:
                    hour = int(time_12h_match.group(1))
                    minute = int(time_12h_match.group(2) or 0)
                    period = time_12h_match.group(3)

                    if period == "pm" and hour != 12:
                        hour += 12
                    elif period == "am" and hour == 12:
                        hour = 0

                    requested_time = time(hour, minute)

            if not requested_time:
                return {
                    "agent": "Hospital Agent",
                    "metric": "Appointment Booking",
                    "patient_id": patient.id,
                    "patient_name": patient.name,
                    "doctor_id": selected_doctor.id,
                    "doctor_name": selected_doctor.name,
                    "date": str(target_date),
                    "message": (
                        "Please provide the appointment time. "
                        "For example: 10:30 AM or 10:30."
                    )
                }

            appointment_datetime = datetime.combine(
                target_date,
                requested_time
            )

            # -------------------------------------------------
            # Check doctor availability
            # -------------------------------------------------

            day_name = target_date.strftime("%A")

            availability = db.query(
                DoctorAvailability
            ).filter(
                DoctorAvailability.doctor_id == selected_doctor.id,
                DoctorAvailability.day_of_week == day_name,
                DoctorAvailability.is_available == True
            ).first()

            if not availability:
                return {
                    "agent": "Hospital Agent",
                    "metric": "Appointment Booking",
                    "patient_id": patient.id,
                    "patient_name": patient.name,
                    "doctor_id": selected_doctor.id,
                    "doctor_name": selected_doctor.name,
                    "date": str(target_date),
                    "time": requested_time.strftime("%H:%M"),
                    "status": "Not Booked",
                    "message": (
                        f"{selected_doctor.name} is not available "
                        f"on {day_name}."
                    )
                }

            if not (
                availability.start_time
                <= requested_time
                < availability.end_time
            ):
                return {
                    "agent": "Hospital Agent",
                    "metric": "Appointment Booking",
                    "patient_id": patient.id,
                    "patient_name": patient.name,
                    "doctor_id": selected_doctor.id,
                    "doctor_name": selected_doctor.name,
                    "date": str(target_date),
                    "time": requested_time.strftime("%H:%M"),
                    "status": "Not Booked",
                    "message": (
                        f"{selected_doctor.name} is available on "
                        f"{day_name} only between "
                        f"{availability.start_time.strftime('%H:%M')} "
                        f"and {availability.end_time.strftime('%H:%M')}."
                    )
                }

            # -------------------------------------------------
            # Validate 30-minute appointment slot
            # -------------------------------------------------

            minutes_from_start = (
                (
                    requested_time.hour
                    - availability.start_time.hour
                ) * 60
                + requested_time.minute
                - availability.start_time.minute
            )

            if minutes_from_start % 30 != 0:
                return {
                    "agent": "Hospital Agent",
                    "metric": "Appointment Booking",
                    "patient_id": patient.id,
                    "patient_name": patient.name,
                    "doctor_id": selected_doctor.id,
                    "doctor_name": selected_doctor.name,
                    "date": str(target_date),
                    "time": requested_time.strftime("%H:%M"),
                    "status": "Not Booked",
                    "message": (
                        "Appointments can currently be booked only "
                        "in 30-minute slots, such as 09:00, 09:30, "
                        "10:00, 10:30."
                    )
                }

            # -------------------------------------------------
            # Doctor conflict check
            # -------------------------------------------------

            doctor_conflict = db.query(Appointment).filter(
                Appointment.doctor_id == selected_doctor.id,
                Appointment.appointment_date == appointment_datetime,
                Appointment.status == "Scheduled"
            ).first()

            if doctor_conflict:
                return {
                    "agent": "Hospital Agent",
                    "metric": "Appointment Booking",
                    "patient_id": patient.id,
                    "patient_name": patient.name,
                    "doctor_id": selected_doctor.id,
                    "doctor_name": selected_doctor.name,
                    "date": str(target_date),
                    "time": requested_time.strftime("%H:%M"),
                    "status": "Not Booked",
                    "message": (
                        "Doctor is already booked for this date and time."
                    )
                }

            # -------------------------------------------------
            # Patient conflict check
            # -------------------------------------------------

            patient_conflict = db.query(Appointment).filter(
                Appointment.patient_id == patient.id,
                Appointment.appointment_date == appointment_datetime,
                Appointment.status == "Scheduled"
            ).first()

            if patient_conflict:
                return {
                    "agent": "Hospital Agent",
                    "metric": "Appointment Booking",
                    "patient_id": patient.id,
                    "patient_name": patient.name,
                    "doctor_id": selected_doctor.id,
                    "doctor_name": selected_doctor.name,
                    "date": str(target_date),
                    "time": requested_time.strftime("%H:%M"),
                    "status": "Not Booked",
                    "message": (
                        "Patient already has an appointment "
                        "at this date and time."
                    )
                }

            # -------------------------------------------------
            # Create appointment
            # -------------------------------------------------

            new_appointment = Appointment(
                patient_id=patient.id,
                doctor_id=selected_doctor.id,
                appointment_date=appointment_datetime,
                reason="AI-assisted appointment booking",
                notes="Booked through MEDIFLOW AI Hospital Agent",
                status="Scheduled"
            )

            db.add(new_appointment)
            db.commit()
            db.refresh(new_appointment)

            return {
                "agent": "Hospital Agent",
                "metric": "Appointment Booking",
                "status": "Booked",
                "message": "Appointment booked successfully.",
                "appointment": {
                    "id": new_appointment.id,
                    "patient_id": patient.id,
                    "patient_name": patient.name,
                    "doctor_id": selected_doctor.id,
                    "doctor_name": selected_doctor.name,
                    "specialization": selected_doctor.specialization,
                    "appointment_date": new_appointment.appointment_date,
                    "reason": new_appointment.reason,
                    "status": new_appointment.status,
                    "notes": new_appointment.notes
                }
            }


        # =====================================================
        # APPOINTMENT SLOT RECOMMENDATION
        # =====================================================

        if (
            "available slots" in query
            or "appointment slots" in query
            or "appointment slot" in query
            or "which time" in query
            or "what time" in query
            or "available time" in query
            or "free slots" in query
        ):

            # -------------------------------------------------
            # Find doctor from the query
            # -------------------------------------------------

            doctors = db.query(Doctor).all()
            selected_doctor = None

            for doctor in doctors:
                doctor_name = doctor.name.lower()

                if doctor_name in query:
                    selected_doctor = doctor
                    break

                name_parts = doctor_name.replace("dr.", "").split()

                if (
                    len(name_parts) >= 2
                    and all(part in query for part in name_parts)
                ):
                    selected_doctor = doctor
                    break

            if not selected_doctor:
                return {
                    "agent": "Hospital Agent",
                    "metric": "Appointment Slot Recommendation",
                    "message": (
                        "Please provide the doctor's name. For example: "
                        "What appointment slots are available for Dr. Amit Verma on Monday?"
                    )
                }

            # -------------------------------------------------
            # Parse date
            # -------------------------------------------------

            target_date = None

            if "today" in query:
                target_date = date.today()

            if not target_date:
                date_match = re.search(
                    r"\b(20\d{2})-(\d{2})-(\d{2})\b",
                    query
                )

                if date_match:
                    try:
                        target_date = datetime.strptime(
                            date_match.group(0),
                            "%Y-%m-%d"
                        ).date()
                    except ValueError:
                        target_date = None

            if not target_date:
                month_pattern = (
                    r"\b(\d{1,2})\s+"
                    r"(january|february|march|april|may|june|july|"
                    r"august|september|october|november|december)"
                    r"\s+(20\d{2})\b"
                )

                date_match = re.search(
                    month_pattern,
                    query
                )

                if date_match:
                    try:
                        target_date = datetime.strptime(
                            date_match.group(0),
                            "%d %B %Y"
                        ).date()
                    except ValueError:
                        target_date = None

            # -------------------------------------------------
            # Parse day of week
            # -------------------------------------------------

            target_day = None

            weekday_pattern = (
                r"\b(monday|tuesday|wednesday|thursday|friday|"
                r"saturday|sunday)\b"
            )

            weekday_match = re.search(weekday_pattern, query)

            if weekday_match:
                target_day = weekday_match.group(1).capitalize()

            if target_date:
                day_name = target_date.strftime("%A")
            elif target_day:
                day_name = target_day
            else:
                return {
                    "agent": "Hospital Agent",
                    "metric": "Appointment Slot Recommendation",
                    "doctor_id": selected_doctor.id,
                    "doctor_name": selected_doctor.name,
                    "message": (
                        "Please provide a date or day. For example: "
                        "What appointment slots are available for Dr. Amit Verma on Monday?"
                    )
                }

            # -------------------------------------------------
            # Find doctor's working hours
            # -------------------------------------------------

            availability = db.query(
                DoctorAvailability
            ).filter(
                DoctorAvailability.doctor_id == selected_doctor.id,
                DoctorAvailability.day_of_week == day_name,
                DoctorAvailability.is_available == True
            ).first()

            if not availability:
                return {
                    "agent": "Hospital Agent",
                    "metric": "Appointment Slot Recommendation",
                    "doctor_id": selected_doctor.id,
                    "doctor_name": selected_doctor.name,
                    "date": str(target_date) if target_date else None,
                    "day": day_name,
                    "available_slots": [],
                    "message": (
                        f"{selected_doctor.name} is not available on {day_name}."
                    )
                }

            # -------------------------------------------------
            # A slot is treated as 30 minutes for now
            # -------------------------------------------------

            slot_duration = timedelta(minutes=30)

            # If the user gave only a weekday (for example,
            # "on Monday"), resolve it to the next occurrence of
            # that weekday. This lets us check real bookings for
            # that upcoming day instead of accidentally checking
            # today's date.
            if target_date:
                base_date = target_date
            else:
                today = date.today()
                weekday_numbers = {
                    "Monday": 0,
                    "Tuesday": 1,
                    "Wednesday": 2,
                    "Thursday": 3,
                    "Friday": 4,
                    "Saturday": 5,
                    "Sunday": 6
                }

                days_ahead = (
                    weekday_numbers[day_name] - today.weekday()
                ) % 7

                base_date = today + timedelta(days=days_ahead)
                target_date = base_date

            start_datetime = datetime.combine(
                base_date,
                availability.start_time
            )
            end_datetime = datetime.combine(
                base_date,
                availability.end_time
            )

            # -------------------------------------------------
            # Get scheduled appointments for this doctor/day
            # -------------------------------------------------

            scheduled_appointments = db.query(Appointment).filter(
                Appointment.doctor_id == selected_doctor.id,
                Appointment.status == "Scheduled",
                Appointment.appointment_date >= start_datetime,
                Appointment.appointment_date < end_datetime
            ).all()

            booked_times = {
                appointment.appointment_date.replace(tzinfo=None).time()
                for appointment in scheduled_appointments
            }

            # -------------------------------------------------
            # Generate free 30-minute slots
            # -------------------------------------------------

            available_slots = []
            current_slot = start_datetime

            while current_slot + slot_duration <= end_datetime:
                slot_time = current_slot.time()

                if slot_time not in booked_times:
                    available_slots.append(
                        current_slot.strftime("%H:%M")
                    )

                current_slot += slot_duration

            return {
                "agent": "Hospital Agent",
                "metric": "Appointment Slot Recommendation",
                "doctor_id": selected_doctor.id,
                "doctor_name": selected_doctor.name,
                "specialization": selected_doctor.specialization,
                "date": str(target_date) if target_date else None,
                "day": day_name,
                "working_hours": {
                    "start": availability.start_time.strftime("%H:%M"),
                    "end": availability.end_time.strftime("%H:%M")
                },
                "slot_duration_minutes": 30,
                "booked_slots": sorted(
                    [time_value.strftime("%H:%M") for time_value in booked_times]
                ),
                "available_slots": available_slots,
                "count": len(available_slots),
                "message": (
                    f"{len(available_slots)} appointment slots are available "
                    f"for {selected_doctor.name} on {day_name}."
                )
            }


        # =====================================================
        # DOCTOR AVAILABILITY / WORKING HOURS
        # =====================================================

        if (
            "availability" in query
            or "available" in query
            or "working hours" in query
            or "working time" in query
        ):

            # -------------------------------------------------
            # Find doctor from the query
            # -------------------------------------------------

            doctors = db.query(Doctor).all()
            selected_doctor = None

            for doctor in doctors:
                doctor_name = doctor.name.lower()

                if doctor_name in query:
                    selected_doctor = doctor
                    break

                name_parts = doctor_name.replace("dr.", "").split()

                if (
                    len(name_parts) >= 2
                    and all(part in query for part in name_parts)
                ):
                    selected_doctor = doctor
                    break

            # -------------------------------------------------
            # Parse optional date
            # -------------------------------------------------

            target_date = None

            if "today" in query:
                target_date = date.today()

            if not target_date:
                date_match = re.search(
                    r"\b(20\d{2})-(\d{2})-(\d{2})\b",
                    query
                )

                if date_match:
                    try:
                        target_date = datetime.strptime(
                            date_match.group(0),
                            "%Y-%m-%d"
                        ).date()
                    except ValueError:
                        target_date = None

            if not target_date:
                month_pattern = (
                    r"\b(\d{1,2})\s+"
                    r"(january|february|march|april|may|june|july|"
                    r"august|september|october|november|december)"
                    r"\s+(20\d{2})\b"
                )

                date_match = re.search(
                    month_pattern,
                    query
                )

                if date_match:
                    date_text = date_match.group(0)

                    try:
                        target_date = datetime.strptime(
                            date_text,
                            "%d %B %Y"
                        ).date()
                    except ValueError:
                        target_date = None

            # -------------------------------------------------
            # Parse optional day of week
            # -------------------------------------------------

            target_day = None

            weekday_pattern = (
                r"\b(monday|tuesday|wednesday|thursday|friday|"
                r"saturday|sunday)\b"
            )

            weekday_match = re.search(weekday_pattern, query)

            if weekday_match:
                target_day = weekday_match.group(1).capitalize()

            # -------------------------------------------------
            # Parse optional time
            # -------------------------------------------------

            requested_time = None

            # Supports 24-hour format: 11:00 or 17:30
            time_match = re.search(
                r"\b([01]\d|2[0-3]):([0-5]\d)\b",
                query
            )

            if time_match:
                requested_time = datetime.strptime(
                    time_match.group(0),
                    "%H:%M"
                ).time()

            # Supports 12-hour format: 11 AM, 11:30 AM, 5 PM
            if not requested_time:
                time_12h_match = re.search(
                    r"\b(1[0-2]|[1-9])(?:[:.]([0-5]\d))?\s*"
                    r"(am|pm)\b",
                    query
                )

                if time_12h_match:
                    hour = int(time_12h_match.group(1))
                    minute = int(time_12h_match.group(2) or 0)
                    period = time_12h_match.group(3)

                    if period == "pm" and hour != 12:
                        hour += 12
                    elif period == "am" and hour == 12:
                        hour = 0

                    requested_time = time(
                        hour,
                        minute
                    )

            # -------------------------------------------------
            # Check a specific doctor/date/time OR doctor/day/time
            # -------------------------------------------------

            if selected_doctor and (target_date or target_day):

                day_name = (
                    target_date.strftime("%A")
                    if target_date
                    else target_day
                )

                availability = db.query(
                    DoctorAvailability
                ).filter(
                    DoctorAvailability.doctor_id == selected_doctor.id,
                    DoctorAvailability.day_of_week == day_name,
                    DoctorAvailability.is_available == True
                ).first()

                if not availability:
                    return {
                        "agent": "Hospital Agent",
                        "metric": "Doctor Availability",
                        "doctor_id": selected_doctor.id,
                        "doctor_name": selected_doctor.name,
                        "date": str(target_date) if target_date else None,
                        "day": day_name,
                        "available": False,
                        "message": (
                            f"{selected_doctor.name} is not available "
                            f"on {day_name}."
                        )
                    }

                if requested_time:
                    is_within_hours = (
                        availability.start_time
                        <= requested_time
                        <= availability.end_time
                    )

                    return {
                        "agent": "Hospital Agent",
                        "metric": "Doctor Availability",
                        "doctor_id": selected_doctor.id,
                        "doctor_name": selected_doctor.name,
                        "specialization": selected_doctor.specialization,
                        "date": str(target_date) if target_date else None,
                        "day": day_name,
                        "requested_time": str(requested_time),
                        "working_hours": {
                            "start": str(availability.start_time),
                            "end": str(availability.end_time)
                        },
                        "available": is_within_hours,
                        "message": (
                            f"{selected_doctor.name} is available on "
                            f"{day_name} from "
                            f"{availability.start_time.strftime('%H:%M')} "
                            f"to {availability.end_time.strftime('%H:%M')}."
                            if is_within_hours
                            else
                            f"{selected_doctor.name} is not available at "
                            f"{requested_time.strftime('%H:%M')} on {day_name}. "
                            f"Working hours are "
                            f"{availability.start_time.strftime('%H:%M')} "
                            f"to {availability.end_time.strftime('%H:%M')}."
                        )
                    }

                return {
                    "agent": "Hospital Agent",
                    "metric": "Doctor Availability",
                    "doctor_id": selected_doctor.id,
                    "doctor_name": selected_doctor.name,
                    "specialization": selected_doctor.specialization,
                    "date": str(target_date) if target_date else None,
                    "day": day_name,
                    "working_hours": {
                        "start": str(availability.start_time),
                        "end": str(availability.end_time)
                    },
                    "available": True,
                    "message": (
                        f"{selected_doctor.name} is available on "
                        f"{day_name} from "
                        f"{availability.start_time.strftime('%H:%M')} "
                        f"to {availability.end_time.strftime('%H:%M')}."
                    )
                }

            # -------------------------------------------------
            # Show weekly availability for a specific doctor
            # -------------------------------------------------

            if selected_doctor:
                availability_list = db.query(
                    DoctorAvailability
                ).filter(
                    DoctorAvailability.doctor_id == selected_doctor.id
                ).all()

                if not availability_list:
                    return {
                        "agent": "Hospital Agent",
                        "metric": "Doctor Availability",
                        "doctor_id": selected_doctor.id,
                        "doctor_name": selected_doctor.name,
                        "count": 0,
                        "message": (
                            f"No availability schedule found for "
                            f"{selected_doctor.name}."
                        )
                    }

                schedule = [
                    {
                        "day_of_week": item.day_of_week,
                        "start_time": str(item.start_time),
                        "end_time": str(item.end_time),
                        "is_available": item.is_available
                    }
                    for item in availability_list
                ]

                return {
                    "agent": "Hospital Agent",
                    "metric": "Doctor Availability",
                    "doctor_id": selected_doctor.id,
                    "doctor_name": selected_doctor.name,
                    "specialization": selected_doctor.specialization,
                    "schedule": schedule,
                    "count": len(schedule),
                    "message": (
                        f"Availability schedule retrieved for "
                        f"{selected_doctor.name}."
                    )
                }

            # -------------------------------------------------
            # No doctor specified
            # -------------------------------------------------

            return {
                "agent": "Hospital Agent",
                "metric": "Doctor Availability",
                "message": (
                    "Please provide the doctor's name. For example: "
                    "Show me Dr. Amit Verma's availability."
                )
            }


        # =====================================================
        # APPOINTMENTS BY DATE
        # =====================================================

        if "appointment" in query:

            target_date = None

            if "today" in query:
                target_date = date.today()

            if not target_date:
                date_match = re.search(
                    r"\b(20\d{2})-(\d{2})-(\d{2})\b",
                    query
                )

                if date_match:
                    try:
                        target_date = datetime.strptime(
                            date_match.group(0),
                            "%Y-%m-%d"
                        ).date()
                    except ValueError:
                        target_date = None

            if not target_date:

                month_pattern = (
                    r"\b(\d{1,2})\s+"
                    r"(january|february|march|april|may|june|july|"
                    r"august|september|october|november|december)"
                    r"\s+(20\d{2})\b"
                )

                date_match = re.search(
                    month_pattern,
                    query
                )

                if date_match:

                    date_text = date_match.group(0)

                    try:
                        target_date = datetime.strptime(
                            date_text,
                            "%d %B %Y"
                        ).date()
                    except ValueError:
                        target_date = None

            if target_date:

                start_datetime = datetime.combine(
                    target_date,
                    datetime.min.time()
                )

                end_datetime = start_datetime + timedelta(days=1)

                appointments = db.query(Appointment).filter(
                    Appointment.appointment_date >= start_datetime,
                    Appointment.appointment_date < end_datetime
                ).all()

                appointment_list = []

                for appointment in appointments:

                    patient = db.query(Patient).filter(
                        Patient.id == appointment.patient_id
                    ).first()

                    doctor = db.query(Doctor).filter(
                        Doctor.id == appointment.doctor_id
                    ).first()

                    appointment_list.append({
                        "appointment_id": appointment.id,
                        "patient_id": appointment.patient_id,
                        "patient_name": (
                            patient.name
                            if patient else None
                        ),
                        "doctor_id": appointment.doctor_id,
                        "doctor_name": (
                            doctor.name
                            if doctor else None
                        ),
                        "specialization": (
                            doctor.specialization
                            if doctor else None
                        ),
                        "appointment_date": (
                            appointment.appointment_date
                        ),
                        "reason": appointment.reason,
                        "status": appointment.status,
                        "notes": appointment.notes
                    })

                if not appointment_list:
                    return {
                        "agent": "Hospital Agent",
                        "metric": "Appointment Date Search",
                        "date": str(target_date),
                        "count": 0,
                        "message": (
                            f"No appointments found for "
                            f"{target_date.strftime('%d %B %Y')}."
                        )
                    }

                return {
                    "agent": "Hospital Agent",
                    "metric": "Appointment Date Search",
                    "date": str(target_date),
                    "count": len(appointment_list),
                    "message": (
                        f"Appointments found for "
                        f"{target_date.strftime('%d %B %Y')}."
                    ),
                    "appointments": appointment_list
                }


        # =====================================================
        # APPOINTMENTS BY STATUS
        # =====================================================

        if "appointment" in query:

            selected_status = None

            if "scheduled" in query:
                selected_status = "Scheduled"

            elif "cancelled" in query or "canceled" in query:
                selected_status = "Cancelled"

            elif "completed" in query:
                selected_status = "Completed"

            elif "pending" in query:
                selected_status = "Pending"

            if selected_status:

                appointments = db.query(Appointment).filter(
                    Appointment.status.ilike(selected_status)
                ).all()

                if not appointments:
                    return {
                        "agent": "Hospital Agent",
                        "metric": "Appointment Status Search",
                        "status": selected_status,
                        "count": 0,
                        "message": (
                            f"No {selected_status.lower()} "
                            f"appointments found."
                        )
                    }

                appointment_list = []

                for appointment in appointments:

                    patient = db.query(Patient).filter(
                        Patient.id == appointment.patient_id
                    ).first()

                    doctor = db.query(Doctor).filter(
                        Doctor.id == appointment.doctor_id
                    ).first()

                    appointment_list.append({
                        "appointment_id": appointment.id,
                        "patient_id": appointment.patient_id,
                        "patient_name": (
                            patient.name
                            if patient else None
                        ),
                        "doctor_id": appointment.doctor_id,
                        "doctor_name": (
                            doctor.name
                            if doctor else None
                        ),
                        "specialization": (
                            doctor.specialization
                            if doctor else None
                        ),
                        "appointment_date": (
                            appointment.appointment_date
                        ),
                        "reason": appointment.reason,
                        "status": appointment.status,
                        "notes": appointment.notes
                    })

                return {
                    "agent": "Hospital Agent",
                    "metric": "Appointment Status Search",
                    "status": selected_status,
                    "count": len(appointment_list),
                    "message": (
                        f"{selected_status} appointments "
                        f"retrieved successfully."
                    ),
                    "appointments": appointment_list
                }


        # =====================================================
        # SHOW ALL APPOINTMENTS
        # =====================================================

        if (
            "all appointments" in query
            or "show appointments" in query
            or "show all appointments" in query
        ):

            appointments = db.query(Appointment).all()

            if not appointments:
                return {
                    "agent": "Hospital Agent",
                    "message": "No appointments found in the database."
                }

            appointment_list = []

            for appointment in appointments:

                patient = db.query(Patient).filter(
                    Patient.id == appointment.patient_id
                ).first()

                doctor = db.query(Doctor).filter(
                    Doctor.id == appointment.doctor_id
                ).first()

                appointment_list.append({
                    "id": appointment.id,
                    "patient_id": appointment.patient_id,
                    "patient_name": patient.name if patient else None,
                    "doctor_id": appointment.doctor_id,
                    "doctor_name": doctor.name if doctor else None,
                    "specialization": (
                        doctor.specialization
                        if doctor else None
                    ),
                    "appointment_date": appointment.appointment_date,
                    "reason": appointment.reason,
                    "status": appointment.status,
                    "notes": appointment.notes
                })

            return {
                "agent": "Hospital Agent",
                "metric": "Appointments",
                "message": "Appointments retrieved successfully.",
                "count": len(appointment_list),
                "appointments": appointment_list
            }


        # =====================================================
        # SEARCH APPOINTMENTS BY DOCTOR NAME
        # =====================================================

        if (
            "appointment" in query
            and (
                "doctor" in query
                or "amit" in query
                or "verma" in query
            )
        ):

            search_text = query

            remove_phrases = [
                "show me",
                "show",
                "find",
                "search",
                "get",
                "the",
                "appointments",
                "appointment",
                "doctor",
                "doctors",
                "'s",
                "please"
            ]

            for phrase in remove_phrases:
                search_text = search_text.replace(phrase, " ")

            search_text = " ".join(search_text.split())

            if search_text:

                doctors = db.query(Doctor).filter(
                    Doctor.name.ilike(f"%{search_text}%")
                ).all()

                if not doctors:
                    return {
                        "agent": "Hospital Agent",
                        "metric": "Doctor Appointment Search",
                        "search": search_text,
                        "count": 0,
                        "message": (
                            f"No doctor found matching "
                            f"'{search_text}'."
                        )
                    }

                appointment_list = []

                for doctor in doctors:

                    appointments = db.query(Appointment).filter(
                        Appointment.doctor_id == doctor.id
                    ).all()

                    for appointment in appointments:

                        patient = db.query(Patient).filter(
                            Patient.id == appointment.patient_id
                        ).first()

                        appointment_list.append({
                            "appointment_id": appointment.id,
                            "doctor_id": doctor.id,
                            "doctor_name": doctor.name,
                            "specialization": doctor.specialization,
                            "patient_id": appointment.patient_id,
                            "patient_name": (
                                patient.name
                                if patient else None
                            ),
                            "appointment_date": (
                                appointment.appointment_date
                            ),
                            "reason": appointment.reason,
                            "status": appointment.status,
                            "notes": appointment.notes
                        })

                if not appointment_list:
                    return {
                        "agent": "Hospital Agent",
                        "metric": "Doctor Appointment Search",
                        "search": search_text,
                        "count": 0,
                        "message": (
                            f"No appointments found for "
                            f"Dr. {search_text}."
                        )
                    }

                return {
                    "agent": "Hospital Agent",
                    "metric": "Doctor Appointment Search",
                    "search": search_text,
                    "count": len(appointment_list),
                    "message": (
                        "Doctor appointments retrieved successfully."
                    ),
                    "appointments": appointment_list
                }


        # =====================================================
        # SEARCH APPOINTMENTS BY PATIENT NAME
        # =====================================================

        if (
            "appointment" in query
            and (
                "patient" in query
                or "rahul" in query
                or "sharma" in query
            )
        ):

            search_text = query

            remove_phrases = [
                "show me",
                "show",
                "find",
                "search",
                "get",
                "the",
                "appointments",
                "appointment",
                "patient",
                "patients",
                "'s",
                "please"
            ]

            for phrase in remove_phrases:
                search_text = search_text.replace(phrase, " ")

            search_text = " ".join(search_text.split())

            if search_text:

                patients = db.query(Patient).filter(
                    Patient.name.ilike(f"%{search_text}%")
                ).all()

                if not patients:
                    return {
                        "agent": "Hospital Agent",
                        "metric": "Patient Appointment Search",
                        "search": search_text,
                        "count": 0,
                        "message": (
                            f"No patient found matching "
                            f"'{search_text}'."
                        )
                    }

                appointment_list = []

                for patient in patients:

                    appointments = db.query(Appointment).filter(
                        Appointment.patient_id == patient.id
                    ).all()

                    for appointment in appointments:

                        doctor = db.query(Doctor).filter(
                            Doctor.id == appointment.doctor_id
                        ).first()

                        appointment_list.append({
                            "appointment_id": appointment.id,
                            "patient_id": patient.id,
                            "patient_name": patient.name,
                            "doctor_id": appointment.doctor_id,
                            "doctor_name": (
                                doctor.name
                                if doctor else None
                            ),
                            "specialization": (
                                doctor.specialization
                                if doctor else None
                            ),
                            "appointment_date": (
                                appointment.appointment_date
                            ),
                            "reason": appointment.reason,
                            "status": appointment.status,
                            "notes": appointment.notes
                        })

                if not appointment_list:
                    return {
                        "agent": "Hospital Agent",
                        "metric": "Patient Appointment Search",
                        "search": search_text,
                        "count": 0,
                        "message": (
                            f"No appointments found for "
                            f"'{search_text}'."
                        )
                    }

                return {
                    "agent": "Hospital Agent",
                    "metric": "Patient Appointment Search",
                    "search": search_text,
                    "count": len(appointment_list),
                    "message": (
                        "Patient appointments retrieved successfully."
                    ),
                    "appointments": appointment_list
                }


        # =====================================================
        # SHOW ALL PATIENTS
        # =====================================================

        if "all patients" in query or "show patients" in query:

            patients = db.query(Patient).all()

            if not patients:
                return {
                    "agent": "Hospital Agent",
                    "message": "No patients found in the database."
                }

            patient_list = []

            for patient in patients:
                patient_list.append({
                    "id": patient.id,
                    "name": patient.name,
                    "age": patient.age,
                    "gender": patient.gender,
                    "phone": patient.phone,
                    "email": patient.email
                })

            return {
                "agent": "Hospital Agent",
                "metric": "Patients",
                "message": "Patients retrieved successfully.",
                "count": len(patient_list),
                "patients": patient_list
            }


        # =====================================================
        # SEARCH SPECIFIC PATIENT BY NAME
        # =====================================================

        if "patient" in query:

            search_text = query

            remove_phrases = [
                "show me patient",
                "show patient",
                "find patient",
                "find the patient",
                "search patient",
                "search for patient",
                "get patient",
                "get the patient",
                "patient details",
                "patient detail",
                "please",
                "patient"
            ]

            for phrase in remove_phrases:
                search_text = search_text.replace(phrase, "")

            search_text = search_text.strip()

            if search_text:

                patients = db.query(Patient).filter(
                    Patient.name.ilike(f"%{search_text}%")
                ).all()

                if not patients:
                    return {
                        "agent": "Hospital Agent",
                        "metric": "Patient Search",
                        "search": search_text,
                        "count": 0,
                        "message": (
                            f"No patient found matching "
                            f"'{search_text}'."
                        )
                    }

                patient_list = []

                for patient in patients:
                    patient_list.append({
                        "id": patient.id,
                        "name": patient.name,
                        "age": patient.age,
                        "gender": patient.gender,
                        "phone": patient.phone,
                        "email": patient.email
                    })

                return {
                    "agent": "Hospital Agent",
                    "metric": "Patient Search",
                    "search": search_text,
                    "count": len(patient_list),
                    "message": "Patient search completed successfully.",
                    "patients": patient_list
                }

            return {
                "agent": "Hospital Agent",
                "message": (
                    "Please provide the patient's name. "
                    "For example: Show me patient Rahul Sharma."
                )
            }


        # =====================================================
        # SEARCH DOCTORS BY SPECIALIZATION
        # =====================================================

        if (
            "cardiologist" in query
            or "cardiology" in query
            or "orthopedic" in query
            or "orthopaedic" in query
            or "dermatologist" in query
            or "dermatology" in query
            or "neurologist" in query
            or "neurology" in query
            or "pediatrician" in query
            or "paediatrician" in query
            or "pediatrics" in query
            or "gynaecologist" in query
            or "gynecologist" in query
            or "gynaecology" in query
            or "gynecology" in query
        ):

            specialization_map = {
                "cardiologist": "Cardiology",
                "cardiology": "Cardiology",
                "orthopedic": "Orthopedic",
                "orthopaedic": "Orthopedic",
                "dermatologist": "Dermatology",
                "dermatology": "Dermatology",
                "neurologist": "Neurology",
                "neurology": "Neurology",
                "pediatrician": "Pediatrics",
                "paediatrician": "Pediatrics",
                "pediatrics": "Pediatrics",
                "gynaecologist": "Gynecology",
                "gynecologist": "Gynecology",
                "gynaecology": "Gynecology",
                "gynecology": "Gynecology"
            }

            selected_specialization = None

            for keyword, specialization in specialization_map.items():
                if keyword in query:
                    selected_specialization = specialization
                    break

            doctors = db.query(Doctor).filter(
                Doctor.specialization.ilike(
                    f"%{selected_specialization}%"
                )
            ).all()

            if not doctors:
                return {
                    "agent": "Hospital Agent",
                    "metric": "Doctor Search",
                    "specialization": selected_specialization,
                    "count": 0,
                    "message": (
                        f"No doctors found for "
                        f"{selected_specialization}."
                    )
                }

            doctor_list = []

            for doctor in doctors:
                doctor_list.append({
                    "id": doctor.id,
                    "name": doctor.name,
                    "specialization": doctor.specialization,
                    "phone": doctor.phone,
                    "email": doctor.email,
                    "department": doctor.department,
                    "experience_years": doctor.experience_years
                })

            return {
                "agent": "Hospital Agent",
                "metric": "Doctor Search",
                "specialization": selected_specialization,
                "count": len(doctor_list),
                "message": (
                    f"Doctors found for "
                    f"{selected_specialization}."
                ),
                "doctors": doctor_list
            }


        # =====================================================
        # SHOW ALL DOCTORS
        # =====================================================

        if "all doctors" in query or "show doctors" in query:

            doctors = db.query(Doctor).all()

            if not doctors:
                return {
                    "agent": "Hospital Agent",
                    "message": "No doctors found in the database."
                }

            doctor_list = []

            for doctor in doctors:
                doctor_list.append({
                    "id": doctor.id,
                    "name": doctor.name,
                    "specialization": doctor.specialization,
                    "phone": doctor.phone,
                    "email": doctor.email,
                    "department": doctor.department,
                    "experience_years": doctor.experience_years
                })

            return {
                "agent": "Hospital Agent",
                "metric": "Doctors",
                "message": "Doctors retrieved successfully.",
                "count": len(doctor_list),
                "doctors": doctor_list
            }


        # =====================================================
        # DOCTOR RELATED QUERY
        # =====================================================

        if "doctor" in query:

            return {
                "agent": "Hospital Agent",
                "message": (
                    "I can help with doctor information. "
                    "Try asking: Show me all doctors."
                )
            }


        # =====================================================
        # APPOINTMENT RELATED QUERY
        # =====================================================

        if "appointment" in query:

            return {
                "agent": "Hospital Agent",
                "message": (
                    "I can help with appointment information. "
                    "Try asking: Show me all appointments."
                )
            }


        # =====================================================
        # ADMISSION QUERY
        # =====================================================

        if "admission" in query or "admit" in query:

            return {
                "agent": "Hospital Agent",
                "message": (
                    "Patient admission management will be added soon."
                )
            }


        # =====================================================
        # DEFAULT RESPONSE
        # =====================================================

        return {
            "agent": "Hospital Agent",
            "message": (
                "I can help with patients, doctors, "
                "appointments and hospital operations."
            )
        }

    finally:
        db.close()
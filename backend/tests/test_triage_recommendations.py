import unittest
from datetime import datetime, time, timedelta
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.database.db import Base
from app.models.appointment import Appointment
from app.models.availability import DoctorAvailability
from app.models.doctor import Doctor
from app.models.patient import Patient
from app.services.triage_service import assess_patient_with_doctors


class TriageRecommendationTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.now = datetime(2026, 11, 25, 10)

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def assess(self, symptoms):
        return assess_patient_with_doctors(self.db, symptoms, now=self.now)

    def test_matches_reported_concern_to_registered_specialties(self):
        self.db.add_all([
            Doctor(name="First", specialization="General Medicine"),
            Doctor(name="Second", specialization="Internal Medicine"),
            Doctor(name="Heart", specialization="Cardiologist"),
            Doctor(name="Unrelated", specialization="Dermatology"),
        ])
        self.db.commit()
        fever = self.assess("High fever")
        self.assertEqual(fever.urgency, "High")
        self.assertEqual([doctor.name for doctor in fever.recommended_doctors], ["First", "Second"])
        self.assertEqual([doctor.name for doctor in self.assess("Heart-related symptoms").recommended_doctors], ["Heart"])
        oncology = self.assess("Questions about my existing cancer care")
        self.assertEqual(oncology.recommended_department, "Oncology")
        self.assertEqual(oncology.recommended_doctors, [])
        self.db.add(Doctor(name="Cancer care", specialization="Medical Oncology"))
        self.db.commit()
        doctor, = self.assess("Questions about my existing cancer care").recommended_doctors
        self.assertEqual(doctor.name, "Cancer care")
        self.assertEqual(doctor.availability, "unverified")
        self.assertEqual(doctor.upcoming_slots, [])

    def test_schedule_honors_past_times_exceptions_and_reservations(self):
        ready = Doctor(name="Ready", specialization="General Medicine", experience_years=8)
        blocked = Doctor(name="Blocked", specialization="General Medicine")
        patient = Patient(name="Private Patient")
        self.db.add_all([ready, blocked, patient])
        self.db.flush()
        today = self.now.date()
        tomorrow = today + timedelta(days=1)
        next_week = today + timedelta(days=7)
        self.db.add_all([
            DoctorAvailability(doctor_id=ready.id, day_of_week="Wednesday", start_time=time(9), end_time=time(12)),
            DoctorAvailability(doctor_id=ready.id, day_of_week="Wednesday", specific_date=next_week, start_time=time(9), end_time=time(12), is_available=False),
            DoctorAvailability(doctor_id=ready.id, day_of_week="Thursday", specific_date=tomorrow, start_time=time(13), end_time=time(14)),
            DoctorAvailability(doctor_id=blocked.id, day_of_week="Wednesday", specific_date=today, start_time=time(9), end_time=time(12), is_available=False),
            Appointment(patient_id=patient.id, doctor_id=ready.id, appointment_date=self.now.replace(minute=30), status="Scheduled"),
            Appointment(patient_id=patient.id, doctor_id=ready.id, appointment_date=self.now.replace(hour=11), status="Pending Doctor Approval"),
        ])
        self.db.commit()
        ready_result, blocked_result = self.assess("High fever").recommended_doctors
        self.assertEqual(ready_result.upcoming_slots, ["2026-11-25T11:30:00", "2026-11-26T13:00:00", "2026-11-26T13:30:00"])
        self.assertEqual(ready_result.experience_years, 8)
        self.assertEqual(ready_result.availability, "available")
        self.assertNotIn("Private Patient", ready_result.model_dump_json())
        self.assertEqual(blocked_result.availability, "no_slots")
        self.assertEqual(blocked_result.upcoming_slots, [])

    def test_other_emergency_skips_directory_lookup(self):
        with patch.object(self.db, "query", side_effect=AssertionError("Unexpected booking lookup")):
            result = self.assess("Existing cancer care and sudden facial drooping")
        self.assertEqual(result.urgency, "Emergency")
        self.assertEqual(result.recommended_doctors, [])
        self.assertIn("Do not wait", result.recommended_action)

    def test_chest_warning_matches_registered_cardiology_specializations_only(self):
        self.db.add_all([
            Doctor(name="General physician", specialization="General Medicine"),
            Doctor(name="Unrelated specialist", specialization="Dermatology", department="Cardiology"),
        ])
        self.db.commit()
        result = self.assess("pain in chest and high fever")
        self.assertEqual(result.urgency, "Emergency")
        self.assertEqual(result.recommended_department, "Emergency / Cardiology")
        self.assertEqual(result.recommended_doctors, [])
        self.assertIn("Do not wait", result.recommended_action)

        doctor = Doctor(name="Registered cardiologist", specialization="INTERVENTIONAL-CARDIOLOGY", experience_years=12)
        self.db.add(doctor)
        self.db.flush()
        self.db.add(DoctorAvailability(
            doctor_id=doctor.id, day_of_week="Wednesday", specific_date=self.now.date(),
            start_time=time(13), end_time=time(14),
        ))
        self.db.commit()
        result = self.assess("chest pressure")
        match, = result.recommended_doctors
        self.assertEqual((match.name, match.specialization, match.experience_years), (doctor.name, doctor.specialization, 12))
        self.assertEqual(match.availability, "available")
        self.assertEqual(match.upcoming_slots, ["2026-11-25T13:00:00", "2026-11-25T13:30:00"])

    def test_directory_failure_does_not_suppress_emergency_guidance(self):
        with patch.object(self.db, "query", side_effect=SQLAlchemyError("Directory unavailable")):
            result = self.assess("pain in chest")
        self.assertEqual(result.urgency, "Emergency")
        self.assertIn("Do not wait", result.recommended_action)
        self.assertIsNone(result.availability_window_days)

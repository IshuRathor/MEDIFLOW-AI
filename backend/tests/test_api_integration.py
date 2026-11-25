import unittest
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor
import os
import tempfile

from fastapi.testclient import TestClient
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database.db import Base
from app.models.audit import AuditLog
from app.models.ai import AIApproval, AIConversationMessage
from app.models.user import User
from app.models.patient import Patient
from app.models.doctor import Doctor
from app.models.appointment import Appointment
from app.models.availability import DoctorAvailability
from app.models.finance import Bill, Expense, Payment
from app.main import app
from app.core import security
from app.api import appointment, availability, bills, doctor, patients, payments


class ApiIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        cls.db_file.close()
        cls.engine = create_engine(
            f"sqlite:///{cls.db_file.name}",
            connect_args={"check_same_thread": False},
        )
        cls.session_factory = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=cls.engine,
        )
        Base.metadata.create_all(cls.engine)

        def override_db():
            db = cls.session_factory()
            try:
                yield db
            finally:
                db.close()

        for module in (
            security,
            appointment,
            availability,
            bills,
            doctor,
            patients,
            payments,
        ):
            app.dependency_overrides[module.get_db] = override_db

        cls.client = TestClient(app)
        app.state.audit_session_factory = cls.session_factory

    @classmethod
    def tearDownClass(cls):
        app.dependency_overrides.clear()
        if hasattr(app.state, "audit_session_factory"):
            del app.state.audit_session_factory
        Base.metadata.drop_all(cls.engine)
        cls.engine.dispose()
        if os.path.exists(cls.db_file.name):
            os.unlink(cls.db_file.name)

    def setUp(self):
        Base.metadata.drop_all(self.engine)
        Base.metadata.create_all(self.engine)
        self.client.post(
            "/api/auth/register",
            json={
                "full_name": "Integration Admin",
                "email": "admin@example.com",
                "password": "secure-password",
            },
        )
        response = self.client.post(
            "/api/auth/login",
            json={
                "email": "admin@example.com",
                "password": "secure-password",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.headers = {"Authorization": f"Bearer {response.json()['access_token']}"}

    def test_public_patient_registration_persists_linked_account(self):
        response = self.client.post(
            "/api/auth/register-patient",
            json={
                "full_name": "Public Patient",
                "email": "public.patient@example.com",
                "phone": "+1 555 0100",
                "password": "patient-password",
                "confirm_password": "patient-password",
            },
        )
        self.assertEqual(response.status_code, 201)
        created = response.json()
        self.assertEqual(created["role"], "patient")

        db = self.session_factory()
        try:
            user = db.query(User).filter(User.email == "public.patient@example.com").first()
            patient = db.query(Patient).filter(Patient.email == "public.patient@example.com").first()
            self.assertIsNotNone(user)
            self.assertIsNotNone(patient)
            self.assertNotEqual(user.password_hash, "patient-password")
            self.assertTrue(user.password_hash.startswith("pbkdf2_sha256$"))
            self.assertEqual(patient.user_id, user.id)
        finally:
            db.close()

    def test_public_patient_registration_rejects_duplicate_missing_invalid_and_elevated_roles(self):
        payload = {
            "full_name": "Public Patient",
            "email": "duplicate.patient@example.com",
            "phone": "+1 555 0101",
            "password": "patient-password",
            "confirm_password": "patient-password",
        }
        first = self.client.post("/api/auth/register-patient", json=payload)
        self.assertEqual(first.status_code, 201)
        duplicate = self.client.post("/api/auth/register-patient", json=payload)
        self.assertEqual(duplicate.status_code, 409)

        missing = self.client.post("/api/auth/register-patient", json={"email": "missing@example.com"})
        self.assertEqual(missing.status_code, 422)

        invalid_email = self.client.post(
            "/api/auth/register-patient",
            json={**payload, "email": "not-an-email"},
        )
        self.assertEqual(invalid_email.status_code, 422)

        mismatch = self.client.post(
            "/api/auth/register-patient",
            json={**payload, "email": "mismatch@example.com", "confirm_password": "different-password"},
        )
        self.assertEqual(mismatch.status_code, 422)

        for elevated_role in ("admin", "clinician", "staff"):
            elevated = self.client.post(
                "/api/auth/register-patient",
                json={**payload, "email": f"{elevated_role}@example.com", "role": elevated_role},
            )
            self.assertEqual(elevated.status_code, 422)

    def test_registered_patient_can_login_and_does_not_create_plaintext_password(self):
        registration = self.client.post(
            "/api/auth/register-patient",
            json={
                "full_name": "Login Patient",
                "email": "login.patient@example.com",
                "phone": "+1 555 0102",
                "password": "patient-password",
                "confirm_password": "patient-password",
            },
        )
        self.assertEqual(registration.status_code, 201)

        login = self.client.post(
            "/api/auth/login",
            json={
                "email": "login.patient@example.com",
                "password": "patient-password",
                "role": "patient",
            },
        )
        self.assertEqual(login.status_code, 200)
        self.assertEqual(login.json()["user"]["role"], "patient")

    def test_all_public_roles_register_with_expected_approval_status(self):
        registrations = [
            ("patient@example.com", "patient", None),
            ("doctor@example.com", "clinician", "Cardiology"),
            ("staff@example.com", "staff", None),
            ("pending-admin@example.com", "admin", None),
        ]
        for index, (email, role, specialization) in enumerate(registrations):
            payload = {
                "full_name": f"Public {role}",
                "email": email,
                "phone": f"+1 555 020{index}",
                "password": "secure-password",
                "confirm_password": "secure-password",
                "role": role,
            }
            if specialization:
                payload["specialization"] = specialization
                payload["department"] = "Specialist Care"
                payload["experience_years"] = 5
            response = self.client.post("/api/auth/register", json=payload)
            self.assertEqual(response.status_code, 201)
            if role == "patient":
                self.assertTrue(response.json()["is_active"])
                self.assertEqual(response.json()["approval_status"], "approved")
            else:
                self.assertFalse(response.json()["is_active"])
                self.assertEqual(response.json()["approval_status"], "pending")

        patient_login = self.client.post(
            "/api/auth/login",
            json={"email": "patient@example.com", "password": "secure-password", "role": "patient"},
        )
        self.assertEqual(patient_login.status_code, 200)
        for email, role, _ in registrations[1:]:
            pending_login = self.client.post(
                "/api/auth/login",
                json={"email": email, "password": "secure-password", "role": role},
            )
            self.assertEqual(pending_login.status_code, 403)

    def test_admin_can_approve_and_reject_public_registrations_with_audit(self):
        doctor = self.client.post(
            "/api/auth/register",
            json={
                "full_name": "Pending Doctor",
                "email": "pending.doctor@example.com",
                "phone": "+1 555 0300",
                "password": "secure-password",
                "confirm_password": "secure-password",
                "role": "clinician",
                "specialization": "Neurology",
            },
        )
        self.assertEqual(doctor.status_code, 201)
        user_id = doctor.json()["id"]

        pending = self.client.get("/api/auth/pending-users", headers=self.headers)
        self.assertEqual(pending.status_code, 200)
        self.assertIn(user_id, [user["id"] for user in pending.json()])

        approved = self.client.post(
            f"/api/auth/users/{user_id}/approve",
            headers=self.headers,
        )
        self.assertEqual(approved.status_code, 200)
        self.assertTrue(approved.json()["is_active"])
        self.assertEqual(approved.json()["approval_status"], "approved")

        login = self.client.post(
            "/api/auth/login",
            json={
                "email": "pending.doctor@example.com",
                "password": "secure-password",
                "role": "clinician",
            },
        )
        self.assertEqual(login.status_code, 200)

        staff = self.client.post(
            "/api/auth/register",
            json={
                "full_name": "Rejected Staff",
                "email": "rejected.staff@example.com",
                "phone": "+1 555 0301",
                "password": "secure-password",
                "confirm_password": "secure-password",
                "role": "staff",
            },
        )
        self.assertEqual(staff.status_code, 201)
        rejected = self.client.post(
            f"/api/auth/users/{staff.json()['id']}/reject",
            headers=self.headers,
        )
        self.assertEqual(rejected.status_code, 200)
        self.assertFalse(rejected.json()["is_active"])
        self.assertEqual(rejected.json()["approval_status"], "rejected")

        db = self.session_factory()
        try:
            actions = db.query(AuditLog).filter(AuditLog.resource == "user").count()
            self.assertGreaterEqual(actions, 2)
        finally:
            db.close()

    def test_public_registration_rejects_duplicate_and_role_mismatches(self):
        payload = {
            "full_name": "Duplicate User",
            "email": "duplicate.roles@example.com",
            "phone": "+1 555 0400",
            "password": "secure-password",
            "confirm_password": "secure-password",
            "role": "patient",
        }
        first = self.client.post("/api/auth/register", json=payload)
        self.assertEqual(first.status_code, 201)
        duplicate = self.client.post("/api/auth/register", json=payload)
        self.assertEqual(duplicate.status_code, 409)

        mismatch = self.client.post(
            "/api/auth/register",
            json={**payload, "email": "clinician.no-specialization@example.com", "role": "clinician"},
        )
        self.assertEqual(mismatch.status_code, 422)

        elevated = self.client.post(
            "/api/auth/register",
            json={**payload, "email": "elevated@example.com", "role": "superadmin"},
        )
        self.assertEqual(elevated.status_code, 422)

    def test_ai_patient_booking_fallback_checks_database_and_returns_confirmation(self):
        db = self.session_factory()
        try:
            doctor_user = User(
                full_name="AI Ritik",
                email="ai.ritik@example.com",
                password_hash=security.hash_password("doctor-password"),
                role="clinician",
                is_active=True,
                approval_status="approved",
            )
            patient_user = User(
                full_name="AI Patient",
                email="ai.patient@example.com",
                password_hash=security.hash_password("patient-password"),
                role="patient",
                is_active=True,
                approval_status="approved",
            )
            db.add_all([doctor_user, patient_user])
            db.flush()
            doctor = Doctor(
                name="Ritik",
                specialization="Cardiology",
                email="ai.ritik.profile@example.com",
                user_id=doctor_user.id,
                appointment_duration_minutes=30,
            )
            patient = Patient(
                name="AI Patient",
                age=30,
                email="ai.patient@example.com",
                user_id=patient_user.id,
            )
            db.add_all([doctor, patient])
            db.commit()
            doctor_id = doctor.id
        finally:
            db.close()

        target = (datetime.now() + timedelta(days=9)).date()
        doctor_login = self.client.post(
            "/api/auth/login",
            json={"email": "ai.ritik@example.com", "password": "doctor-password", "role": "clinician"},
        )
        patient_login = self.client.post(
            "/api/auth/login",
            json={"email": "ai.patient@example.com", "password": "patient-password", "role": "patient"},
        )
        doctor_headers = {"Authorization": f"Bearer {doctor_login.json()['access_token']}"}
        patient_headers = {"Authorization": f"Bearer {patient_login.json()['access_token']}"}
        self.client.post(
            "/api/availability/",
            headers=doctor_headers,
            params={
                "day_of_week": target.strftime("%A"),
                "specific_date": target.isoformat(),
                "start_time": "16:00",
                "end_time": "16:30",
                "is_available": "true",
            },
        )

        with patch("app.ai.orchestrator._gemini_response", side_effect=RuntimeError("Gemini unavailable")):
            first = self.client.post(
                "/api/ai/chat",
                headers=patient_headers,
                json={"query": f"Could you arrange a visit with Dr. Ritik on {target.isoformat()} at 4 PM for a headache"},
            )
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.json()["status"], "approval_required")
        self.assertIn("pending until the doctor accepts", first.json()["message"])
        self.assertEqual(first.json()["data"]["doctor_id"], doctor_id)

        approval_id = first.json()["approval_id"]
        approved = self.client.post(
            f"/api/ai/approvals/{approval_id}/approve",
            headers=patient_headers,
        )
        self.assertEqual(approved.status_code, 200)
        self.assertEqual(approved.json()["status"], "executed")
        self.assertIn("appointment_id", approved.json()["result"])
        self.assertEqual(approved.json()["result"]["status"], "Pending Doctor Approval")

    def test_patient_ai_booking_remembers_context_and_waits_for_confirmation(self):
        target = (datetime.now() + timedelta(days=12)).date()
        db = self.session_factory()
        try:
            doctor_user = User(full_name="Context Doctor", email="context.doctor@example.com", password_hash=security.hash_password("doctor-password"), role="clinician", is_active=True, approval_status="approved")
            patient_user = User(full_name="Context Patient", email="context.patient@example.com", password_hash=security.hash_password("patient-password"), role="patient", is_active=True, approval_status="approved")
            db.add_all([doctor_user, patient_user])
            db.flush()
            doctor = Doctor(name="Context Doctor", specialization="Cardiology", department="Heart", email="context.profile@example.com", user_id=doctor_user.id)
            patient = Patient(name="Context Patient", age=29, email="context.patient@example.com", user_id=patient_user.id)
            db.add_all([doctor, patient])
            db.flush()
            db.add(DoctorAvailability(doctor_id=doctor.id, day_of_week=target.strftime("%A"), specific_date=target, start_time=datetime.strptime("09:00", "%H:%M").time(), end_time=datetime.strptime("10:00", "%H:%M").time(), is_available=True))
            db.commit()
            doctor_id = doctor.id
        finally:
            db.close()

        login = self.client.post("/api/auth/login", json={"email": "context.patient@example.com", "password": "patient-password", "role": "patient"})
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
        doctor_search = self.client.post("/api/ai/chat", headers=headers, json={"query": "Find a cardiologist"})
        self.assertEqual(doctor_search.status_code, 200)
        self.assertEqual(doctor_search.json()["status"], "completed")
        self.assertEqual(doctor_search.json()["data"]["doctors"][0]["name"], "Context Doctor")
        first = self.client.post("/api/ai/chat", headers=headers, json={"query": "I want to book an appointment"})
        self.assertEqual(first.json()["status"], "clarification_required")
        doctor_cards = first.json()["data"]["doctors"]
        self.assertTrue(doctor_cards)
        self.assertEqual(doctor_cards[0]["id"], doctor_id)
        self.assertEqual(doctor_cards[0]["name"], "Context Doctor")
        self.assertEqual(doctor_cards[0]["specialization"], "Cardiology")
        self.assertEqual(doctor_cards[0]["department"], "Heart")
        self.assertIn("Choose a doctor", first.json()["message"])
        self.assertNotIn("ID", first.json()["message"])
        conversation_id = first.json()["conversation_id"]

        def ask(text):
            return self.client.post("/api/ai/chat", headers=headers, json={"query": text, "conversation_id": conversation_id})

        doctor_choice = ask("Dr. Context Doctor")
        self.assertIn("What date", doctor_choice.json()["message"])
        self.assertEqual(doctor_choice.json()["data"]["doctor"]["name"], "Context Doctor")
        date_choice = ask(target.isoformat())
        self.assertIn("Available slots", date_choice.json()["message"])
        time_choice = ask("9 AM")
        self.assertEqual(time_choice.json()["status"], "approval_required")
        self.assertIn("General consultation", time_choice.json()["message"])
        self.assertIn("Confirm to submit", time_choice.json()["message"])

        pending_snapshot = self.client.get("/api/ai/conversations/latest", headers=headers)
        self.assertEqual(pending_snapshot.status_code, 200)
        pending_body = pending_snapshot.json()
        self.assertEqual(pending_body["conversation_id"], conversation_id)
        self.assertEqual(pending_body["pending_approval"]["id"], time_choice.json()["approval_id"])
        self.assertEqual(pending_body["last_response"]["status"], "approval_required")
        self.assertEqual(pending_body["last_response"]["data"]["date"], target.isoformat())
        self.assertEqual(pending_body["last_response"]["data"]["time"], "09:00")
        self.assertEqual(pending_body["last_response"]["data"]["doctor"]["name"], "Context Doctor")
        self.assertNotIn("patient_id", pending_body["last_response"]["data"])
        self.assertNotIn("reason", pending_body["last_response"]["data"])
        self.assertTrue(any(item["content"] == "Dr. Context Doctor" for item in pending_body["messages"]))
        self.assertTrue(any(item["content"] == target.isoformat() for item in pending_body["messages"]))

        db = self.session_factory()
        try:
            self.assertEqual(db.query(Appointment).count(), 0)
        finally:
            db.close()
        submitted = self.client.post(f"/api/ai/approvals/{time_choice.json()['approval_id']}/approve", headers=headers)
        self.assertEqual(submitted.status_code, 200)
        self.assertEqual(submitted.json()["result"]["status"], "Pending Doctor Approval")
        completed_snapshot = self.client.get("/api/ai/conversations/latest", headers=headers).json()
        self.assertIsNone(completed_snapshot["pending_approval"])
        self.assertIn("waiting for doctor approval", completed_snapshot["messages"][-1]["content"].lower())

    def test_available_slot_booking_succeeds_with_confirmation_data(self):
        db = self.session_factory()
        try:
            doctor_user = User(full_name="Confirmation Doctor", email="confirmation.doctor@example.com", password_hash=security.hash_password("doctor-password"), role="clinician", is_active=True, approval_status="approved")
            patient_user = User(full_name="Confirmation Patient", email="confirmation.patient@example.com", password_hash=security.hash_password("patient-password"), role="patient", is_active=True, approval_status="approved")
            db.add_all([doctor_user, patient_user])
            db.flush()
            doctor = Doctor(name="Confirmation Doctor", specialization="Cardiology", email="confirmation.profile@example.com", user_id=doctor_user.id, appointment_duration_minutes=30)
            patient = Patient(name="Confirmation Patient", age=28, email="confirmation.patient@example.com", user_id=patient_user.id)
            db.add_all([doctor, patient])
            db.commit()
            doctor_id = doctor.id
        finally:
            db.close()

        doctor_login = self.client.post("/api/auth/login", json={"email": "confirmation.doctor@example.com", "password": "doctor-password", "role": "clinician"})
        patient_login = self.client.post("/api/auth/login", json={"email": "confirmation.patient@example.com", "password": "patient-password", "role": "patient"})
        doctor_headers = {"Authorization": f"Bearer {doctor_login.json()['access_token']}"}
        patient_headers = {"Authorization": f"Bearer {patient_login.json()['access_token']}"}

        target = (datetime.now() + timedelta(days=6)).date()
        self.client.post(
            "/api/availability/",
            headers=doctor_headers,
            params={"day_of_week": target.strftime("%A"), "specific_date": target.isoformat(), "start_time": "09:00", "end_time": "09:30", "is_available": "true"},
        )
        slot = f"{target.isoformat()}T09:00:00"
        response = self.client.post(
            "/api/appointments/",
            headers=patient_headers,
            params={"patient_id": 0, "doctor_id": doctor_id, "appointment_date": slot, "reason": "General consultation"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["appointment"]["doctor_id"], doctor_id)
        self.assertEqual(response.json()["appointment"]["appointment_date"], slot)
        self.assertEqual(response.json()["appointment"]["status"], "Pending Doctor Approval")

    def test_doctor_unavailable_slot_returns_exact_error(self):
        db = self.session_factory()
        try:
            doctor_user = User(full_name="Unavailable Doctor", email="unavailable.doctor@example.com", password_hash=security.hash_password("doctor-password"), role="clinician", is_active=True, approval_status="approved")
            patient_user = User(full_name="Unavailable Patient", email="unavailable.patient@example.com", password_hash=security.hash_password("patient-password"), role="patient", is_active=True, approval_status="approved")
            db.add_all([doctor_user, patient_user])
            db.flush()
            doctor = Doctor(name="Unavailable Doctor", specialization="Dermatology", email="unavailable.profile@example.com", user_id=doctor_user.id, appointment_duration_minutes=30)
            patient = Patient(name="Unavailable Patient", age=29, email="unavailable.patient@example.com", user_id=patient_user.id)
            db.add_all([doctor, patient])
            db.commit()
            doctor_id = doctor.id
        finally:
            db.close()

        patient_login = self.client.post("/api/auth/login", json={"email": "unavailable.patient@example.com", "password": "patient-password", "role": "patient"})
        patient_headers = {"Authorization": f"Bearer {patient_login.json()['access_token']}"}
        target = (datetime.now() + timedelta(days=7)).date()
        response = self.client.post(
            "/api/appointments/",
            headers=patient_headers,
            params={"patient_id": 0, "doctor_id": doctor_id, "appointment_date": f"{target.isoformat()}T16:00:00"},
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"]["message"], "Doctor is not available at this time.")

    def test_already_booked_slot_returns_exact_conflict(self):
        db = self.session_factory()
        try:
            doctor_user = User(full_name="Booked Doctor", email="booked.doctor@example.com", password_hash=security.hash_password("doctor-password"), role="clinician", is_active=True, approval_status="approved")
            patient1 = User(full_name="Booked Patient 1", email="booked.patient1@example.com", password_hash=security.hash_password("patient-password"), role="patient", is_active=True, approval_status="approved")
            patient2 = User(full_name="Booked Patient 2", email="booked.patient2@example.com", password_hash=security.hash_password("patient-password"), role="patient", is_active=True, approval_status="approved")
            db.add_all([doctor_user, patient1, patient2])
            db.flush()
            doctor = Doctor(name="Booked Doctor", specialization="Orthopedics", email="booked.profile@example.com", user_id=doctor_user.id, appointment_duration_minutes=30)
            profile1 = Patient(name="Booked Patient 1", age=30, email="booked.patient1@example.com", user_id=patient1.id)
            profile2 = Patient(name="Booked Patient 2", age=31, email="booked.patient2@example.com", user_id=patient2.id)
            db.add_all([doctor, profile1, profile2])
            db.commit()
            doctor_id = doctor.id
        finally:
            db.close()

        doctor_login = self.client.post("/api/auth/login", json={"email": "booked.doctor@example.com", "password": "doctor-password", "role": "clinician"})
        doctor_headers = {"Authorization": f"Bearer {doctor_login.json()['access_token']}"}
        target = (datetime.now() + timedelta(days=8)).date()
        self.client.post(
            "/api/availability/",
            headers=doctor_headers,
            params={"day_of_week": target.strftime("%A"), "specific_date": target.isoformat(), "start_time": "11:00", "end_time": "11:30", "is_available": "true"},
        )
        slot = f"{target.isoformat()}T11:00:00"

        responses = []
        for email in ("booked.patient1@example.com", "booked.patient2@example.com"):
            login = self.client.post("/api/auth/login", json={"email": email, "password": "patient-password", "role": "patient"})
            headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
            responses.append(self.client.post(
                "/api/appointments/",
                headers=headers,
                params={"patient_id": 0, "doctor_id": doctor_id, "appointment_date": slot},
            ))

        statuses = [response.status_code for response in responses]
        self.assertEqual(statuses.count(200), 1)
        conflict = next(response for response in responses if response.status_code == 409)
        self.assertEqual(conflict.json()["detail"]["message"], "This appointment slot is already booked.")

    def test_doctor_availability_and_patient_slot_booking_flow(self):
        db = self.session_factory()
        try:
            doctor_user = User(
                full_name="Schedule Doctor",
                email="schedule.doctor@example.com",
                password_hash=security.hash_password("doctor-password"),
                role="clinician",
                is_active=True,
                approval_status="approved",
            )
            patient_user = User(
                full_name="Schedule Patient",
                email="schedule.patient@example.com",
                password_hash=security.hash_password("patient-password"),
                role="patient",
                is_active=True,
                approval_status="approved",
            )
            db.add_all([doctor_user, patient_user])
            db.flush()
            doctor = Doctor(
                name="Schedule Doctor",
                specialization="General Medicine",
                email="schedule.profile@example.com",
                user_id=doctor_user.id,
                appointment_duration_minutes=30,
            )
            patient = Patient(
                name="Schedule Patient",
                age=30,
                email="schedule.patient@example.com",
                phone="+1 555 0600",
                user_id=patient_user.id,
            )
            db.add_all([doctor, patient])
            db.commit()
            doctor_id = doctor.id
        finally:
            db.close()

        doctor_login = self.client.post(
            "/api/auth/login",
            json={"email": "schedule.doctor@example.com", "password": "doctor-password", "role": "clinician"},
        )
        patient_login = self.client.post(
            "/api/auth/login",
            json={"email": "schedule.patient@example.com", "password": "patient-password", "role": "patient"},
        )
        self.assertEqual(doctor_login.status_code, 200)
        self.assertEqual(patient_login.status_code, 200)
        doctor_headers = {"Authorization": f"Bearer {doctor_login.json()['access_token']}"}
        patient_headers = {"Authorization": f"Bearer {patient_login.json()['access_token']}"}

        target = (datetime.now() + timedelta(days=4)).date()
        day_name = target.strftime("%A")
        create = self.client.post(
            "/api/availability/",
            headers=doctor_headers,
            params={
                "day_of_week": day_name,
                "specific_date": target.isoformat(),
                "start_time": "13:00",
                "end_time": "14:00",
                "is_available": "true",
            },
        )
        self.assertEqual(create.status_code, 200)
        self.assertEqual(create.json()["availability"]["specific_date"], target.isoformat())

        slots = self.client.get(
            f"/api/availability/slots/{doctor_id}",
            headers=patient_headers,
            params={"date": target.isoformat()},
        )
        self.assertEqual(slots.status_code, 200)
        available = [slot for slot in slots.json()["slots"] if slot["status"] == "available"]
        self.assertEqual(len(available), 2)

        booking = self.client.post(
            "/api/appointments/",
            headers=patient_headers,
            params={
                "patient_id": 0,
                "doctor_id": doctor_id,
                "appointment_date": available[0]["start"],
            },
        )
        self.assertEqual(booking.status_code, 200)

        conflict = self.client.post(
            "/api/appointments/",
            headers=patient_headers,
            params={
                "patient_id": 0,
                "doctor_id": doctor_id,
                "appointment_date": available[0]["start"],
            },
        )
        self.assertEqual(conflict.status_code, 409)
        self.assertEqual(
            conflict.json()["detail"]["message"],
            "This appointment slot is already booked.",
        )

        blocked = self.client.post(
            "/api/availability/",
            headers=doctor_headers,
            params={
                "day_of_week": target.strftime("%A"),
                "specific_date": target.isoformat(),
                "start_time": "00:00",
                "end_time": "23:59",
                "is_available": "false",
            },
        )
        self.assertEqual(blocked.status_code, 200)
        blocked_slots = self.client.get(
            f"/api/availability/slots/{doctor_id}",
            headers=patient_headers,
            params={"date": target.isoformat()},
        )
        self.assertEqual(blocked_slots.status_code, 200)
        self.assertTrue(blocked_slots.json()["blocked"])

    def test_two_patients_cannot_concurrently_book_the_same_slot(self):
        db = self.session_factory()
        try:
            doctor_user = User(
                full_name="Concurrency Doctor",
                email="concurrency.doctor@example.com",
                password_hash=security.hash_password("doctor-password"),
                role="clinician",
                is_active=True,
                approval_status="approved",
            )
            patient1 = User(
                full_name="Concurrency Patient 1",
                email="concurrency.patient1@example.com",
                password_hash=security.hash_password("patient-password"),
                role="patient",
                is_active=True,
                approval_status="approved",
            )
            patient2 = User(
                full_name="Concurrency Patient 2",
                email="concurrency.patient2@example.com",
                password_hash=security.hash_password("patient-password"),
                role="patient",
                is_active=True,
                approval_status="approved",
            )
            db.add_all([doctor_user, patient1, patient2])
            db.flush()
            doctor = Doctor(
                name="Concurrency Doctor",
                specialization="General Medicine",
                email="concurrency.profile@example.com",
                user_id=doctor_user.id,
                appointment_duration_minutes=30,
            )
            profile1 = Patient(name="Concurrency Patient 1", age=30, email=patient1.email, user_id=patient1.id)
            profile2 = Patient(name="Concurrency Patient 2", age=31, email=patient2.email, user_id=patient2.id)
            db.add_all([doctor, profile1, profile2])
            db.commit()
            doctor_id = doctor.id
        finally:
            db.close()

        target = (datetime.now() + timedelta(days=5)).date()
        day_name = target.strftime("%A")
        doctor_login = self.client.post(
            "/api/auth/login",
            json={"email": "concurrency.doctor@example.com", "password": "doctor-password", "role": "clinician"},
        )
        doctor_headers = {"Authorization": f"Bearer {doctor_login.json()['access_token']}"}
        self.client.post(
            "/api/availability/",
            headers=doctor_headers,
            params={"day_of_week": day_name, "specific_date": target.isoformat(), "start_time": "10:00", "end_time": "11:00", "is_available": "true"},
        )

        patient_tokens = []
        for email in ("concurrency.patient1@example.com", "concurrency.patient2@example.com"):
            login = self.client.post(
                "/api/auth/login",
                json={"email": email, "password": "patient-password", "role": "patient"},
            )
            patient_tokens.append({"Authorization": f"Bearer {login.json()['access_token']}"})

        requested = f"{target.isoformat()}T10:00:00"

        def attempt(headers):
            return self.client.post(
                "/api/appointments/",
                headers=headers,
                params={"patient_id": 0, "doctor_id": doctor_id, "appointment_date": requested},
            )

        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(pool.map(attempt, patient_tokens))
        statuses = [response.status_code for response in responses]
        self.assertEqual(statuses.count(200), 1)
        self.assertEqual(statuses.count(409), 1)

    def test_protected_resources_require_authentication(self):
        response = self.client.get("/api/patients/")

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(response.headers["X-Frame-Options"], "DENY")
        self.assertEqual(response.headers["Cache-Control"], "no-store")

    def test_patient_doctor_availability_appointment_and_cancellation(self):
        patient_response = self.client.post(
            "/api/patients/",
            headers=self.headers,
            json={
                "name": "Alex Morgan",
                "age": 34,
                "gender": "Other",
                "email": "alex@example.com",
            },
        )
        doctor_response = self.client.post(
            "/api/doctors/",
            headers=self.headers,
            json={
                "name": "Jordan Lee",
                "specialization": "Cardiology",
                "email": "jordan@example.com",
                "experience_years": 8,
            },
        )
        self.assertEqual(patient_response.status_code, 200)
        self.assertEqual(doctor_response.status_code, 200)
        patient_id = patient_response.json()["id"]
        doctor_id = doctor_response.json()["id"]

        weekday = (datetime.now() + timedelta(days=1)).strftime("%A")
        availability_response = self.client.post(
            "/api/availability/",
            headers=self.headers,
            params={
                "doctor_id": doctor_id,
                "day_of_week": weekday,
                "start_time": "09:00:00",
                "end_time": "17:00:00",
            },
        )
        self.assertEqual(availability_response.status_code, 200)

        appointment_response = self.client.post(
            "/api/appointments/",
            headers=self.headers,
            params={
                "patient_id": patient_id,
                "doctor_id": doctor_id,
                "appointment_date": (
                    datetime.now() + timedelta(days=1)
                ).replace(hour=10, minute=0, second=0, microsecond=0).isoformat(),
                "reason": "Follow-up",
            },
        )
        self.assertEqual(appointment_response.status_code, 200)
        appointment_id = appointment_response.json()["appointment"]["id"]

        cancellation_response = self.client.delete(
            f"/api/appointments/{appointment_id}",
            headers=self.headers,
        )
        self.assertEqual(cancellation_response.status_code, 200)
        self.assertEqual(cancellation_response.json()["status"], "Cancelled")

    def test_billing_payment_and_overpayment_protection(self):
        patient_response = self.client.post(
            "/api/patients/",
            headers=self.headers,
            json={
                "name": "Billing Patient",
                "age": 40,
                "email": "billing@example.com",
            },
        )
        patient_id = patient_response.json()["id"]
        bill_response = self.client.post(
            "/api/bills/",
            headers=self.headers,
            params={
                "patient_id": patient_id,
                "bill_number": "BILL-001",
                "total_amount": 100,
            },
        )
        self.assertEqual(bill_response.status_code, 200)
        bill_id = bill_response.json()["bill"]["id"]

        payment_response = self.client.post(
            "/api/payments/",
            headers=self.headers,
            params={
                "bill_id": bill_id,
                "amount": 60,
                "payment_method": "Card",
            },
        )
        self.assertEqual(payment_response.status_code, 200)
        self.assertEqual(payment_response.json()["bill_status"], "Partially Paid")

        overpayment_response = self.client.post(
            "/api/payments/",
            headers=self.headers,
            params={
                "bill_id": bill_id,
                "amount": 41,
                "payment_method": "Card",
            },
        )
        self.assertEqual(overpayment_response.status_code, 409)

    def test_triage_requires_authentication_and_returns_disclaimer(self):
        unauthenticated = self.client.post(
            "/api/triage/",
            json={"symptoms": "severe chest pain"},
        )
        self.assertEqual(unauthenticated.status_code, 401)

        response = self.client.post(
            "/api/triage/",
            headers=self.headers,
            json={"symptoms": "severe chest pain"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["urgency"], "Emergency")
        self.assertIn("not a medical diagnosis", response.json()["disclaimer"])

    def test_dashboard_metrics_are_authenticated_and_database_backed(self):
        unauthenticated = self.client.get("/api/dashboard/metrics")
        self.assertEqual(unauthenticated.status_code, 401)

        response = self.client.get(
            "/api/dashboard/metrics",
            headers=self.headers,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["patients_registered"], 0)
        self.assertEqual(response.json()["appointments_today"], 0)

        audit_db = self.session_factory()
        try:
            self.assertGreaterEqual(audit_db.query(AuditLog).count(), 1)
        finally:
            audit_db.close()

    def test_billing_and_payment_reads_are_scoped_by_role(self):
        db = self.session_factory()
        try:
            patient_users = [
                User(full_name=f"Finance Patient {index}", email=f"finance.patient{index}@example.com", password_hash=security.hash_password("patient-password"), role="patient", is_active=True, approval_status="approved")
                for index in (1, 2)
            ]
            staff_user = User(full_name="Finance Staff", email="finance.staff@example.com", password_hash=security.hash_password("staff-password"), role="staff", is_active=True, approval_status="approved")
            clinician_user = User(full_name="Finance Clinician", email="finance.clinician@example.com", password_hash=security.hash_password("clinician-password"), role="clinician", is_active=True, approval_status="approved")
            db.add_all([*patient_users, staff_user, clinician_user])
            db.flush()
            patient_profiles = [
                Patient(name=f"Finance Patient {index}", age=30 + index, email=f"finance.patient{index}@example.com", user_id=user.id)
                for index, user in enumerate(patient_users, start=1)
            ]
            db.add_all(patient_profiles)
            db.flush()
            bills = [
                Bill(patient_id=patient_profiles[index].id, bill_number=f"FIN-{index + 1}", total_amount=100 + index, status="Pending")
                for index in range(2)
            ]
            db.add_all(bills)
            db.flush()
            payments = [
                Payment(bill_id=bill.id, amount=50, payment_method="Card", payment_status="Completed", transaction_reference=f"FIN-REF-{index + 1}")
                for index, bill in enumerate(bills)
            ]
            db.add_all(payments)
            db.commit()
            bill_ids = [bill.id for bill in bills]
            payment_ids = [payment.id for payment in payments]
        finally:
            db.close()

        def login(email, password):
            response = self.client.post("/api/auth/login", json={"email": email, "password": password})
            self.assertEqual(response.status_code, 200)
            return {"Authorization": f"Bearer {response.json()['access_token']}"}

        patient_one = login("finance.patient1@example.com", "patient-password")
        own_bills = self.client.get("/api/bills/", headers=patient_one)
        own_payments = self.client.get("/api/payments/", headers=patient_one)
        self.assertEqual(own_bills.status_code, 200)
        self.assertEqual([item["id"] for item in own_bills.json()], [bill_ids[0]])
        self.assertEqual(own_payments.status_code, 200)
        self.assertEqual([item["id"] for item in own_payments.json()], [payment_ids[0]])
        self.assertEqual(self.client.get(f"/api/bills/{bill_ids[0]}", headers=patient_one).status_code, 200)
        self.assertEqual(self.client.get(f"/api/payments/{payment_ids[0]}", headers=patient_one).status_code, 200)
        self.assertEqual(self.client.get(f"/api/bills/{bill_ids[1]}", headers=patient_one).status_code, 404)
        self.assertEqual(self.client.get(f"/api/payments/{payment_ids[1]}", headers=patient_one).status_code, 404)

        clinician = login("finance.clinician@example.com", "clinician-password")
        self.assertEqual(self.client.get("/api/bills/", headers=clinician).status_code, 403)
        self.assertEqual(self.client.get("/api/payments/", headers=clinician).status_code, 403)
        self.assertEqual(self.client.get(f"/api/bills/{bill_ids[0]}", headers=clinician).status_code, 403)
        self.assertEqual(self.client.get(f"/api/payments/{payment_ids[0]}", headers=clinician).status_code, 403)

        for authorized_finance_user in (
            login("finance.staff@example.com", "staff-password"),
            self.headers,
        ):
            finance_bills = self.client.get("/api/bills/", headers=authorized_finance_user)
            finance_payments = self.client.get("/api/payments/", headers=authorized_finance_user)
            self.assertEqual(finance_bills.status_code, 200)
            self.assertEqual({item["id"] for item in finance_bills.json()}, set(bill_ids))
            self.assertEqual(finance_payments.status_code, 200)
            self.assertEqual({item["id"] for item in finance_payments.json()}, set(payment_ids))
            for bill_id, payment_id in zip(bill_ids, payment_ids):
                self.assertEqual(self.client.get(f"/api/bills/{bill_id}", headers=authorized_finance_user).status_code, 200)
                self.assertEqual(self.client.get(f"/api/payments/{payment_id}", headers=authorized_finance_user).status_code, 200)

    def test_dashboard_metrics_return_role_safe_fields(self):
        db = self.session_factory()
        try:
            patient_user = User(full_name="Metrics Patient", email="metrics.patient@example.com", password_hash=security.hash_password("patient-password"), role="patient", is_active=True, approval_status="approved")
            clinician_user = User(full_name="Metrics Clinician", email="metrics.clinician@example.com", password_hash=security.hash_password("clinician-password"), role="clinician", is_active=True, approval_status="approved")
            staff_user = User(full_name="Metrics Staff", email="metrics.staff@example.com", password_hash=security.hash_password("staff-password"), role="staff", is_active=True, approval_status="approved")
            db.add_all([patient_user, clinician_user, staff_user])
            db.flush()
            db.add_all([
                Patient(name="Metrics Patient", age=28, email="metrics.patient@example.com", user_id=patient_user.id),
                Doctor(name="Metrics Clinician", specialization="Cardiology", email="metrics.doctor@example.com", user_id=clinician_user.id),
            ])
            db.commit()
        finally:
            db.close()

        def login(email, password):
            response = self.client.post("/api/auth/login", json={"email": email, "password": password})
            self.assertEqual(response.status_code, 200)
            return {"Authorization": f"Bearer {response.json()['access_token']}"}

        self.assertEqual(self.client.get("/api/dashboard/metrics").status_code, 401)
        patient_metrics = self.client.get("/api/dashboard/metrics", headers=login("metrics.patient@example.com", "patient-password"))
        self.assertEqual(patient_metrics.status_code, 200)
        self.assertEqual(patient_metrics.json()["doctors_registered"], 0)
        self.assertEqual(float(patient_metrics.json()["recorded_billing"]), 0)
        self.assertEqual(patient_metrics.json()["outstanding_bills"], 0)

        clinician_metrics = self.client.get("/api/dashboard/metrics", headers=login("metrics.clinician@example.com", "clinician-password"))
        self.assertEqual(clinician_metrics.status_code, 200)
        self.assertEqual(clinician_metrics.json()["doctors_registered"], 1)
        self.assertEqual(float(clinician_metrics.json()["recorded_billing"]), 0)
        self.assertEqual(clinician_metrics.json()["outstanding_bills"], 0)

        staff_metrics = self.client.get("/api/dashboard/metrics", headers=login("metrics.staff@example.com", "staff-password"))
        admin_metrics = self.client.get("/api/dashboard/metrics", headers=self.headers)
        for response in (staff_metrics, admin_metrics):
            self.assertEqual(response.status_code, 200)
            self.assertEqual(set(response.json()), {
                "appointments_today", "patients_registered", "doctors_registered",
                "recorded_billing", "outstanding_bills",
            })

    def test_list_endpoints_support_search_filtering_and_pagination(self):
        for name, email in (
            ("Searchable Patient", "searchable@example.com"),
            ("Other Patient", "other@example.com"),
        ):
            self.client.post(
                "/api/patients/",
                headers=self.headers,
                json={"name": name, "age": 30, "email": email},
            )

        response = self.client.get(
            "/api/patients/",
            headers=self.headers,
            params={"search": "Searchable", "limit": 1, "offset": 0},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()), 1)
        self.assertEqual(response.json()[0]["name"], "Searchable Patient")

    def test_ai_chat_uses_deterministic_triage_and_preserves_conversation(self):
        first = self.client.post(
            "/api/ai/chat",
            headers=self.headers,
            json={"query": "I have severe chest pain"},
        )
        self.assertEqual(first.status_code, 200)
        first_body = first.json()
        self.assertEqual(first_body["agent"], "Medical Triage Agent")
        self.assertEqual(first_body["data"]["urgency"], "Emergency")
        self.assertIsNotNone(first_body["conversation_id"])

        follow_up = self.client.post(
            "/api/ai/chat",
            headers=self.headers,
            json={
                "query": "Show me cardiology doctors",
                "conversation_id": first_body["conversation_id"],
            },
        )
        self.assertEqual(follow_up.status_code, 200)
        self.assertEqual(
            follow_up.json()["conversation_id"],
            first_body["conversation_id"],
        )

    def test_patient_id_lookup_and_support_clarification_tools(self):
        patient = self.client.post(
            "/api/patients/",
            headers=self.headers,
            json={"name": "ID Lookup Patient", "age": 31, "email": "idlookup@example.com"},
        ).json()

        class GetCall:
            name = "get_patient"
            args = {"patient_id": patient["id"]}

        class GetResponse:
            function_calls = [GetCall()]
            text = "Patient lookup completed."

        with patch("app.ai.orchestrator._gemini_response", return_value=GetResponse()):
            lookup = self.client.post(
                "/api/ai/chat",
                headers=self.headers,
                json={"query": f"Find patient ID {patient['id']}"},
            )

        self.assertEqual(lookup.status_code, 200)
        self.assertEqual(
            lookup.json()["data"]["tool_results"][0]["result"]["patient"]["name"],
            "ID Lookup Patient",
        )

        class SupportCall:
            name = "support_guidance"
            args = {"category": "appointment", "issue": "appointment problem"}

        class SupportResponse:
            function_calls = [SupportCall()]
            text = "Support guidance requested."

        with patch("app.ai.orchestrator._gemini_response", return_value=SupportResponse()):
            support = self.client.post(
                "/api/ai/chat",
                headers=self.headers,
                json={"query": "I have a problem with my appointment"},
            )

        self.assertEqual(support.status_code, 200)
        self.assertEqual(support.json()["status"], "clarification_required")
        self.assertIn("appointment", support.json()["message"].lower())
        self.assertIn("cancelling", support.json()["message"].lower())

    def test_customer_support_guidance_and_authenticated_appointment_status(self):
        class NoToolCalls:
            function_calls = []
            text = ""

        guidance_cases = (
            ("How do I book an appointment?", "appointment_booking", "wait for your confirmation"),
            ("I have a problem with my appointment", "appointment_support", "cancelling"),
            ("How can I cancel an appointment?", "appointment_cancellation", "appointment number"),
            ("I can't log in to my account", "login_registration", "self-service password reset"),
            ("How do I register?", "login_registration", "administrator approval"),
            ("Where is my dashboard?", "dashboard_navigation", "Accounts"),
            ("Is Dr Smith available?", "doctor_availability", "schedule on file"),
            ("The technical error is not working", "technical_support", "verified channel"),
        )
        with patch("app.ai.orchestrator._gemini_response", return_value=NoToolCalls()):
            for query, expected_category, expected_text in guidance_cases:
                response = self.client.post("/api/ai/chat", headers=self.headers, json={"query": query})
                self.assertEqual(response.status_code, 200, query)
                self.assertEqual(response.json()["agent"], "Customer Support Agent", query)
                support_result = response.json()["data"]["tool_results"][0]["result"]
                self.assertEqual(support_result["category"], expected_category, query)
                self.assertIn(expected_text.lower(), response.json()["message"].lower(), query)

            unknown = self.client.post(
                "/api/ai/chat",
                headers=self.headers,
                json={"query": "What is the weather on Neptune?"},
            )
        self.assertEqual(unknown.status_code, 200)
        self.assertEqual(unknown.json()["agent"], "Customer Support Agent")
        self.assertEqual(unknown.json()["status"], "clarification_required")

        db = self.session_factory()
        try:
            patient_user = User(full_name="Support Patient", email="support.patient@example.com", password_hash=security.hash_password("patient-password"), role="patient", is_active=True, approval_status="approved")
            clinician_user = User(full_name="Support Clinician", email="support.clinician@example.com", password_hash=security.hash_password("doctor-password"), role="clinician", is_active=True, approval_status="approved")
            db.add_all([patient_user, clinician_user])
            db.flush()
            patient = Patient(name="Support Patient", age=30, email="support.patient@example.com", user_id=patient_user.id)
            doctor = Doctor(name="Support Clinician", specialization="Cardiology", email="support.clinician.profile@example.com", user_id=clinician_user.id)
            db.add_all([patient, doctor])
            db.flush()
            appointment = Appointment(patient_id=patient.id, doctor_id=doctor.id, appointment_date=datetime.now() + timedelta(days=14), status="Pending Doctor Approval")
            db.add(appointment)
            db.commit()
            appointment_id = appointment.id
        finally:
            db.close()

        patient_login = self.client.post("/api/auth/login", json={"email": "support.patient@example.com", "password": "patient-password", "role": "patient"})
        clinician_login = self.client.post("/api/auth/login", json={"email": "support.clinician@example.com", "password": "doctor-password", "role": "clinician"})
        self.assertEqual(patient_login.status_code, 200)
        self.assertEqual(clinician_login.status_code, 200)
        patient_headers = {"Authorization": f"Bearer {patient_login.json()['access_token']}"}
        clinician_headers = {"Authorization": f"Bearer {clinician_login.json()['access_token']}"}

        with patch("app.ai.orchestrator._gemini_response", return_value=NoToolCalls()):
            patient_status = self.client.post("/api/ai/chat", headers=patient_headers, json={"query": "What is my appointment status?"})
            clinician_dashboard = self.client.post("/api/ai/chat", headers=clinician_headers, json={"query": "How do I find my dashboard?"})
        self.assertEqual(patient_status.status_code, 200)
        history_result = patient_status.json()["data"]["tool_results"][0]["result"]["appointments"]
        self.assertEqual([item["id"] for item in history_result], [appointment_id])
        self.assertEqual(history_result[0]["status"], "Pending Doctor Approval")
        self.assertEqual(clinician_dashboard.status_code, 200)
        self.assertIn("clinician Overview", clinician_dashboard.json()["message"])

    def test_pending_bills_use_completed_payment_balance(self):
        patient = self.client.post(
            "/api/patients/",
            headers=self.headers,
            json={"name": "Balance Patient", "age": 38, "email": "balance@example.com"},
        ).json()
        bill = self.client.post(
            "/api/bills/",
            headers=self.headers,
            params={
                "patient_id": patient["id"],
                "bill_number": "BALANCE-001",
                "total_amount": 100,
            },
        ).json()["bill"]
        self.client.post(
            "/api/payments/",
            headers=self.headers,
            params={
                "bill_id": bill["id"],
                "amount": 60,
                "payment_method": "Card",
            },
        )

        class Call:
            name = "pending_bills"
            args = {}

        class Response:
            function_calls = [Call()]
            text = "Pending bills checked."

        with patch("app.ai.orchestrator._gemini_response", return_value=Response()):
            result = self.client.post(
                "/api/ai/chat",
                headers=self.headers,
                json={"query": "Show pending bills"},
            )

        self.assertEqual(result.status_code, 200)
        tool_result = result.json()["data"]["tool_results"][0]["result"]
        self.assertEqual(tool_result["pending_amount"], 40)
        self.assertEqual(tool_result["bills"][0]["outstanding_amount"], 40)

    def test_ai_finance_write_requires_approval_and_enforces_role(self):
        patient = self.client.get("/api/patients/", headers=self.headers).json()
        if not patient:
            patient = self.client.post(
                "/api/patients/",
                headers=self.headers,
                json={"name": "Finance AI Patient", "age": 30, "email": "finance.ai.patient@example.com"},
            ).json()
        else:
            patient = patient[0]

        class BillCall:
            name = "generate_bill"
            args = {
                "patient_id": patient["id"],
                "bill_number": "AI-FINANCE-001",
                "total_amount": 250.0,
            }

        class BillResponse:
            function_calls = [BillCall()]
            text = "Bill proposed."

        with patch("app.ai.orchestrator._gemini_response", return_value=BillResponse()):
            proposed = self.client.post(
                "/api/ai/chat",
                headers=self.headers,
                json={"query": "Generate a bill for this patient"},
            )
        self.assertEqual(proposed.status_code, 200)
        self.assertEqual(proposed.json()["status"], "approval_required")
        approval_id = proposed.json()["approval_id"]

        approved = self.client.post(
            f"/api/ai/approvals/{approval_id}/approve",
            headers=self.headers,
        )
        self.assertEqual(approved.status_code, 200)
        self.assertEqual(approved.json()["status"], "executed")
        self.assertIn("bill_id", approved.json()["result"])

    def test_finance_analytics_reports_use_authorized_decimal_aggregates(self):
        headers, appointments, _, _ = self._cancellation_fixture()
        staff = headers["staff"]
        self.enterContext(patch("app.services.finance_analytics.finance_today", return_value=date(2026, 11, 25)))
        gemini = self.enterContext(patch("app.ai.orchestrator._gemini_response", side_effect=ConnectionError("offline")))

        def ask(query, actor=staff):
            response = self.client.post("/api/ai/chat", headers=actor, json={"query": query, "role": "admin"})
            self.assertEqual(response.status_code, 200, response.text)
            return response.json()

        def report(query, actor=staff):
            result = ask(query, actor)
            self.assertEqual(result["status"], "completed", result)
            self.assertEqual(result["agent"], "Finance Agent")
            self.assertEqual(result["trace"][0]["tool"], "finance_analytics")
            self.assertIsNone(result["approval_id"])
            return result["data"]["finance_report"]

        def metrics(result):
            return {item["label"]: Decimal(item["value"]) if item["value"] is not None else None for item in result["metrics"]}

        empty = report("Show monthly collections for the last 12 months")
        self.assertEqual(len(empty["charts"][0]["labels"]), 12)
        self.assertFalse(empty["charts"][0]["has_activity"])
        self.assertEqual(metrics(empty)["Total completed collections"], 0)
        self.assertIsNone(metrics(report("Compare this month with last month"))["Collections change (%)"])
        unavailable = report("Forecast next month's collections")
        self.assertIsNone(metrics(unavailable)["Baseline forecast"])
        self.assertIn("Forecast unavailable", " ".join(unavailable["notes"]))

        with self.session_factory() as db:
            patient_id = db.get(Appointment, appointments["own"]).patient_id
            bills = [
                Bill(patient_id=patient_id, bill_number=number, total_amount=amount, status=status, created_at=datetime(2026, 5, 1))
                for number, amount, status in (
                    ("ANALYTICS-PARTIAL", 500, "Partially Paid"),
                    ("ANALYTICS-UNPAID", 200, "Pending"),
                    ("ANALYTICS-CANCELLED", 1000, "Cancelled"),
                )
            ]
            db.add_all(bills)
            db.flush()
            bill_id = bills[0].id
            for when, amount, status in (
                (datetime(2026, 7, 5), "20.00", "Completed"),
                (datetime(2026, 10, 1), "100.10", "Completed"),
                (datetime(2026, 10, 31, 18, 29), "25.10", "Completed"),
                (datetime(2026, 10, 31, 18, 30), "50.30", "Completed"),
                (datetime(2026, 11, 24), "30.20", "Completed"),
                (datetime(2026, 11, 25), "90.10", "Completed"),
                (datetime(2026, 11, 25), "999.00", "Failed"),
            ):
                db.add(Payment(bill_id=bill_id, amount=Decimal(amount), payment_method="Cash", payment_status=status, paid_at=when))
            for day, category, amount in ((date(2026, 11, 1), "Supplies", 10),
                                          (date(2026, 11, 24), "Supplies", 20),
                                          (date(2026, 11, 25), "Utilities", 15)):
                db.add(Expense(description="Fixture expense", category=category, amount=amount, payment_method="Cash", expense_date=day))
            db.commit()

        month = report("Show total revenue this month")
        self.assertEqual(month["timezone"], "Asia/Kolkata")
        self.assertEqual(month["currency"], "INR")
        self.assertEqual(metrics(month)["Total completed collections"], Decimal("170.60"))
        history = report("Show monthly collections for the last 12 months", self.headers)
        self.assertEqual(history["charts"][0]["series"][0]["values"][-2:], ["125.20", "170.60"])
        self.assertEqual(report("Show daily collections today")["charts"][0]["series"][0]["values"], ["90.10"])
        self.assertEqual(report("Show weekly collections")["charts"][0]["kind"], "line")
        categories = report("Which expense category costs us the most?")
        self.assertEqual(categories["charts"][0]["labels"], ["Supplies", "Utilities"])
        self.assertEqual(categories["charts"][0]["series"][0]["values"], ["30.00", "15.00"])
        performance = report("Compare revenue and expenses this month")
        self.assertEqual([chart["kind"] for chart in performance["charts"]], ["bar", "line"])
        self.assertEqual(metrics(performance)["Total recorded expenses"], 45)
        self.assertEqual(metrics(performance)["Recorded financial movement"], Decimal("125.60"))
        balance = report("Show outstanding payments")
        self.assertEqual(metrics(balance), {
            "Paid amount applied": Decimal("315.80"), "Outstanding amount": Decimal("384.20"),
            "Unpaid bills": 1, "Partially paid bills": 1,
        })
        dashboard = self.client.get("/api/dashboard/finance", headers=staff).json()
        self.assertEqual(dashboard["stats"]["outstanding_bills"], 384.20)
        monthly = report("Compare this month with last month")
        self.assertEqual(monthly["charts"][0]["labels"], ["2026-11-01 to 2026-11-24", "2026-10-01 to 2026-10-24"])
        self.assertEqual(metrics(monthly)["Collections change"], Decimal("-19.60"))
        self.assertEqual(metrics(monthly)["Collections change (%)"], Decimal("-19.58"))
        quarterly = report("Show quarterly financial performance")
        self.assertEqual(quarterly["charts"][0]["series"][0]["values"], ["205.70", "20.00"])
        self.assertEqual(metrics(quarterly)["Collections change"], Decimal("185.70"))
        restored = self.client.get("/api/ai/conversations/latest", headers=staff).json()
        self.assertEqual(restored["last_response"]["data"]["finance_report"], quarterly)
        gemini.assert_not_called()

        with self.session_factory() as db:
            for month_number in (5, 6, 8, 9):
                db.add(Payment(bill_id=bill_id, amount=10, payment_method="Cash", payment_status="Completed",
                               paid_at=datetime(2026, month_number, 2)))
            db.add_all(Expense(description="Historical observation", category="Supplies", amount=5, payment_method="Cash",
                               expense_date=date(2026, 10, day)) for day in range(1, 9))
            db.commit()
        forecast = report("Forecast next month's collections")
        self.assertEqual(metrics(forecast)["Baseline forecast"], Decimal("30.87"))
        self.assertEqual((forecast["start_date"], forecast["end_date"]), ("2026-12-01", "2026-12-31"))
        candidates = report("Identify unusual expenses")
        self.assertEqual(metrics(candidates)["Candidates"], 1)
        self.assertIn("threshold ₹15.00 (n=8)", candidates["metrics"][1]["label"])
        self.assertEqual(report("Show department expense breakdown")["charts"], [])

        for role in ("patient", "doctor"):
            result = ask("Show monthly collections for the last 12 months", headers[role])
            self.assertNotIn("finance_report", result["data"])

    def test_finance_chart_schema_and_approval_gated_payment(self):
        from pydantic import ValidationError
        from app.schemas.finance_analytics import FinanceChart

        with self.assertRaises(ValidationError):
            FinanceChart.model_validate({
                "title": "Bad chart", "kind": "line", "labels": ["Nov"], "has_activity": True,
                "series": [{"label": "Collections", "values": ["1", "2"]}],
            })
        headers, appointments, _, _ = self._cancellation_fixture()
        with self.session_factory() as db:
            patient_id = db.get(Appointment, appointments["own"]).patient_id
            bill = Bill(patient_id=patient_id, bill_number="ANALYTICS-APPROVAL", total_amount=100, status="Pending")
            db.add(bill)
            db.commit()
            bill_id = bill.id

        class Call:
            name = "record_payment"
            args = {"bill_id": bill_id, "amount": 20, "payment_method": "Cash"}

        class Response:
            function_calls = [Call()]

        with patch("app.ai.orchestrator._gemini_response", return_value=Response()):
            response = self.client.post("/api/ai/chat", headers=headers["staff"], json={"query": "Record payment"})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["status"], "approval_required")
        with self.session_factory() as db:
            self.assertEqual(db.query(Payment).count(), 0)
        approval = self.client.post(f"/api/ai/approvals/{response.json()['approval_id']}/approve", headers=headers["staff"])
        self.assertEqual(approval.status_code, 200, approval.text)
        with self.session_factory() as db:
            self.assertEqual(db.query(Payment).one().amount, Decimal("20.00"))

    def test_gemini_mocked_function_call_executes_registered_tool(self):
        class Call:
            name = "search_doctors"
            args = {"specialization": "Cardiology", "limit": 5}

        class Response:
            function_calls = [Call()]
            text = "Cardiology doctors retrieved from the database."

        with patch("app.ai.orchestrator._gemini_response", return_value=Response()):
            response = self.client.post(
                "/api/ai/chat",
                headers=self.headers,
                json={"query": "Find cardiology doctors"},
            )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["agent"], "Hospital Operations Agent")
        self.assertEqual(body["trace"][0]["tool"], "search_doctors")
        self.assertEqual(body["trace"][0]["status"], "success")

    def test_ai_approval_rejection_and_expiry_are_enforced(self):
        db = self.session_factory()
        try:
            admin = db.query(User).filter(User.email == "admin@example.com").first()
            rejected = AIApproval(
                id="reject-test",
                conversation_id="test-conversation",
                user_id=admin.id,
                action="cancel_appointment",
                parameters_json={"appointment_id": 999},
                status="pending",
                expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
            )
            expired = AIApproval(
                id="expired-test",
                conversation_id="test-conversation",
                user_id=admin.id,
                action="cancel_appointment",
                parameters_json={"appointment_id": 999},
                status="pending",
                expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),
            )
            db.add_all([rejected, expired])
            db.commit()
        finally:
            db.close()

        rejected_response = self.client.post(
            "/api/ai/approvals/reject-test/reject",
            headers=self.headers,
        )
        self.assertEqual(rejected_response.status_code, 200)
        self.assertEqual(rejected_response.json()["status"], "rejected")

        expired_response = self.client.post(
            "/api/ai/approvals/expired-test/approve",
            headers=self.headers,
        )
        self.assertEqual(expired_response.status_code, 410)

    def test_ai_reschedule_requires_approval_and_executes(self):
        patient = self.client.post(
            "/api/patients/",
            headers=self.headers,
            json={"name": "Reschedule Patient", "age": 29, "email": "reschedule@example.com"},
        ).json()
        doctor = self.client.post(
            "/api/doctors/",
            headers=self.headers,
            json={
                "name": "Reschedule Doctor",
                "specialization": "Neurology",
                "email": "reschedule-doctor@example.com",
            },
        ).json()
        first_day = datetime.now() + timedelta(days=1)
        second_day = datetime.now() + timedelta(days=2)
        for day in (first_day, second_day):
            self.client.post(
                "/api/availability/",
                headers=self.headers,
                params={
                    "doctor_id": doctor["id"],
                    "day_of_week": day.strftime("%A"),
                    "start_time": "09:00:00",
                    "end_time": "17:00:00",
                },
            )
        appointment = self.client.post(
            "/api/appointments/",
            headers=self.headers,
            params={
                "patient_id": patient["id"],
                "doctor_id": doctor["id"],
                "appointment_date": first_day.replace(hour=10, minute=0, second=0, microsecond=0).isoformat(),
            },
        ).json()["appointment"]

        class Call:
            name = "reschedule_appointment"
            args = {
                "appointment_id": appointment["id"],
                "appointment_date": second_day.strftime("%Y-%m-%d"),
                "appointment_time": "11:00",
            }

        class Response:
            function_calls = [Call()]
            text = "Reschedule proposed."

        with patch("app.ai.orchestrator._gemini_response", return_value=Response()):
            proposed = self.client.post(
                "/api/ai/chat",
                headers=self.headers,
                json={
                    "query": (
                        f"Reschedule appointment {appointment['id']} "
                        f"to {second_day.strftime('%Y-%m-%d')} at 11:00"
                    )
                },
            )

        self.assertEqual(proposed.status_code, 200)
        self.assertEqual(proposed.json()["status"], "approval_required")
        approval_id = proposed.json()["approval_id"]

        executed = self.client.post(
            f"/api/ai/approvals/{approval_id}/approve",
            headers=self.headers,
        )
        self.assertEqual(executed.status_code, 200)
        self.assertEqual(executed.json()["status"], "executed")
        self.assertIn("rescheduled successfully", executed.json()["result"]["message"])

    def test_ai_conversation_history_is_isolated_between_users(self):
        db = self.session_factory()
        try:
            from app.core.security import hash_password

            second_user = User(
                full_name="Second Staff",
                email="second@example.com",
                password_hash=hash_password("secure-password"),
                role="staff",
            )
            db.add(second_user)
            db.commit()
        finally:
            db.close()

        login = self.client.post(
            "/api/auth/login",
            json={
                "email": "second@example.com",
                "password": "secure-password",
                "role": "staff",
            },
        )
        self.assertEqual(login.status_code, 200)
        second_headers = {
            "Authorization": f"Bearer {login.json()['access_token']}"
        }

        first = self.client.post(
            "/api/ai/chat",
            headers=self.headers,
            json={"query": "Show me cardiology doctors"},
        )
        first_body = first.json()
        second = self.client.post(
            "/api/ai/chat",
            headers=second_headers,
            json={
                "query": "Show me cardiology doctors",
                "conversation_id": first_body["conversation_id"],
            },
        )
        self.assertEqual(second.status_code, 403)

        db = self.session_factory()
        try:
            second_user = db.query(User).filter(User.email == "second@example.com").first()
            second_messages = db.query(AIConversationMessage).filter(
                AIConversationMessage.user_id == second_user.id,
                AIConversationMessage.conversation_id == first_body["conversation_id"],
            ).count()
            self.assertEqual(second_messages, 0)
            admin = db.query(User).filter(User.email == "admin@example.com").first()
            admin_messages = db.query(AIConversationMessage).filter(
                AIConversationMessage.user_id == admin.id,
                AIConversationMessage.conversation_id == first_body["conversation_id"],
            ).count()
            self.assertGreater(admin_messages, 0)
        finally:
            db.close()

        clear = self.client.delete(
            f"/api/ai/conversations/{first_body['conversation_id']}",
            headers=second_headers,
        )
        self.assertEqual(clear.status_code, 204)

        db = self.session_factory()
        try:
            admin = db.query(User).filter(User.email == "admin@example.com").first()
            foreign_approval = AIApproval(
                id="foreign-approval",
                conversation_id=first_body["conversation_id"],
                user_id=admin.id,
                action="cancel_appointment",
                parameters_json={"appointment_id": 999},
                status="pending",
                expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
            )
            db.add(foreign_approval)
            db.commit()
        finally:
            db.close()

        unauthorized = self.client.post(
            "/api/ai/approvals/foreign-approval/approve",
            headers=second_headers,
        )
        self.assertEqual(unauthorized.status_code, 403)

    def test_latest_conversations_are_restored_per_authenticated_role(self):
        db = self.session_factory()
        try:
            users = [
                User(full_name="Restore Patient", email="restore.patient@example.com", password_hash=security.hash_password("patient-password"), role="patient", is_active=True, approval_status="approved"),
                User(full_name="Restore Clinician", email="restore.clinician@example.com", password_hash=security.hash_password("doctor-password"), role="clinician", is_active=True, approval_status="approved"),
                User(full_name="Restore Staff", email="restore.staff@example.com", password_hash=security.hash_password("staff-password"), role="staff", is_active=True, approval_status="approved"),
            ]
            db.add_all(users)
            db.flush()
            db.add_all([
                Patient(name="Restore Patient", age=30, email="restore.patient@example.com", user_id=users[0].id),
                Doctor(name="Restore Clinician", specialization="Cardiology", email="restore.clinician.profile@example.com", user_id=users[1].id),
            ])
            db.commit()
        finally:
            db.close()

        def auth(email, password, role):
            result = self.client.post("/api/auth/login", json={"email": email, "password": password, "role": role})
            self.assertEqual(result.status_code, 200)
            return {"Authorization": f"Bearer {result.json()['access_token']}"}

        patient_headers = auth("restore.patient@example.com", "patient-password", "patient")
        clinician_headers = auth("restore.clinician@example.com", "doctor-password", "clinician")
        staff_headers = auth("restore.staff@example.com", "staff-password", "staff")
        no_tools = type("NoToolCalls", (), {"function_calls": [], "text": ""})()

        with patch("app.ai.orchestrator._gemini_response", return_value=no_tools):
            patient_chat = self.client.post("/api/ai/chat", headers=patient_headers, json={"query": "I need system support"})
            clinician_chat = self.client.post("/api/ai/chat", headers=clinician_headers, json={"query": "Where is my dashboard?"})
            staff_chat = self.client.post("/api/ai/chat", headers=staff_headers, json={"query": "Where is my dashboard?"})
            admin_chat = self.client.post("/api/ai/chat", headers=self.headers, json={"query": "Where is my dashboard?"})
        chats = (
            (patient_headers, patient_chat),
            (clinician_headers, clinician_chat),
            (staff_headers, staff_chat),
            (self.headers, admin_chat),
        )
        conversation_ids = set()
        for headers, response in chats:
            self.assertEqual(response.status_code, 200)
            conversation_id = response.json()["conversation_id"]
            conversation_ids.add(conversation_id)
            restored = self.client.get("/api/ai/conversations/latest", headers=headers)
            self.assertEqual(restored.status_code, 200)
            self.assertEqual(restored.json()["conversation_id"], conversation_id)
            self.assertEqual(restored.json()["messages"][-1]["content"], response.json()["message"])
        self.assertEqual(len(conversation_ids), 4)

        first_patient_conversation = patient_chat.json()["conversation_id"]
        with patch("app.ai.orchestrator._gemini_response", return_value=no_tools):
            second_patient_chat = self.client.post("/api/ai/chat", headers=patient_headers, json={"query": "Where is my dashboard?"})
        self.assertEqual(second_patient_chat.status_code, 200)
        self.assertNotEqual(second_patient_chat.json()["conversation_id"], first_patient_conversation)
        latest_patient = self.client.get("/api/ai/conversations/latest", headers=patient_headers)
        self.assertEqual(latest_patient.json()["conversation_id"], second_patient_chat.json()["conversation_id"])

        cross_user = self.client.post("/api/ai/chat", headers=clinician_headers, json={
            "query": "Continue this conversation",
            "conversation_id": second_patient_chat.json()["conversation_id"],
        })
        self.assertEqual(cross_user.status_code, 403)

    def test_conversation_deletion_removes_messages_and_all_associated_approvals(self):
        no_tools = type("NoToolCalls", (), {"function_calls": [], "text": ""})()
        with patch("app.ai.orchestrator._gemini_response", return_value=no_tools):
            chat = self.client.post("/api/ai/chat", headers=self.headers, json={"query": "I need system support"})
        self.assertEqual(chat.status_code, 200)
        conversation_id = chat.json()["conversation_id"]

        db = self.session_factory()
        try:
            admin = db.query(User).filter(User.email == "admin@example.com").first()
            db.add_all([
                AIApproval(id="delete-pending", conversation_id=conversation_id, user_id=admin.id, action="create_appointment", parameters_json={"doctor_id": 1}, status="pending", expires_at=datetime.now(timezone.utc) + timedelta(minutes=10)),
                AIApproval(id="delete-executed", conversation_id=conversation_id, user_id=admin.id, action="record_payment", parameters_json={"bill_id": 1}, status="executed", expires_at=datetime.now(timezone.utc) + timedelta(minutes=10)),
            ])
            db.commit()
        finally:
            db.close()

        deleted = self.client.delete(f"/api/ai/conversations/{conversation_id}", headers=self.headers)
        self.assertEqual(deleted.status_code, 204)
        latest = self.client.get("/api/ai/conversations/latest", headers=self.headers)
        self.assertEqual(latest.status_code, 200)
        self.assertIsNone(latest.json()["conversation_id"])
        unavailable = self.client.post("/api/ai/chat", headers=self.headers, json={
            "query": "Continue this conversation",
            "conversation_id": conversation_id,
        })
        self.assertEqual(unavailable.status_code, 404)
        db = self.session_factory()
        try:
            self.assertEqual(db.query(AIConversationMessage).filter(AIConversationMessage.conversation_id == conversation_id).count(), 0)
            self.assertEqual(db.query(AIApproval).filter(AIApproval.conversation_id == conversation_id).count(), 0)
        finally:
            db.close()

    def test_expired_conversation_confirmation_restores_without_approval_actions(self):
        db = self.session_factory()
        try:
            user = db.query(User).filter(User.email == "admin@example.com").first()
            conversation_id = "expired-restore-conversation"
            db.add_all([
                AIConversationMessage(user_id=user.id, conversation_id=conversation_id, role="user", content="Book with Dr Rao"),
                AIConversationMessage(user_id=user.id, conversation_id=conversation_id, role="assistant", content="Review and confirm this appointment."),
                AIApproval(id="expired-restore-approval", conversation_id=conversation_id, user_id=user.id, action="create_appointment", parameters_json={"doctor_id": 1}, status="pending", expires_at=datetime.now(timezone.utc) - timedelta(minutes=1)),
            ])
            db.commit()
        finally:
            db.close()

        restored = self.client.get("/api/ai/conversations/latest", headers=self.headers)
        self.assertEqual(restored.status_code, 200)
        body = restored.json()
        self.assertEqual(body["conversation_id"], "expired-restore-conversation")
        self.assertIsNone(body["pending_approval"])
        self.assertTrue(body["expired_approval"])
        self.assertIn("expired", body["messages"][-1]["content"].lower())
        db = self.session_factory()
        try:
            approval = db.query(AIApproval).filter(AIApproval.id == "expired-restore-approval").first()
            self.assertEqual(approval.status, "expired")
        finally:
            db.close()

    def _cancellation_fixture(self):
        # Test databases recycle user IDs while the process-wide limiter retains its counters.
        self.enterContext(patch("app.api.ai.enforce_rate_limit"))
        with self.session_factory() as db:
            users = {
                name: User(full_name=name, email=f"{name}@cancel.example", password_hash="unused",
                           role=role, is_active=True, approval_status="approved")
                for name, role in (
                    ("patient", "patient"), ("other_patient", "patient"),
                    ("doctor", "clinician"), ("other_doctor", "clinician"), ("staff", "staff"),
                )
            }
            db.add_all(users.values())
            db.flush()
            patient = Patient(name="Cancellation Patient", age=30, user_id=users["patient"].id)
            other_patient = Patient(name="Other Patient", age=30, user_id=users["other_patient"].id)
            doctor = Doctor(name="Review Doctor", specialization="Cardiology", email="review@cancel.example",
                            user_id=users["doctor"].id)
            other_doctor = Doctor(name="Other Doctor", specialization="Cardiology", email="other@cancel.example",
                                  user_id=users["other_doctor"].id)
            db.add_all([patient, other_patient, doctor, other_doctor])
            db.flush()
            start = (datetime.now() + timedelta(days=7)).replace(hour=9, minute=0, second=0, microsecond=0)
            appointments = {
                "own": Appointment(patient_id=patient.id, doctor_id=doctor.id, appointment_date=start, status="Scheduled"),
                "foreign": Appointment(patient_id=other_patient.id, doctor_id=doctor.id,
                                       appointment_date=start + timedelta(hours=1), status="Scheduled"),
                "past": Appointment(patient_id=patient.id, doctor_id=doctor.id,
                                    appointment_date=start - timedelta(days=8), status="Scheduled"),
                "completed": Appointment(patient_id=patient.id, doctor_id=doctor.id,
                                         appointment_date=start + timedelta(hours=2), status="Completed"),
                "booking": Appointment(patient_id=patient.id, doctor_id=doctor.id,
                                       appointment_date=start + timedelta(hours=3), status="Pending Doctor Approval"),
            }
            db.add_all(appointments.values())
            db.add(DoctorAvailability(doctor_id=doctor.id, day_of_week=start.strftime("%A"),
                                      start_time=start.time(), end_time=(start + timedelta(hours=4)).time(),
                                      is_available=True))
            db.commit()
            headers = {name: {"Authorization": f"Bearer {security.create_access_token(user)}"} for name, user in users.items()}
            return headers, {name: item.id for name, item in appointments.items()}, doctor.id, start

    def _cancellation_chat(self, headers, query="Cancel my booking", conversation=None):
        response = self.client.post("/api/ai/chat", headers=headers, json={"query": query, "conversation_id": conversation})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def _select_cancellation(self, headers, conversation, appointment):
        return self.client.post(f"/api/ai/conversations/{conversation}/cancellation-selection",
                                headers=headers, json={"appointment_id": appointment})

    def _cancellation_slot(self, headers, doctor_id, start):
        response = self.client.get(f"/api/availability/slots/{doctor_id}", headers=headers,
                                   params={"date": start.date().isoformat()})
        self.assertEqual(response.status_code, 200, response.text)
        return next(slot["status"] for slot in response.json()["slots"] if slot["start"] == start.isoformat())

    def test_doctor_dashboard_prompts_use_authenticated_routing_after_support_fallback(self):
        headers, appointments, _, _ = self._cancellation_fixture()
        conversation_id = "doctor-dashboard-routing-regression"
        fallback = "Please describe whether you need hospital, billing, appointment, or technical support."
        with self.session_factory() as db:
            doctor_user_id = db.get(Appointment, appointments["own"]).doctor.user_id
            db.add_all([
                AIConversationMessage(user_id=doctor_user_id, conversation_id=conversation_id,
                                      role="user", content="Give me my daily briefing"),
                AIConversationMessage(user_id=doctor_user_id, conversation_id=conversation_id,
                                      role="assistant", content=fallback),
            ])
            db.commit()

        prompts = (
            ("Give me my daily briefing", "doctor_daily_briefing"),
            ("What appointments do I have this week?", "doctor_daily_briefing"),
            ("Show my pending appointment requests", "doctor_daily_briefing"),
            ("Show my pending cancellation requests", "doctor_daily_briefing"),
            ("Compare this week with last week", "doctor_weekly_workload"),
            ("Show my assigned patients", "doctor_patient_timeline"),
        )
        with patch("app.ai.orchestrator._gemini_response", side_effect=ConnectionError("offline")) as gemini:
            for query, tool in prompts:
                with self.subTest(query=query):
                    response = self.client.post("/api/ai/chat", headers=headers["doctor"], json={
                        "query": query, "conversation_id": conversation_id, "role": "patient",
                    })
                    self.assertEqual(response.status_code, 200, response.text)
                    result = response.json()
                    self.assertEqual(result["agent"], "Doctor AI Agent")
                    self.assertEqual(result["status"], "completed")
                    self.assertEqual([entry["tool"] for entry in result["trace"]], [tool])
                    self.assertIn("doctor_intelligence", result["data"])
            gemini.assert_not_called()
            denied = self.client.post("/api/ai/chat", headers=headers["patient"], json={
                "query": "Give me my daily briefing", "role": "clinician",
            })
            self.assertEqual(denied.status_code, 200, denied.text)
            self.assertEqual(denied.json()["agent"], "Customer Support Agent")
            self.assertEqual(denied.json()["message"], fallback)
            self.assertNotIn("doctor_intelligence", denied.json()["data"])

    def test_doctor_week_boundaries_counts_and_trace_on_november_2026_dates(self):
        headers, appointments, doctor_id, _ = self._cancellation_fixture()
        upcoming = [datetime(2026, 11, 30, hour, minute) for hour, minute in ((11, 0), (14, 30), (15, 30))]
        with self.session_factory() as db:
            patient_id = db.get(Appointment, appointments["own"]).patient_id
            for index, appointment_id in enumerate(appointments.values()):
                db.get(Appointment, appointment_id).appointment_date = datetime(2026, 10, 1, 9) + timedelta(hours=index)
            db.add_all(Appointment(doctor_id=doctor_id, patient_id=patient_id, appointment_date=when, status="Scheduled")
                       for when in upcoming)
            db.commit()

        def ask(prompt, tool):
            response = self.client.post("/api/ai/chat", headers=headers["doctor"], json={"query": prompt})
            self.assertEqual(response.status_code, 200, response.text)
            result = response.json()
            self.assertEqual(result["status"], "completed")
            self.assertEqual([(item["tool"], item["status"]) for item in result["trace"]], [(tool, "success")])
            return result["data"]["doctor_intelligence"]

        def workload():
            return ask("Compare this week with last week", "doctor_weekly_workload")["periods"]

        def counts(periods):
            return [tuple(period[key] for key in ("scheduled", "completed", "cancelled")) for period in periods]

        with patch("app.services.doctor_intelligence.datetime", wraps=datetime) as clock:
            clock.now.return_value = datetime(2026, 11, 25, 12)
            daily = ask("Give me my daily briefing", "doctor_daily_briefing")
            self.assertEqual(daily["date"], "2026-11-25")
            future = next(section["visits"] for section in daily["sections"] if section["title"] == "Upcoming scheduled visits")
            self.assertEqual([item["appointment_date"] for item in future], [when.isoformat() for when in upcoming])
            weekly = ask("What appointments do I have this week?", "doctor_daily_briefing")
            self.assertEqual(weekly["period"], {"start": "2026-11-23", "end": "2026-11-29"})
            self.assertEqual(weekly["sections"][0]["visits"], [])
            comparison = workload()
            self.assertEqual([(period["start"], period["end"]) for period in comparison],
                             [("2026-11-23", "2026-11-29"), ("2026-11-16", "2026-11-22")])
            self.assertEqual(counts(comparison), [(0, 0, 0), (0, 0, 0)])

            with self.session_factory() as db:
                db.add_all([
                    Appointment(doctor_id=doctor_id, patient_id=patient_id, appointment_date=datetime(2026, 11, 23),
                                status="Scheduled", cancellation_status="Pending Doctor Approval"),
                    Appointment(doctor_id=doctor_id, patient_id=patient_id, appointment_date=datetime(2026, 11, 23, 10),
                                status="Pending Doctor Approval"),
                    Appointment(doctor_id=doctor_id, patient_id=patient_id, appointment_date=datetime(2026, 11, 29, 23, 59),
                                status="Completed"),
                ])
                db.commit()
            self.assertEqual(counts(workload()), [(1, 1, 0), (0, 0, 0)])
            with self.session_factory() as db:
                db.add(Appointment(doctor_id=doctor_id, patient_id=patient_id, appointment_date=datetime(2026, 11, 16),
                                   status="Cancelled", cancellation_status="Approved"))
                db.commit()
            self.assertEqual(counts(workload()), [(1, 1, 0), (0, 0, 1)])

            clock.now.return_value = datetime(2026, 11, 30)
            next_week = ask("What appointments do I have this week?", "doctor_daily_briefing")
            self.assertEqual([item["appointment_date"] for item in next_week["sections"][0]["visits"]],
                             [when.isoformat() for when in upcoming])
            self.assertEqual(counts(workload()), [(3, 0, 0), (1, 1, 0)])

    def test_doctor_intelligence_is_scoped_and_works_without_gemini(self):
        from app.ai.orchestrator import DOCTOR_INTELLIGENCE_TOOLS, _gemini_declarations

        headers, appointments, doctor_id, _ = self._cancellation_fixture()
        clinician = headers["doctor"]
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        week = today - timedelta(days=today.weekday())
        with self.session_factory() as db:
            existing = db.get(Appointment, appointments["own"])
            patient_id = existing.patient_id
            existing.cancellation_status = "Pending Doctor Approval"
            existing.cancellation_requested_at = datetime.now(timezone.utc)
            db.add_all([
                Appointment(doctor_id=doctor_id, patient_id=patient_id, appointment_date=today + timedelta(hours=9), status="Scheduled"),
                Appointment(doctor_id=doctor_id, patient_id=patient_id, appointment_date=today + timedelta(hours=10), status="Completed"),
                Appointment(doctor_id=doctor_id, patient_id=patient_id, appointment_date=today + timedelta(hours=11), status="Completed"),
                Appointment(doctor_id=doctor_id, patient_id=patient_id, appointment_date=week - timedelta(hours=4), status="Cancelled", reason="Recorded reason"),
            ])
            db.commit()

        def ask(query, *, actor=clinician, expected=200, **options):
            response = self.client.post("/api/ai/chat", headers=actor, json={"query": query, **options})
            self.assertEqual(response.status_code, expected, response.text)
            return response.json()

        with patch("app.ai.orchestrator._gemini_response", side_effect=RuntimeError("offline")) as gemini:
            for prompt in ("Give me my daily briefing", "Summarize my day"):
                briefing = ask(prompt)
                self.assertEqual(briefing["agent"], "Doctor AI Agent")
                sections = {item["title"]: item["visits"] for item in briefing["data"]["doctor_intelligence"]["sections"]}
                self.assertEqual(len(sections["Scheduled today"]), 1)
                self.assertEqual(len(sections["Pending booking requests"]), 1)
                self.assertEqual(len(sections["Pending cancellation requests"]), 1)
                self.assertEqual(len(sections["Completed visits today"]), 2)
                self.assertIn("Upcoming scheduled visits", sections)
                self.assertNotIn("id", sections["Scheduled today"][0])
            empty = ask("What is my schedule today?", actor=headers["other_doctor"])
            self.assertEqual(empty["data"]["doctor_intelligence"]["sections"][0]["visits"], [])
            for prompt, title in (
                ("Show my pending appointment requests", "Pending booking requests"),
                ("Show my pending cancellation requests", "Pending cancellation requests"),
                ("What appointments do I have this week?", "Appointments this week"),
            ):
                self.assertEqual(ask(prompt)["data"]["doctor_intelligence"]["title"], title)
            completed = ask("How many patients have I seen today?")["data"]["doctor_intelligence"]["metrics"]
            self.assertEqual([metric["value"] for metric in completed], [2, 1])
            for prompt in ("Analyze my workload this week", "Compare this week with last week",
                           "Show my appointment trends", "How many appointments were cancelled?"):
                periods = ask(prompt)["data"]["doctor_intelligence"]["periods"]
                self.assertEqual((periods[0]["completed"], periods[1]["cancelled"]), (2, 1))
            assigned = ask("Show my assigned patients")
            self.assertIn(patient_id, {item["id"] for item in assigned["data"]["doctor_intelligence"]["patients"]})
            timeline = ask("Show this patient's appointment history", doctor_patient_id=patient_id,
                           conversation_id=assigned["conversation_id"])
            history = timeline["data"]["doctor_intelligence"]["sections"][0]["visits"]
            self.assertTrue(any(item["reason"] == "Recorded reason" and item["appointment_date"] for item in history))
            self.assertTrue(all(item["patient_name"] == "Cancellation Patient" for item in history))
            follow_up = ask("Summarize my previous visits with this patient", conversation_id=assigned["conversation_id"])
            self.assertEqual(follow_up["data"]["doctor_intelligence"], timeline["data"]["doctor_intelligence"])
            restored = self.client.get("/api/ai/conversations/latest", headers=clinician).json()
            self.assertEqual(restored["last_response"]["data"]["doctor_intelligence"], timeline["data"]["doctor_intelligence"])
            denied = ask("Show this patient's appointment history", actor=headers["other_doctor"], doctor_patient_id=patient_id)
            self.assertEqual(denied["status"], "error")
            self.assertEqual(denied["data"], {})
            ask("Show this patient's appointment history", actor=headers["patient"], doctor_patient_id=patient_id, expected=403)
            gemini.assert_not_called()

        self.assertTrue(DOCTOR_INTELLIGENCE_TOOLS <= {item.name for item in _gemini_declarations("clinician")})
        for role in ("patient", "staff", "admin"):
            self.assertFalse(DOCTOR_INTELLIGENCE_TOOLS & {item.name for item in _gemini_declarations(role)})

        class DoctorCall:
            name = "doctor_daily_briefing"
            args = {}

        class ModelResponse:
            function_calls = [DoctorCall()]

        with patch("app.ai.orchestrator._gemini_response", return_value=ModelResponse()):
            denied = ask("Please run the tool", actor=headers["patient"])
        self.assertEqual(denied["status"], "error")
        self.assertIn("permission", denied["message"])
        self.assertEqual(denied["data"], {})

    def test_cancellation_routing_filters_owned_cards_and_restores_the_picker(self):
        headers, appointments, _, start = self._cancellation_fixture()
        patient = headers["patient"]
        with self.session_factory() as db:
            original = db.get(Appointment, appointments["own"])
            original.doctor.name = "Hritik Sharma"
            other_doctor = db.query(Doctor).filter(Doctor.name == "Other Doctor").one()
            same_doctor = Appointment(patient_id=original.patient_id, doctor_id=original.doctor_id,
                                      appointment_date=start + timedelta(days=1), status="Scheduled")
            other_visit = Appointment(patient_id=original.patient_id, doctor_id=other_doctor.id,
                                      appointment_date=start + timedelta(days=2), status="Scheduled")
            db.add_all([same_doctor, other_visit])
            db.commit()
            same_doctor_id, other_visit_id = same_doctor.id, other_visit.id
            db.add_all([
                AIConversationMessage(user_id=original.patient.user_id, conversation_id="old-cancellation",
                                      role="user", content="Cancel my appointment"),
                AIConversationMessage(user_id=original.patient.user_id, conversation_id="old-cancellation",
                                      role="assistant", content="I could not find that doctor. Please provide the doctor name or specialization."),
            ])
            db.commit()

        with (
            patch("app.ai.orchestrator._gemini_response") as model,
            patch("app.ai.orchestrator._patient_appointment_conversation") as booking,
            patch("app.ai.orchestrator._resolve_doctor") as directory,
            patch("app.ai.orchestrator.REGISTRY.execute") as tools,
        ):
            for query in ("Cancel my appointment", "I need to cancel an appointment", "Cancel my appointment with Dr.Hritik"):
                chat = self._cancellation_chat(patient, query)
                self.assertEqual(chat["agent"], "Hospital Operations Agent")
                self.assertEqual([card["id"] for card in chat["data"]["cancellation_options"]],
                                 [appointments["own"], same_doctor_id, other_visit_id])
                self.assertIsNone(chat["approval_id"])

            conversation = chat["conversation_id"]
            for current_conversation in ("old-cancellation", conversation):
                filtered = self._cancellation_chat(patient, "Dr.Hritik", current_conversation)
                self.assertEqual(filtered["agent"], "Hospital Operations Agent")
                self.assertIn("correct date and time", filtered["message"])
                self.assertEqual([card["id"] for card in filtered["data"]["cancellation_options"]],
                                 [appointments["own"], same_doctor_id])
                self.assertIsNone(filtered["approval_id"])
            restored = self.client.get("/api/ai/conversations/latest", headers=patient).json()
            self.assertEqual(restored["last_response"]["data"], filtered["data"])

            unmatched = self._cancellation_chat(patient, "Dr.Nobody", conversation)
            self.assertIn("No eligible appointment matches", unmatched["message"])
            self.assertEqual(len(unmatched["data"]["cancellation_options"]), 3)
            single = self._cancellation_chat(patient, "Dr.Other", conversation)
            self.assertEqual([card["id"] for card in single["data"]["cancellation_options"]], [other_visit_id])
            self.assertIsNone(single["approval_id"])

            selected = self._select_cancellation(patient, conversation, other_visit_id)
            self.assertEqual(selected.status_code, 200, selected.text)
            proposal = selected.json()
            self.assertEqual(proposal["status"], "approval_required")
            follow_up = self._cancellation_chat(patient, "Dr.Other", conversation)
            self.assertEqual(follow_up["approval_id"], proposal["approval_id"])
            restored = self.client.get("/api/ai/conversations/latest", headers=patient).json()
            self.assertEqual(restored["last_response"]["data"], proposal["data"])
            self.assertEqual(restored["pending_approval"]["id"], proposal["approval_id"])
            dashboard = self.client.get("/api/dashboard/doctor", headers=headers["other_doctor"]).json()
            self.assertEqual(dashboard["cancellation_requests"], [])

        for mock in (model, booking, directory, tools):
            mock.assert_not_called()

    def test_patient_cancellation_eligibility_explicit_confirmation_and_doctor_approval(self):
        headers, appointments, doctor_id, start = self._cancellation_fixture()
        patient = headers["patient"]
        for query in ("I want to cancel my appointment", "Cancel my booking", "I don't want to attend my appointment"):
            chat = self._cancellation_chat(patient, query)
            self.assertEqual([card["id"] for card in chat["data"]["cancellation_options"]], [appointments["own"]])
            self.assertIsNone(chat["approval_id"])
        conversation = chat["conversation_id"]
        restored = self.client.get("/api/ai/conversations/latest", headers=patient).json()
        self.assertEqual(restored["last_response"]["data"], chat["data"])
        self.assertEqual(self._select_cancellation(headers["other_patient"], conversation, appointments["own"]).status_code, 404)
        for ineligible in ("foreign", "past", "completed", "booking"):
            self.assertEqual(self._select_cancellation(patient, conversation, appointments[ineligible]).status_code, 404)

        path = f"/api/appointments/{appointments['own']}"
        self.assertEqual(self.client.delete(path, headers=patient).status_code, 403)
        for ineligible in ("past", "completed"):
            self.assertEqual(self.client.delete(f"/api/appointments/{appointments[ineligible]}", headers=self.headers).status_code, 409)
        selected = self._select_cancellation(patient, conversation, appointments["own"])
        self.assertEqual(selected.status_code, 200, selected.text)
        proposal = selected.json()
        self.assertEqual(proposal["status"], "approval_required")
        self.assertEqual(proposal["data"]["cancellation_selection"], chat["data"]["cancellation_options"][0])
        restored = self.client.get("/api/ai/conversations/latest", headers=patient).json()
        self.assertEqual(restored["last_response"]["data"], proposal["data"])
        self.assertEqual(restored["pending_approval"]["id"], proposal["approval_id"])
        self._cancellation_chat(patient, "confirm", conversation)
        before = self.client.get("/api/dashboard/doctor", headers=headers["doctor"]).json()
        self.assertEqual(before["cancellation_requests"], [])
        self.assertEqual([request["id"] for request in before["pending_requests"]], [appointments["booking"]])

        approval_path = f"/api/ai/approvals/{proposal['approval_id']}/approve"
        self.assertEqual(self.client.post(approval_path, headers=headers["other_patient"]).status_code, 403)
        confirmed = self.client.post(approval_path, headers=patient)
        self.assertEqual(confirmed.status_code, 200, confirmed.text)
        self.assertEqual(confirmed.json()["result"]["status"], "Pending Doctor Approval")
        self.assertEqual(self.client.post(approval_path, headers=patient).status_code, 409)
        self.assertEqual(self._cancellation_slot(patient, doctor_id, start), "booked")
        no_options = self._cancellation_chat(patient)
        self.assertEqual(no_options["data"]["cancellation_options"], [])
        self.assertIn("no upcoming appointments eligible", no_options["message"])
        pending_history = self.client.get("/api/dashboard/patient", headers=patient).json()["cancellation_history"]
        self.assertEqual(pending_history[0]["cancellation_status"], "Pending Doctor Approval")
        after = self.client.get("/api/dashboard/doctor", headers=headers["doctor"]).json()
        self.assertEqual(len(after["cancellation_requests"]), 1)
        request = after["cancellation_requests"][0]
        self.assertEqual(request["patient_name"], "Cancellation Patient")
        self.assertEqual(request["status"], "Pending Doctor Approval")
        self.assertEqual(request["appointment_date"], start.isoformat())
        self.assertTrue(request["requested_at"])
        self.assertEqual(self.client.get("/api/dashboard/doctor", headers=headers["other_doctor"]).json()["cancellation_requests"], [])
        decision = {"request_id": request["request_id"]}
        for role in ("patient", "staff", "other_doctor"):
            self.assertEqual(self.client.post(f"{path}/cancellation/approve", headers=headers[role], json=decision).status_code, 403)
        self.assertEqual(self.client.delete(path, headers=headers["doctor"]).status_code, 409)
        self.assertEqual(self.client.delete(f"/api/ai/conversations/{conversation}", headers=patient).status_code, 204)
        approved = self.client.post(f"{path}/cancellation/approve", headers=headers["doctor"], json=decision)
        self.assertEqual(approved.status_code, 200, approved.text)
        self.assertEqual(self._cancellation_slot(patient, doctor_id, start), "available")
        history = self.client.get("/api/dashboard/patient", headers=patient).json()["cancellation_history"]
        self.assertEqual((history[0]["cancellation_status"], history[0]["status"]), ("Approved", "Cancelled"))
        self.assertEqual(self.client.get("/api/dashboard/patient", headers=headers["other_patient"]).json()["cancellation_history"], [])
        self.assertEqual(self._cancellation_chat(patient)["data"]["cancellation_options"], [])

    def test_cancellation_rejection_retains_slot_and_stale_decisions_cannot_process_a_new_request(self):
        headers, appointments, doctor_id, start = self._cancellation_fixture()
        patient = headers["patient"]
        appointment_id = appointments["own"]
        path = f"/api/appointments/{appointment_id}/cancellation"

        def propose():
            conversation = self._cancellation_chat(patient)["conversation_id"]
            response = self._select_cancellation(patient, conversation, appointment_id)
            self.assertEqual(response.status_code, 200, response.text)
            return response.json()["approval_id"]

        def confirm(approval_id):
            return self.client.post(f"/api/ai/approvals/{approval_id}/approve", headers=patient)

        first, duplicate = propose(), propose()
        self.assertEqual(confirm(first).status_code, 200)
        self.assertEqual(confirm(duplicate).status_code, 409)
        rejected = self.client.post(f"{path}/reject", headers=headers["doctor"],
                                    json={"request_id": first, "reason": "  Please keep this follow-up.  "})
        self.assertEqual(rejected.status_code, 200, rejected.text)
        self.assertEqual(self._cancellation_slot(patient, doctor_id, start), "booked")
        history = self.client.get("/api/dashboard/patient", headers=patient).json()["cancellation_history"][0]
        self.assertEqual(history["status"], "Scheduled")
        self.assertEqual(history["cancellation_status"], "Rejected")
        self.assertEqual(history["cancellation_reason"], "Please keep this follow-up.")
        self.assertEqual(confirm(duplicate).status_code, 409)

        second = propose()
        self.assertEqual(confirm(second).status_code, 200)
        self.assertEqual(self.client.post(f"{path}/approve", headers=headers["doctor"], json={"request_id": first}).status_code, 409)
        with ThreadPoolExecutor(max_workers=2) as executor:
            decisions = [
                executor.submit(self.client.post, f"{path}/{action}", headers=actor, json={"request_id": second})
                for action, actor in (("approve", self.headers), ("reject", headers["doctor"]))
            ]
            responses = [decision.result() for decision in decisions]
        self.assertEqual(sorted(response.status_code for response in responses), [200, 409])
        expected_slot = "available" if responses[0].status_code == 200 else "booked"
        self.assertEqual(self._cancellation_slot(patient, doctor_id, start), expected_slot)

    def test_ai_cancel_requires_approval_and_executes_after_approval(self):
        patient = self.client.post(
            "/api/patients/",
            headers=self.headers,
            json={"name": "Approval Patient", "age": 30, "email": "approval@example.com"},
        ).json()
        doctor = self.client.post(
            "/api/doctors/",
            headers=self.headers,
            json={
                "name": "Approval Doctor",
                "specialization": "Cardiology",
                "email": "approval-doctor@example.com",
            },
        ).json()
        weekday = (datetime.now() + timedelta(days=1)).strftime("%A")
        self.client.post(
            "/api/availability/",
            headers=self.headers,
            params={
                "doctor_id": doctor["id"],
                "day_of_week": weekday,
                "start_time": "09:00:00",
                "end_time": "17:00:00",
            },
        )
        appointment = self.client.post(
            "/api/appointments/",
            headers=self.headers,
            params={
                "patient_id": patient["id"],
                "doctor_id": doctor["id"],
                "appointment_date": (
                    datetime.now() + timedelta(days=1)
                ).replace(hour=10, minute=0, second=0, microsecond=0).isoformat(),
            },
        ).json()["appointment"]

        class ProposedCall:
            name = "cancel_appointment"
            args = {"appointment_id": appointment["id"]}

        class ProposedResponse:
            function_calls = [ProposedCall()]
            text = "Cancellation proposed."

        with patch("app.ai.orchestrator._gemini_response", return_value=ProposedResponse()):
            proposed = self.client.post(
                "/api/ai/chat",
                headers=self.headers,
                json={"query": f"Cancel appointment {appointment['id']}"},
            )
        self.assertEqual(proposed.status_code, 200)
        proposed_body = proposed.json()
        self.assertEqual(proposed_body["status"], "approval_required")
        approval_id = proposed_body["approval_id"]
        self.assertIsNotNone(approval_id)

        executed = self.client.post(
            f"/api/ai/approvals/{approval_id}/approve",
            headers=self.headers,
        )
        self.assertEqual(executed.status_code, 200)
        self.assertEqual(executed.json()["status"], "executed")
        self.assertEqual(executed.json()["result"]["status"], "Cancelled")

        repeat = self.client.post(
            f"/api/ai/approvals/{approval_id}/approve",
            headers=self.headers,
        )
        self.assertEqual(repeat.status_code, 409)

        class CancelCall:
            name = "cancel_appointment"
            args = {"appointment_id": appointment["id"]}

        class CancelResponse:
            function_calls = [CancelCall()]
            text = "Cancellation proposed."

        with patch("app.ai.orchestrator._gemini_response", return_value=CancelResponse()):
            canceled_again = self.client.post(
                "/api/ai/chat",
                headers=self.headers,
                json={"query": f"Cancel appointment {appointment['id']}"},
            )
        self.assertEqual(canceled_again.status_code, 200)
        self.assertEqual(canceled_again.json()["status"], "error")
        self.assertIn("already cancelled", canceled_again.json()["message"].lower())


    def test_duplicate_patient_creation_returns_conflict(self):
        first = self.client.post(
            "/api/patients/",
            headers=self.headers,
            json={"name": "Duplicate Patient", "age": 30, "email": "duplicate@example.com"},
        )
        second = self.client.post(
            "/api/patients/",
            headers=self.headers,
            json={"name": "Duplicate Patient Again", "age": 31, "email": "duplicate@example.com"},
        )
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 409)

    def test_gemini_outage_availability_and_booking_fallback(self):
        patient = self.client.post(
            "/api/patients/",
            headers=self.headers,
            json={"name": "Fallback Patient", "age": 32, "email": "fallback@example.com"},
        ).json()
        doctor = self.client.post(
            "/api/doctors/",
            headers=self.headers,
            json={
                "name": "Fallback Doctor",
                "specialization": "Cardiology",
                "email": "fallback-doctor@example.com",
            },
        ).json()
        booking_date = (datetime.now() + timedelta(days=2)).date()
        weekday = booking_date.strftime("%A")
        self.client.post(
            "/api/availability/",
            headers=self.headers,
            params={
                "doctor_id": doctor["id"],
                "day_of_week": weekday,
                "start_time": "09:00:00",
                "end_time": "17:00:00",
            },
        )

        with patch(
            "app.ai.orchestrator._gemini_response",
            side_effect=RuntimeError("Gemini unavailable"),
        ):
            availability = self.client.post(
                "/api/ai/chat",
                headers=self.headers,
                json={"query": f"Show availability for doctor {doctor['id']}"},
            )
            date_text = booking_date.strftime("%Y-%m-%d")
            booking = self.client.post(
                "/api/ai/chat",
                headers=self.headers,
                json={
                    "query": (
                        f"Book appointment for patient {patient['id']} "
                        f"with doctor {doctor['id']} on {date_text} at 11:00"
                    )
                },
            )

        self.assertEqual(availability.status_code, 200)
        self.assertEqual(availability.json()["status"], "completed")
        self.assertEqual(availability.json()["agent"], "Hospital Operations Agent")
        self.assertEqual(booking.status_code, 200)
        self.assertEqual(booking.json()["status"], "approval_required")
        self.assertIsNotNone(booking.json()["approval_id"])

    def test_doctor_accounts_only_access_their_linked_appointments(self):
        db = self.session_factory()
        try:
            rithik_user = User(
                full_name="Rithik",
                email="rithik.isolation@example.com",
                password_hash=security.hash_password("doctor-password"),
                role="clinician",
                is_active=True,
                approval_status="approved",
            )
            amit_user = User(
                full_name="Amit Verma",
                email="amit.isolation@example.com",
                password_hash=security.hash_password("doctor-password"),
                role="clinician",
                is_active=True,
                approval_status="approved",
            )
            db.add_all([rithik_user, amit_user])
            db.flush()

            rithik = Doctor(
                name="Rithik",
                specialization="Cardiology",
                email="rithik.doctor@example.com",
                experience_years=5,
                user_id=rithik_user.id,
            )
            amit = Doctor(
                name="Amit Verma",
                specialization="Neurology",
                email="amit.doctor@example.com",
                experience_years=8,
                user_id=amit_user.id,
            )
            db.add_all([rithik, amit])
            db.flush()

            patient_a = Patient(name="Patient A", age=30, email="patient.a@example.com")
            patient_b = Patient(name="Patient B", age=31, email="patient.b@example.com")
            db.add_all([patient_a, patient_b])
            db.flush()

            rithik_appointments = [
                Appointment(patient_id=patient_a.id, doctor_id=rithik.id, appointment_date=datetime.now() + timedelta(days=1), status="Scheduled"),
                Appointment(patient_id=patient_b.id, doctor_id=rithik.id, appointment_date=datetime.now() + timedelta(days=2), status="Scheduled"),
            ]
            amit_appointments = [
                Appointment(patient_id=patient_a.id, doctor_id=amit.id, appointment_date=datetime.now() + timedelta(days=3), status="Scheduled"),
                Appointment(patient_id=patient_b.id, doctor_id=amit.id, appointment_date=datetime.now() + timedelta(days=4), status="Scheduled"),
            ]
            db.add_all(rithik_appointments + amit_appointments)
            db.commit()
            ids = {
                "rithik": [item.id for item in rithik_appointments],
                "amit": [item.id for item in amit_appointments],
                "rithik_user": rithik_user.id,
                "amit_user": amit_user.id,
            }
        finally:
            db.close()

        rithik_login = self.client.post(
            "/api/auth/login",
            json={"email": "rithik.isolation@example.com", "password": "doctor-password", "role": "clinician"},
        )
        amit_login = self.client.post(
            "/api/auth/login",
            json={"email": "amit.isolation@example.com", "password": "doctor-password", "role": "clinician"},
        )
        self.assertEqual(rithik_login.status_code, 200)
        self.assertEqual(amit_login.status_code, 200)
        rithik_headers = {"Authorization": f"Bearer {rithik_login.json()['access_token']}"}
        amit_headers = {"Authorization": f"Bearer {amit_login.json()['access_token']}"}

        rithik_list = self.client.get("/api/appointments/", headers=rithik_headers).json()
        amit_list = self.client.get("/api/appointments/", headers=amit_headers).json()
        self.assertEqual({item["id"] for item in rithik_list}, set(ids["rithik"]))
        self.assertEqual({item["id"] for item in amit_list}, set(ids["amit"]))

        for appointment_id in ids["amit"]:
            self.assertEqual(self.client.get(f"/api/appointments/{appointment_id}", headers=rithik_headers).status_code, 403)
            self.assertEqual(self.client.delete(f"/api/appointments/{appointment_id}", headers=rithik_headers).status_code, 403)
        for appointment_id in ids["rithik"]:
            self.assertEqual(self.client.get(f"/api/appointments/{appointment_id}", headers=amit_headers).status_code, 403)
            self.assertEqual(self.client.delete(f"/api/appointments/{appointment_id}", headers=amit_headers).status_code, 403)

        rithik_metrics = self.client.get("/api/dashboard/metrics", headers=rithik_headers)
        amit_metrics = self.client.get("/api/dashboard/metrics", headers=amit_headers)
        self.assertEqual(rithik_metrics.status_code, 200)
        self.assertEqual(amit_metrics.status_code, 200)
        self.assertEqual(rithik_metrics.json()["appointments_today"], 0)
        self.assertEqual(amit_metrics.json()["appointments_today"], 0)

        unlinked = User(
            full_name="Unlinked Doctor",
            email="unlinked.doctor@example.com",
            password_hash=security.hash_password("doctor-password"),
            role="clinician",
            is_active=True,
            approval_status="approved",
        )
        db = self.session_factory()
        try:
            db.add(unlinked)
            db.commit()
        finally:
            db.close()
        unlinked_login = self.client.post(
            "/api/auth/login",
            json={"email": "unlinked.doctor@example.com", "password": "doctor-password", "role": "clinician"},
        )
        self.assertEqual(unlinked_login.status_code, 200)
        unlinked_headers = {"Authorization": f"Bearer {unlinked_login.json()['access_token']}"}
        self.assertEqual(self.client.get("/api/appointments/", headers=unlinked_headers).status_code, 403)
        self.assertEqual(self.client.get("/api/dashboard/metrics", headers=unlinked_headers).status_code, 403)

    def test_patient_records_are_scoped_to_clinician_appointments(self):
        db = self.session_factory()
        try:
            clinician_user = User(full_name="Assigned Clinician", email="assigned.clinician@example.com", password_hash=security.hash_password("doctor-password"), role="clinician", is_active=True, approval_status="approved")
            staff_user = User(full_name="Patient Staff", email="patient.staff@example.com", password_hash=security.hash_password("staff-password"), role="staff", is_active=True, approval_status="approved")
            db.add_all([clinician_user, staff_user])
            db.flush()
            doctor = Doctor(name="Assigned Clinician", specialization="Cardiology", email="assigned.clinician.profile@example.com", user_id=clinician_user.id)
            assigned = Patient(name="Assigned Patient", age=36, email="assigned.record@example.com")
            unrelated = Patient(name="Unrelated Patient", age=42, email="unrelated.record@example.com")
            db.add_all([doctor, assigned, unrelated])
            db.flush()
            db.add(Appointment(patient_id=assigned.id, doctor_id=doctor.id, appointment_date=datetime.now() + timedelta(days=20), status="Scheduled"))
            db.commit()
            assigned_id, unrelated_id = assigned.id, unrelated.id
        finally:
            db.close()

        def login(email, password, role):
            response = self.client.post("/api/auth/login", json={"email": email, "password": password, "role": role})
            self.assertEqual(response.status_code, 200)
            return {"Authorization": f"Bearer {response.json()['access_token']}"}

        clinician_headers = login("assigned.clinician@example.com", "doctor-password", "clinician")
        staff_headers = login("patient.staff@example.com", "staff-password", "staff")

        listing = self.client.get("/api/patients/", headers=clinician_headers, params={"search": "Patient", "sort": "name", "order": "asc", "offset": 0, "limit": 1})
        self.assertEqual(listing.status_code, 200)
        self.assertEqual([item["id"] for item in listing.json()], [assigned_id])
        unrelated_search = self.client.get("/api/patients/", headers=clinician_headers, params={"search": "Unrelated", "sort": "name", "order": "desc", "limit": 1})
        self.assertEqual(unrelated_search.status_code, 200)
        self.assertEqual(unrelated_search.json(), [])
        paginated = self.client.get("/api/patients/", headers=clinician_headers, params={"sort": "name", "order": "desc", "offset": 1, "limit": 1})
        self.assertEqual(paginated.status_code, 200)
        self.assertEqual(paginated.json(), [])
        self.assertEqual(self.client.get(f"/api/patients/{assigned_id}", headers=clinician_headers).status_code, 200)
        self.assertEqual(self.client.get(f"/api/patients/{unrelated_id}", headers=clinician_headers).status_code, 404)

        update_payload = {"name": "Changed Name", "age": 42, "email": "unrelated.record@example.com"}
        unrelated_update = self.client.put(f"/api/patients/{unrelated_id}", headers=clinician_headers, json=update_payload)
        self.assertEqual(unrelated_update.status_code, 404)
        self.assertEqual(self.client.delete(f"/api/patients/{unrelated_id}", headers=clinician_headers).status_code, 403)
        assigned_update = self.client.put(f"/api/patients/{assigned_id}", headers=clinician_headers, json={"name": "Assigned Patient Updated", "age": 36, "email": "assigned.record@example.com"})
        self.assertEqual(assigned_update.status_code, 200)

        for headers in (self.headers, staff_headers):
            all_patients = self.client.get("/api/patients/", headers=headers, params={"limit": 10})
            self.assertEqual({item["id"] for item in all_patients.json()}, {assigned_id, unrelated_id})
            self.assertEqual(self.client.get(f"/api/patients/{unrelated_id}", headers=headers).status_code, 200)
            update = self.client.put(f"/api/patients/{unrelated_id}", headers=headers, json=update_payload)
            self.assertEqual(update.status_code, 200)

    def test_alternative_appointment_dates_have_real_free_slots(self):
        db = self.session_factory()
        try:
            doctor_user = User(full_name="Availability Clinician", email="availability.clinician@example.com", password_hash=security.hash_password("doctor-password"), role="clinician", is_active=True, approval_status="approved")
            patient_users = [
                User(full_name=f"Availability Patient {index}", email=f"availability.patient{index}@example.com", password_hash=security.hash_password("patient-password"), role="patient", is_active=True, approval_status="approved")
                for index in range(1, 4)
            ]
            db.add_all([doctor_user, *patient_users])
            db.flush()
            doctor = Doctor(name="Availability Clinician", specialization="Cardiology", email="availability.profile@example.com", user_id=doctor_user.id, appointment_duration_minutes=30)
            patients = [Patient(name=f"Availability Patient {index}", age=30, email=f"availability.patient{index}@example.com", user_id=user.id) for index, user in enumerate(patient_users, start=1)]
            db.add_all([doctor, *patients])
            db.flush()
            base_date = (datetime.now() + timedelta(days=21)).date()
            full_date, partial_date = base_date + timedelta(days=1), base_date + timedelta(days=2)
            for candidate in (full_date, partial_date):
                db.add(DoctorAvailability(doctor_id=doctor.id, day_of_week=candidate.strftime("%A"), specific_date=candidate, start_time=datetime.strptime("09:00", "%H:%M").time(), end_time=datetime.strptime("10:00", "%H:%M").time(), is_available=True))
            db.flush()
            db.add_all([
                Appointment(patient_id=patients[0].id, doctor_id=doctor.id, appointment_date=datetime.combine(full_date, datetime.strptime("09:00", "%H:%M").time()), status="Pending Doctor Approval"),
                Appointment(patient_id=patients[1].id, doctor_id=doctor.id, appointment_date=datetime.combine(full_date, datetime.strptime("09:30", "%H:%M").time()), status="Scheduled"),
                Appointment(patient_id=patients[2].id, doctor_id=doctor.id, appointment_date=datetime.combine(partial_date, datetime.strptime("09:00", "%H:%M").time()), status="Pending Doctor Approval"),
            ])
            db.commit()
            doctor_id = doctor.id
        finally:
            db.close()

        login = self.client.post("/api/auth/login", json={"email": "availability.patient1@example.com", "password": "patient-password", "role": "patient"})
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
        result = self.client.get(f"/api/availability/slots/{doctor_id}", headers=headers, params={"date": base_date.isoformat()})
        self.assertEqual(result.status_code, 200)
        alternatives = result.json()["alternatives"]
        self.assertNotIn(full_date.isoformat(), alternatives)
        self.assertIn(partial_date.isoformat(), alternatives)
        self.assertTrue(all(result.json()["slots"][i]["status"] != "available" for i in range(len(result.json()["slots"]))))

        # A suggestion must still contain an unoccupied interval after checking
        # the same pending/scheduled appointment rules used for the requested date.
        for alternative in alternatives:
            slots = self.client.get(f"/api/availability/slots/{doctor_id}", headers=headers, params={"date": alternative}).json()["slots"]
            self.assertTrue(any(slot["status"] == "available" for slot in slots), alternative)

        partial = self.client.get(f"/api/availability/slots/{doctor_id}", headers=headers, params={"date": partial_date.isoformat()}).json()
        self.assertEqual([slot["status"] for slot in partial["slots"]], ["booked", "available"])

    def test_doctor_request_approval_scope_status_and_decline_releases_slot(self):
        target = (datetime.now() + timedelta(days=10)).replace(hour=0, minute=0, second=0, microsecond=0)
        db = self.session_factory()
        try:
            doctor_users = [
                User(full_name=name, email=f"{slug}.workflow@example.com", password_hash=security.hash_password("doctor-password"), role="clinician", is_active=True, approval_status="approved")
                for name, slug in (("Workflow Doctor One", "workflow1"), ("Workflow Doctor Two", "workflow2"))
            ]
            patient_users = [
                User(full_name=f"Workflow Patient {index}", email=f"workflow.patient{index}@example.com", password_hash=security.hash_password("patient-password"), role="patient", is_active=True, approval_status="approved")
                for index in (1, 2, 3)
            ]
            db.add_all(doctor_users + patient_users)
            db.flush()
            doctors = [
                Doctor(name=f"Workflow Doctor {index}", specialization="Cardiology", department="Heart", email=f"workflow.doctor{index}@example.com", user_id=doctor_users[index - 1].id)
                for index in (1, 2)
            ]
            patients = [
                Patient(name=f"Workflow Patient {index}", age=30, email=f"workflow.patient{index}@example.com", user_id=patient_users[index - 1].id)
                for index in (1, 2, 3)
            ]
            db.add_all(doctors + patients)
            db.flush()
            db.add(DoctorAvailability(doctor_id=doctors[0].id, day_of_week=target.strftime("%A"), specific_date=target.date(), start_time=datetime.strptime("09:00", "%H:%M").time(), end_time=datetime.strptime("10:30", "%H:%M").time(), is_available=True))
            requests = [
                Appointment(patient_id=patients[0].id, doctor_id=doctors[0].id, appointment_date=target.replace(hour=9), status="Pending Doctor Approval", reason="Headache"),
                Appointment(patient_id=patients[1].id, doctor_id=doctors[0].id, appointment_date=target.replace(hour=9, minute=30), status="Pending Doctor Approval", reason="Check-up"),
                Appointment(patient_id=patients[2].id, doctor_id=doctors[1].id, appointment_date=target.replace(hour=10), status="Pending Doctor Approval", reason="Consultation"),
            ]
            db.add_all(requests)
            db.commit()
            request_ids = [item.id for item in requests]
            first_doctor_id = doctors[0].id
        finally:
            db.close()

        def auth(email, password, role):
            response = self.client.post("/api/auth/login", json={"email": email, "password": password, "role": role})
            self.assertEqual(response.status_code, 200)
            return {"Authorization": f"Bearer {response.json()['access_token']}"}

        doctor_one = auth("workflow1.workflow@example.com", "doctor-password", "clinician")
        doctor_two = auth("workflow2.workflow@example.com", "doctor-password", "clinician")
        patient_one = auth("workflow.patient1@example.com", "patient-password", "patient")
        patient_two = auth("workflow.patient2@example.com", "patient-password", "patient")
        patient_three = auth("workflow.patient3@example.com", "patient-password", "patient")

        own_dashboard = self.client.get("/api/dashboard/doctor", headers=doctor_one)
        self.assertEqual(own_dashboard.status_code, 200)
        self.assertEqual([item["id"] for item in own_dashboard.json()["pending_requests"]], request_ids[:2])
        self.assertEqual(self.client.post(f"/api/appointments/{request_ids[0]}/accept", headers=doctor_two).status_code, 403)

        accepted = self.client.post(f"/api/appointments/{request_ids[0]}/accept", headers=doctor_one)
        self.assertEqual(accepted.status_code, 200)
        self.assertEqual(accepted.json()["appointment"]["status"], "Scheduled")
        self.assertEqual(self.client.post(f"/api/appointments/{request_ids[0]}/accept", headers=doctor_one).status_code, 409)
        accepted_visible = self.client.get("/api/dashboard/patient", headers=patient_one)
        self.assertEqual(accepted_visible.status_code, 200)
        self.assertEqual(accepted_visible.json()["upcoming"][0]["status"], "Scheduled")

        declined = self.client.post(f"/api/appointments/{request_ids[1]}/decline", headers=doctor_one, json={"reason": "Doctor unavailable"})
        self.assertEqual(declined.status_code, 200)
        self.assertEqual(declined.json()["appointment"]["status"], "Declined")
        patient_dashboard = self.client.get("/api/dashboard/patient", headers=patient_two)
        self.assertEqual(patient_dashboard.status_code, 200)
        self.assertEqual(patient_dashboard.json()["declined"][0]["decline_reason"], "Doctor unavailable")
        alternatives = self.client.post("/api/ai/chat", headers=patient_two, json={"query": "Find an alternative after my declined request"})
        self.assertEqual(alternatives.status_code, 200)
        self.assertIn("09:30 am", alternatives.json()["message"])

        replacement = self.client.post("/api/appointments/", headers=patient_three, params={
            "patient_id": 0,
            "doctor_id": first_doctor_id,
            "appointment_date": target.replace(hour=9, minute=30).isoformat(),
            "reason": "Alternative request",
        })
        self.assertEqual(replacement.status_code, 200)
        self.assertEqual(replacement.json()["appointment"]["status"], "Pending Doctor Approval")
        self.assertEqual(self.client.get("/api/appointments/", headers=patient_one).json()[0]["status"], "Scheduled")

    def test_role_specific_dashboard_endpoints_enforce_authorization(self):
        db = self.session_factory()
        try:
            patient_user = User(
                full_name="Dashboard Patient",
                email="dashboard.patient@example.com",
                password_hash=security.hash_password("secure-password"),
                role="patient",
                is_active=True,
                approval_status="approved",
            )
            staff_user = User(
                full_name="Dashboard Staff",
                email="dashboard.staff@example.com",
                password_hash=security.hash_password("secure-password"),
                role="staff",
                is_active=True,
                approval_status="approved",
            )
            doctor_user = User(
                full_name="Dashboard Doctor",
                email="dashboard.doctor@example.com",
                password_hash=security.hash_password("secure-password"),
                role="clinician",
                is_active=True,
                approval_status="approved",
            )
            unlinked_doctor = User(
                full_name="Unlinked Dashboard Doctor",
                email="unlinked.dashboard.doctor@example.com",
                password_hash=security.hash_password("secure-password"),
                role="clinician",
                is_active=True,
                approval_status="approved",
            )
            db.add_all([patient_user, staff_user, doctor_user, unlinked_doctor])
            db.flush()
            patient = Patient(
                name="Dashboard Patient",
                age=32,
                email="dashboard.patient@example.com",
                user_id=patient_user.id,
            )
            doctor = Doctor(
                name="Dashboard Doctor",
                specialization="Internal Medicine",
                email="dashboard.doctor.profile@example.com",
                user_id=doctor_user.id,
            )
            db.add_all([patient, doctor])
            db.commit()
        finally:
            db.close()

        credentials = {
            "patient": ("dashboard.patient@example.com", "patient"),
            "staff": ("dashboard.staff@example.com", "staff"),
            "doctor": ("dashboard.doctor@example.com", "clinician"),
            "unlinked": ("unlinked.dashboard.doctor@example.com", "clinician"),
        }
        tokens = {}
        for key, (email, role) in credentials.items():
            login = self.client.post(
                "/api/auth/login",
                json={"email": email, "password": "secure-password", "role": role},
            )
            self.assertEqual(login.status_code, 200)
            tokens[key] = {"Authorization": f"Bearer {login.json()['access_token']}"}

        admin_headers = self.headers
        self.assertEqual(self.client.get("/api/dashboard/admin", headers=admin_headers).status_code, 200)
        self.assertEqual(self.client.get("/api/dashboard/doctor", headers=admin_headers).status_code, 403)
        self.assertEqual(self.client.get("/api/dashboard/patient", headers=admin_headers).status_code, 403)
        self.assertEqual(self.client.get("/api/dashboard/finance", headers=admin_headers).status_code, 403)

        doctor_dashboard = self.client.get("/api/dashboard/doctor", headers=tokens["doctor"])
        self.assertEqual(doctor_dashboard.status_code, 200)
        self.assertEqual(doctor_dashboard.json()["role"], "clinician")
        self.assertNotIn("revenue", doctor_dashboard.json()["stats"])

        patient_dashboard = self.client.get("/api/dashboard/patient", headers=tokens["patient"])
        self.assertEqual(patient_dashboard.status_code, 200)
        self.assertEqual(patient_dashboard.json()["role"], "patient")
        self.assertIn("prescriptions", patient_dashboard.json())

        finance_dashboard = self.client.get("/api/dashboard/finance", headers=tokens["staff"])
        self.assertEqual(finance_dashboard.status_code, 200)
        self.assertEqual(finance_dashboard.json()["role"], "staff")
        self.assertNotIn("appointments", finance_dashboard.json())

        self.assertEqual(self.client.get("/api/dashboard/doctor", headers=tokens["patient"]).status_code, 403)
        self.assertEqual(self.client.get("/api/dashboard/patient", headers=tokens["staff"]).status_code, 403)
        self.assertEqual(self.client.get("/api/dashboard/finance", headers=tokens["doctor"]).status_code, 403)
        self.assertEqual(self.client.get("/api/dashboard/doctor", headers=tokens["unlinked"]).status_code, 403)

    def test_patient_account_can_only_access_owned_records(self):
        patient1 = self.client.post(
            "/api/patients/",
            headers=self.headers,
            json={"name": "Owned Patient", "age": 34, "email": "owned@example.com"},
        ).json()
        patient2 = self.client.post(
            "/api/patients/",
            headers=self.headers,
            json={"name": "Other Patient", "age": 40, "email": "other.patient@example.com"},
        ).json()

        created1 = self.client.post(
            "/api/auth/users",
            headers=self.headers,
            json={
                "full_name": "Owned Patient",
                "email": "owned@example.com",
                "password": "patient-password",
                "role": "patient",
                "patient_id": patient1["id"],
            },
        )
        self.assertEqual(created1.status_code, 201)

        login = self.client.post(
            "/api/auth/login",
            json={
                "email": "owned@example.com",
                "password": "patient-password",
                "role": "patient",
            },
        )
        self.assertEqual(login.status_code, 200)
        patient_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

        own_search = self.client.get(
            "/api/patients/",
            headers=patient_headers,
            params={"search": "Owned Patient", "sort": "name", "order": "asc", "limit": 1, "offset": 0},
        )
        self.assertEqual(own_search.status_code, 200)
        self.assertEqual([item["id"] for item in own_search.json()], [patient1["id"]])

        foreign_search = self.client.get(
            "/api/patients/",
            headers=patient_headers,
            params={"search": "Other Patient", "sort": "name", "order": "asc", "limit": 1, "offset": 0},
        )
        self.assertEqual(foreign_search.status_code, 200)
        self.assertEqual(foreign_search.json(), [])

        foreign_email_search = self.client.get(
            "/api/patients/",
            headers=patient_headers,
            params={"search": "other.patient@example.com", "limit": 10, "offset": 0},
        )
        self.assertEqual(foreign_email_search.status_code, 200)
        self.assertEqual(foreign_email_search.json(), [])

        owned = self.client.get(
            f"/api/patients/{patient1['id']}",
            headers=patient_headers,
        )
        self.assertEqual(owned.status_code, 200)

        foreign = self.client.get(
            f"/api/patients/{patient2['id']}",
            headers=patient_headers,
        )
        self.assertEqual(foreign.status_code, 403)

        appointment_foreign = self.client.post(
            "/api/appointments/",
            headers=patient_headers,
            params={
                "patient_id": patient2["id"],
                "doctor_id": 999,
                "appointment_date": (
                    datetime.now() + timedelta(days=1)
                ).replace(hour=10, minute=0, second=0, microsecond=0).isoformat(),
            },
        )
        self.assertEqual(appointment_foreign.status_code, 403)

        bill = self.client.post(
            "/api/bills/",
            headers=self.headers,
            params={
                "patient_id": patient2["id"],
                "bill_number": "OWNERSHIP-BILL",
                "total_amount": 75,
            },
        ).json()["bill"]
        foreign_bill = self.client.get(
            f"/api/bills/{bill['id']}",
            headers=patient_headers,
        )
        self.assertEqual(foreign_bill.status_code, 404)

        class Call:
            name = "get_patient"
            args = {"patient_id": patient2["id"]}

        class Response:
            function_calls = [Call()]
            text = "Patient lookup."

        with patch("app.ai.orchestrator._gemini_response", return_value=Response()):
            ai_foreign = self.client.post(
                "/api/ai/chat",
                headers=patient_headers,
                json={"query": f"Find patient ID {patient2['id']}"},
            )
        self.assertEqual(ai_foreign.status_code, 200)
        self.assertEqual(ai_foreign.json()["status"], "error")
        self.assertIn("own patient", ai_foreign.json()["message"].lower())

    def test_concurrent_approval_execution_is_idempotent(self):
        patient = self.client.post(
            "/api/patients/",
            headers=self.headers,
            json={"name": "Concurrent Patient", "age": 45, "email": "concurrent@example.com"},
        ).json()
        doctor = self.client.post(
            "/api/doctors/",
            headers=self.headers,
            json={
                "name": "Concurrent Doctor",
                "specialization": "Cardiology",
                "email": "concurrent-doctor@example.com",
            },
        ).json()
        weekday = (datetime.now() + timedelta(days=1)).strftime("%A")
        self.client.post(
            "/api/availability/",
            headers=self.headers,
            params={
                "doctor_id": doctor["id"],
                "day_of_week": weekday,
                "start_time": "09:00:00",
                "end_time": "17:00:00",
            },
        )
        appointment = self.client.post(
            "/api/appointments/",
            headers=self.headers,
            params={
                "patient_id": patient["id"],
                "doctor_id": doctor["id"],
                "appointment_date": (
                    datetime.now() + timedelta(days=1)
                ).replace(hour=10, minute=0, second=0, microsecond=0).isoformat(),
            },
        ).json()["appointment"]

        handle, db_path = tempfile.mkstemp(suffix=".db")
        os.close(handle)
        engine = create_engine(
            f"sqlite:///{db_path}",
            connect_args={"check_same_thread": False},
        )
        Base.metadata.create_all(engine)
        direct_factory = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=engine,
        )
        db = direct_factory()
        try:
            admin = User(
                full_name="Concurrent Admin",
                email="concurrent-admin@example.com",
                password_hash=security.hash_password("secure-password"),
                role="admin",
            )
            db.add(admin)
            db.flush()
            linked_patient = Patient(
                name="Concurrent Approval Patient",
                age=45,
                email="concurrent-approval@example.com",
                user_id=admin.id,
            )
            linked_doctor = Doctor(
                name="Concurrent Approval Doctor",
                specialization="Cardiology",
                email="concurrent-approval-doctor@example.com",
            )
            db.add_all([linked_patient, linked_doctor])
            db.flush()
            scheduled = Appointment(
                patient_id=linked_patient.id,
                doctor_id=linked_doctor.id,
                appointment_date=datetime.now() + timedelta(days=1),
                status="Scheduled",
            )
            approval = AIApproval(
                id="concurrent-approval",
                conversation_id="concurrent-conversation",
                user_id=admin.id,
                action="cancel_appointment",
                parameters_json={"appointment_id": 1},
                status="pending",
                expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
            )
            db.add(scheduled)
            db.flush()
            approval.parameters_json = {"appointment_id": scheduled.id}
            db.add(approval)
            db.commit()
            admin_id = admin.id
        finally:
            db.close()

        from app.api.ai import decide_approval

        def approve():
            session = direct_factory()
            try:
                direct_admin = session.query(User).filter(User.id == admin_id).first()
                decide_approval(
                    "concurrent-approval",
                    "approve",
                    session,
                    direct_admin,
                )
                return 200
            except HTTPException as exc:
                return exc.status_code
            finally:
                session.close()

        try:
            with ThreadPoolExecutor(max_workers=2) as executor:
                statuses = list(executor.map(lambda _: approve(), range(2)))
        finally:
            engine.dispose()
            os.unlink(db_path)

        self.assertIn(200, statuses)
        self.assertIn(409, statuses)


if __name__ == "__main__":
    unittest.main()

import unittest
from datetime import datetime, timedelta, timezone
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
                json={"query": f"I want to book an appointment with Dr. Ritik on {target.isoformat()} at 4 PM"},
            )
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.json()["status"], "approval_required")
        self.assertIn("Would you like me to confirm", first.json()["message"])
        self.assertEqual(first.json()["data"]["doctor_id"], doctor_id)

        approval_id = first.json()["approval_id"]
        approved = self.client.post(
            f"/api/ai/approvals/{approval_id}/approve",
            headers=patient_headers,
        )
        self.assertEqual(approved.status_code, 200)
        self.assertEqual(approved.json()["status"], "executed")
        self.assertIn("appointment_id", approved.json()["result"])

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
        self.assertIn("appointment id", support.json()["message"].lower())

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

        with patch(
            "app.ai.orchestrator._gemini_response",
            side_effect=RuntimeError("Gemini unavailable"),
        ):
            availability = self.client.post(
                "/api/ai/chat",
                headers=self.headers,
                json={"query": f"Show availability for doctor {doctor['id']}"},
            )
            date_text = (datetime.now() + timedelta(days=2)).strftime("%Y-%m-%d")
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
        self.assertEqual(foreign_bill.status_code, 403)

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

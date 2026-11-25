import unittest
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event, Lock, get_ident
from types import SimpleNamespace
from unittest.mock import Mock, patch

from app.agents import main_agent
from app.ai.orchestrator import REGISTRY, _extract_date, _extract_time, _function_calls, _gemini_declarations, _support_guidance, _support_intent_category
from app.ai.tool_registry import ToolRegistry


class FakeModelResponse:
    text = "UNSUPPORTED"


class FakeModels:
    def generate_content(self, **_kwargs):
        return FakeModelResponse()


class FakeClient:
    models = FakeModels()


class AiRouterTests(unittest.TestCase):
    def test_booking_entity_parsing_supports_weekdays_and_natural_time(self):
        self.assertIsNotNone(_extract_date("I want to book on Monday"))
        self.assertEqual(_extract_time("Monday at 4 PM"), "16:00")
        self.assertEqual(_extract_time("at 09:30"), "09:30")

    def test_booking_entity_parsing_accepts_written_and_day_first_dates(self):
        self.assertEqual(_extract_date("25/11/2026"), "2026-11-25")
        self.assertEqual(_extract_date("November 25, 2026"), "2026-11-25")
        self.assertEqual(_extract_date("25 November 2026"), "2026-11-25")
        self.assertEqual(_extract_time("12 PM"), "12:00")
        self.assertEqual(_extract_time("12 AM"), "00:00")
        self.assertEqual(_extract_time("4:30 PM"), "16:30")
        self.assertEqual(_extract_time("4:30 AM"), "04:30")

    def test_ambiguous_slash_date_is_not_guessed(self):
        from app.ai.orchestrator import _has_ambiguous_numeric_date

        self.assertTrue(_has_ambiguous_numeric_date("03/04/2026"))
        self.assertIsNone(_extract_date("03/04/2026"))
        self.assertFalse(_has_ambiguous_numeric_date("25/11/2026"))
    def test_unsupported_model_selection_is_explicitly_rejected(self):
        with patch.object(main_agent, "client", FakeClient()):
            with self.assertRaisesRegex(RuntimeError, "unsupported agent"):
                main_agent.main_agent("What should I ask?")

    def test_gemini_function_declarations_are_registered(self):
        declarations = _gemini_declarations()
        names = {item.name for item in declarations}
        self.assertIn("search_doctors", names)
        self.assertIn("create_appointment", names)
        self.assertIn("financial_summary", names)
        self.assertIn("monthly_financial_comparison", names)

    def test_patient_gemini_tools_do_not_request_internal_booking_ids(self):
        names = {item.name for item in _gemini_declarations("patient")}
        self.assertNotIn("get_patient", names)
        self.assertNotIn("doctor_availability", names)
        self.assertNotIn("find_available_slots", names)
        self.assertNotIn("create_appointment", names)
        self.assertNotIn("financial_summary", names)
        self.assertIn("pending_bills", names)

    def test_support_intent_categories_cover_requested_workflows(self):
        cases = {
            "How do I book an appointment?": "appointment_booking",
            "What is my appointment status?": "appointment_status",
            "How can I cancel an appointment?": "appointment_cancellation",
            "Is Dr Singh available?": "doctor_availability",
            "I cannot log in to my account": "login_registration",
            "Where is my dashboard?": "dashboard_navigation",
            "The technical error is not working": "technical_support",
            "Please connect me to a human": "human_escalation",
        }
        for query, expected in cases.items():
            with self.subTest(query=query):
                self.assertEqual(_support_intent_category(query), expected)
        self.assertIsNone(_support_intent_category("What is the weather on Neptune?"))

    def test_support_guidance_uses_authenticated_role_without_database_reads(self):
        db = Mock()
        patient = SimpleNamespace(role="patient")
        clinician = SimpleNamespace(role="clinician")

        patient_result = _support_guidance(db, patient, category="dashboard_navigation", issue="Where is my dashboard?")
        clinician_result = _support_guidance(db, clinician, category="dashboard_navigation", issue="Where is my dashboard?")

        self.assertIn("Patient Overview", patient_result["message"])
        self.assertIn("clinician Overview", clinician_result["message"])
        db.query.assert_not_called()
        db.execute.assert_not_called()

    def test_support_tool_never_queries_records_or_bypasses_role_validation(self):
        db = Mock()
        patient = SimpleNamespace(role="patient")
        result, trace = REGISTRY.execute(
            "support_guidance",
            patient,
            db,
            {"category": "technical_support", "issue": "The app is not working"},
        )
        self.assertEqual(result["status"], "success")
        self.assertEqual(trace["status"], "success")
        db.query.assert_not_called()
        db.execute.assert_not_called()

        unauthorized = SimpleNamespace(role="guest")
        denied, denied_trace = REGISTRY.execute(
            "support_guidance",
            unauthorized,
            db,
            {"category": "general_system", "issue": "Help"},
        )
        self.assertEqual(denied["status"], "error")
        self.assertEqual(denied_trace["status"], "error")
        db.query.assert_not_called()

    def test_gemini_function_calls_are_parsed_as_valid_arguments(self):
        class Call:
            name = "search_doctors"
            args = {"specialization": "Cardiology", "limit": 5}

        class Response:
            function_calls = [Call()]

        calls = _function_calls(Response())
        self.assertEqual(
            calls,
            [("search_doctors", {"specialization": "Cardiology", "limit": 5})],
        )

    def test_malformed_tool_arguments_are_rejected_before_execution(self):
        registry = ToolRegistry()
        executed = {"value": False}

        def tool(db, user, doctor_id):
            executed["value"] = True
            return {"status": "success"}

        registry.register(
            "typed_tool",
            "Test typed tool",
            ("admin",),
            tool,
            {
                "type": "object",
                "properties": {"doctor_id": {"type": "integer"}},
                "required": ["doctor_id"],
            },
        )
        result, trace = registry.execute(
            "typed_tool",
            type("User", (), {"role": "admin"})(),
            object(),
            {"doctor_id": "not-an-integer"},
        )
        self.assertEqual(result["status"], "error")
        self.assertIn("Invalid type", result["message"])
        self.assertFalse(executed["value"])
        self.assertEqual(trace["status"], "error")

    def test_read_tool_failure_is_retried_and_returns_error(self):
        sessions = [Mock(), Mock()]
        registry = ToolRegistry(session_factory=Mock(side_effect=sessions))

        def failing_tool(db, user):
            raise RuntimeError("database unavailable")

        registry.register(
            "failing_tool",
            "Test tool",
            ("admin",),
            failing_tool,
        )
        result, trace = registry.execute(
            "failing_tool",
            type("User", (), {"role": "admin"})(),
            object(),
            {},
        )
        self.assertEqual(result["status"], "error")
        self.assertEqual(trace["status"], "error")
        self.assertEqual(registry._session_factory.call_count, 2)
        for session in sessions:
            session.rollback.assert_called_once()
            session.close.assert_called_once()
            session.commit.assert_not_called()

    def test_read_retry_starts_only_after_previous_session_is_closed(self):
        active_sessions = 0
        max_active_sessions = 0
        sessions = []
        calls = 0

        def session_factory():
            nonlocal active_sessions, max_active_sessions
            active_sessions += 1
            max_active_sessions = max(max_active_sessions, active_sessions)
            session = Mock()

            def close():
                nonlocal active_sessions
                active_sessions -= 1

            session.close.side_effect = close
            sessions.append(session)
            return session

        def flaky_read(db, user):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise RuntimeError("temporary read failure")
            return {"status": "success"}

        registry = ToolRegistry(session_factory=session_factory)
        registry.register("flaky_read", "Flaky read", ("admin",), flaky_read)
        result, _ = registry.execute("flaky_read", SimpleNamespace(id=1, role="admin"), object(), {})

        self.assertEqual(result["status"], "success")
        self.assertEqual(calls, 2)
        self.assertEqual(max_active_sessions, 1)
        self.assertEqual(active_sessions, 0)
        for session in sessions:
            session.close.assert_called_once()

    def test_tool_uses_distinct_worker_sessions_and_detached_user_context(self):
        sessions = []
        observed = []
        lock = Lock()
        barrier = Barrier(2)

        def session_factory():
            session = Mock()
            with lock:
                sessions.append(session)
            return session

        def handler(db, user):
            barrier.wait(timeout=2)
            observed.append((db, get_ident(), user.id, user.role))
            return {"status": "success"}

        registry = ToolRegistry(session_factory=session_factory, timeout_seconds=3)
        registry.register("session_test", "Session test", ("admin",), handler)
        user = SimpleNamespace(id=42, role="admin")
        request_sessions = [object(), object()]

        with ThreadPoolExecutor(max_workers=2) as callers:
            results = list(callers.map(
                lambda request_db: registry.execute("session_test", user, request_db, {}),
                request_sessions,
            ))

        self.assertTrue(all(result[0]["status"] == "success" for result in results))
        self.assertEqual(len(sessions), 2)
        self.assertIsNot(sessions[0], sessions[1])
        self.assertTrue(all(
            session is not request_db
            for session in sessions
            for request_db in request_sessions
        ))
        self.assertEqual({id(item[0]) for item in observed}, {id(session) for session in sessions})
        self.assertEqual(len({item[1] for item in observed}), 2)
        self.assertEqual({(item[2], item[3]) for item in observed}, {(42, "admin")})
        for session in sessions:
            session.commit.assert_called_once()
            session.close.assert_called_once()

    def test_success_commits_and_closes_worker_session(self):
        session = Mock()
        registry = ToolRegistry(session_factory=lambda: session)
        registry.register("successful", "Success", ("admin",), lambda db, user: {"value": 1})

        result, _ = registry.execute("successful", SimpleNamespace(id=1, role="admin"), object(), {})

        self.assertEqual(result, {"status": "success", "value": 1})
        session.commit.assert_called_once()
        session.rollback.assert_not_called()
        session.close.assert_called_once()

    def test_timed_out_read_is_not_retried_while_original_may_run(self):
        session = Mock()
        started = Event()
        release = Event()
        closed = Event()
        session.close.side_effect = closed.set
        calls = []

        def slow_read(db, user):
            calls.append(get_ident())
            started.set()
            release.wait(timeout=2)
            return {"status": "success"}

        registry = ToolRegistry(session_factory=lambda: session, timeout_seconds=0.05)
        registry.register("slow_read", "Slow read", ("admin",), slow_read)
        result, _ = registry.execute("slow_read", SimpleNamespace(id=1, role="admin"), object(), {})

        self.assertTrue(started.is_set())
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["message"], "The tool timed out.")
        self.assertEqual(len(calls), 1)
        release.set()
        self.assertTrue(closed.wait(timeout=1))
        self.assertEqual(len(calls), 1)
        session.commit.assert_called_once()
        session.close.assert_called_once()

    def test_timed_out_write_reports_unknown_outcome_without_retry(self):
        session = Mock()
        started = Event()
        release = Event()
        closed = Event()
        session.close.side_effect = closed.set
        calls = []

        def slow_write(db, user):
            calls.append(get_ident())
            started.set()
            release.wait(timeout=2)
            return {"status": "success"}

        registry = ToolRegistry(session_factory=lambda: session, timeout_seconds=0.05)
        registry.register("slow_write", "Slow write", ("admin",), slow_write, kind="approval_write")
        result, _ = registry.execute("slow_write", SimpleNamespace(id=1, role="admin"), object(), {})

        self.assertTrue(started.is_set())
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["outcome"], "unknown")
        self.assertIn("outcome is unknown", result["message"])
        self.assertIn("before retrying", result["message"])
        self.assertEqual(len(calls), 1)
        release.set()
        self.assertTrue(closed.wait(timeout=1))
        self.assertEqual(len(calls), 1)
        session.commit.assert_called_once()
        session.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()

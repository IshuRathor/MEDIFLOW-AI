import unittest
from unittest.mock import patch

from app.agents import main_agent
from app.ai.orchestrator import _extract_date, _extract_time, _function_calls, _gemini_declarations
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
        registry = ToolRegistry()

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


if __name__ == "__main__":
    unittest.main()

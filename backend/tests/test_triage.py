import unittest

from app.services.triage_service import triage_patient


class TriageServiceTests(unittest.TestCase):
    def test_emergency_phrases_take_priority_over_fever(self):
        for phrase in (
            "pain in chest", "pain in my chest", "CHEST-PRESSURE", "chest pain",
            "severe breathing difficulty", "fainted", "loss of consciousness",
            "sudden facial drooping", "arm weakness", "speech difficulty",
            "severe uncontrolled bleeding", "bleeding won’t stop", "seizure",
        ):
            with self.subTest(phrase=phrase):
                result = triage_patient(f"High fever and {phrase}")
                self.assertEqual(result.urgency, "Emergency")
                self.assertIn("Call local emergency services now", result.recommended_action)
                self.assertIn("Do not wait", result.recommended_action)

    def test_emergency_symptoms_are_escalated(self):
        result = triage_patient("The patient has severe chest pain and difficulty breathing")

        self.assertEqual(result.urgency, "Emergency")
        self.assertIn("Emergency", result.recommended_department)
        self.assertIn("emergency services", result.recommended_action)
        self.assertIn("not a medical diagnosis", result.disclaimer)
        self.assertIn("life-threatening", result.safety_notice)

    def test_department_is_selected_for_specialized_symptoms(self):
        result = triage_patient("The patient has a skin rash and itching")

        self.assertEqual(result.urgency, "Low")
        self.assertEqual(result.recommended_department, "Dermatology")

    def test_unknown_symptoms_return_safe_default(self):
        result = triage_patient("Unusual discomfort")

        self.assertEqual(result.urgency, "Low")
        self.assertEqual(result.recommended_department, "General Medicine")


if __name__ == "__main__":
    unittest.main()

import unittest


try:
    from fastapi.testclient import TestClient

    import backend.main as backend_main

    API_DEPENDENCIES_AVAILABLE = True
except ModuleNotFoundError:
    API_DEPENDENCIES_AVAILABLE = False


class FakeOrchestrator:
    async def start(self):
        return None

    async def close(self):
        return None

    async def evaluate_essay(self, question: str, answer: str):
        return {
            "detailed_feedback": {"summary": "Mock feedback"},
            "overall_criteria_scores": {
                "overall_score": 6.0,
                "criteria_scores": {},
            },
        }


@unittest.skipUnless(
    API_DEPENDENCIES_AVAILABLE,
    "FastAPI dependencies are not installed",
)
class ApiContractTests(unittest.TestCase):
    def setUp(self):
        self.original_orchestrator = backend_main.orchestrator
        backend_main.orchestrator = FakeOrchestrator()
        self.client_context = TestClient(backend_main.app)
        self.client = self.client_context.__enter__()

    def tearDown(self):
        self.client_context.__exit__(None, None, None)
        backend_main.orchestrator = self.original_orchestrator

    def test_health(self):
        response = self.client.get("/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_evaluate_essay_contract(self):
        response = self.client.post(
            "/evaluate_essay",
            json={
                "question": "Do you agree?",
                "answer": "I agree because education matters.",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["overall_criteria_scores"]["overall_score"],
            6.0,
        )

    def test_rejects_blank_essay(self):
        response = self.client.post(
            "/evaluate_essay",
            json={"question": "Do you agree?", "answer": "   "},
        )

        self.assertEqual(response.status_code, 422)


if __name__ == "__main__":
    unittest.main()

import asyncio
import os
import unittest
from unittest.mock import patch


try:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from langgraph.checkpoint.memory import InMemorySaver
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
        InMemorySpanExporter,
    )
    from opentelemetry.trace import StatusCode

    from backend.agents.ielts_graph import IELTSGraphDependencies
    from backend.agents.orchestrator import IELTSWritingOrchestrator
    from backend.observability.telemetry import (
        TelemetrySettings,
        initialize_telemetry,
        instrument_fastapi,
        shutdown_telemetry,
        workflow_span,
    )

    TELEMETRY_DEPENDENCIES_AVAILABLE = True
except ModuleNotFoundError:
    TELEMETRY_DEPENDENCIES_AVAILABLE = False


SENSITIVE_ESSAY = "PRIVATE_ESSAY_SENTINEL_71429"
SENSITIVE_KEY = "PRIVATE_API_KEY_SENTINEL_92714"


def sample_feedback(score: float) -> dict:
    criterion_names = (
        "Task Achievement",
        "Coherence and Cohesion",
        "Lexical Resource",
        "Grammatical Range and Accuracy",
    )
    criterion_keys = (
        "task_response",
        "coherence_and_cohesion",
        "lexical_resource",
        "grammatical_range_and_accuracy",
    )
    return {
        "overall_score": score,
        "evaluation_feedback": {
            name: {
                "suggested_band_score": score,
                "feedback": "Mock evaluation.",
            }
            for name in criterion_names
        },
        "constructive_feedback": {
            "criteria": {
                key: {
                    "score": score,
                    "strengths": ["Mock strength"],
                    "areas_for_improvement": ["Mock area"],
                    "recommendations": ["Mock recommendation"],
                }
                for key in criterion_keys
            },
            "overall_feedback": {"summary": "Mock summary."},
        },
    }


def span_text(spans) -> str:
    values = []
    for span in spans:
        values.extend(
            [
                span.name,
                repr(span.attributes),
                repr(span.status.description),
            ]
        )
        for event in span.events:
            values.extend([event.name, repr(event.attributes)])
    return "\n".join(values)


@unittest.skipUnless(
    TELEMETRY_DEPENDENCIES_AVAILABLE,
    "OpenTelemetry dependencies are not installed",
)
class TelemetryTests(unittest.TestCase):
    def setUp(self):
        self.exporter = InMemorySpanExporter()
        self.settings = TelemetrySettings(
            disabled=False,
            exporter="console",
            service_name="ielts-test",
            otlp_endpoint=None,
        )
        self.runtime = initialize_telemetry(self.settings, self.exporter)

    def tearDown(self):
        shutdown_telemetry()

    @staticmethod
    def dependencies(
        failing_score_message: str | None = None,
    ) -> IELTSGraphDependencies:
        async def score_tool(question: str, answer: str) -> float:
            if failing_score_message is not None:
                raise RuntimeError(failing_score_message)
            return 6.0

        async def grammar_tool(answer: str) -> dict:
            return {
                "corrected_text": "Corrected essay.",
                "with_errors": "<span>Correction</span>",
                "fixed_only": "<p>Corrected essay.</p>",
            }

        async def feedback_tool(
            question: str,
            answer: str,
            score: float,
        ) -> dict:
            return sample_feedback(score)

        return IELTSGraphDependencies(
            score_essay=score_tool,
            check_grammar=grammar_tool,
            generate_feedback=feedback_tool,
        )

    def test_combined_workflow_creates_root_and_node_spans(self):
        orchestrator = IELTSWritingOrchestrator(
            checkpointer=InMemorySaver(),
            dependencies=self.dependencies(),
        )

        result = asyncio.run(
            orchestrator.process_essay(
                "Do you agree?",
                SENSITIVE_ESSAY,
                session_id="private-session-id",
            )
        )

        self.assertEqual(result["session_id"], "private-session-id")
        spans = self.exporter.get_finished_spans()
        spans_by_name = {span.name: span for span in spans}
        workflow = spans_by_name["ielts.workflow.combined"]
        expected_nodes = {
            "ielts.node.validate_input",
            "ielts.node.prepare_session",
            "ielts.node.score_essay",
            "ielts.node.correct_grammar",
            "ielts.node.generate_feedback",
            "ielts.node.process_scores",
            "ielts.node.build_report",
        }

        self.assertTrue(expected_nodes.issubset(spans_by_name))
        self.assertEqual(workflow.attributes["ielts.session.source"], "provided")
        self.assertNotIn("private-session-id", span_text(spans))
        self.assertNotIn(SENSITIVE_ESSAY, span_text(spans))

        for node_name in expected_nodes:
            node = spans_by_name[node_name]
            self.assertIsNotNone(node.parent)
            self.assertEqual(node.parent.span_id, workflow.context.span_id)

    def test_workflow_records_sanitized_exception_and_error_status(self):
        provider_message = f"provider failed for {SENSITIVE_ESSAY} {SENSITIVE_KEY}"
        orchestrator = IELTSWritingOrchestrator(
            checkpointer=InMemorySaver(),
            dependencies=self.dependencies(provider_message),
        )

        with self.assertRaisesRegex(RuntimeError, SENSITIVE_ESSAY):
            asyncio.run(
                orchestrator.evaluate_essay(
                    "Do you agree?",
                    SENSITIVE_ESSAY,
                    session_id="error-test",
                )
            )

        spans = self.exporter.get_finished_spans()
        spans_by_name = {span.name: span for span in spans}
        workflow = spans_by_name["ielts.workflow.evaluate"]
        score_node = spans_by_name["ielts.node.score_essay"]

        self.assertEqual(workflow.status.status_code, StatusCode.ERROR)
        self.assertEqual(score_node.status.status_code, StatusCode.ERROR)
        self.assertTrue(workflow.events)
        self.assertTrue(score_node.events)
        self.assertNotIn(SENSITIVE_ESSAY, span_text(spans))
        self.assertNotIn(SENSITIVE_KEY, span_text(spans))

    def test_fastapi_redacts_query_and_unhandled_exception_message(self):
        app = FastAPI()

        @app.get("/grammar_correction")
        async def grammar_correction(answer: str):
            return {"length": len(answer)}

        @app.get("/failure")
        async def failure():
            message = f"provider failed for {SENSITIVE_ESSAY} {SENSITIVE_KEY}"
            raise RuntimeError(message)

        instrument_fastapi(app, self.runtime)
        try:
            with TestClient(app, raise_server_exceptions=False) as client:
                response = client.get(
                    "/grammar_correction",
                    params={"answer": SENSITIVE_ESSAY},
                )
                failure_response = client.get("/failure")
        finally:
            FastAPIInstrumentor.uninstrument_app(app)

        self.assertEqual(response.json(), {"length": len(SENSITIVE_ESSAY)})
        self.assertEqual(failure_response.status_code, 500)
        spans = self.exporter.get_finished_spans()
        self.assertNotIn(SENSITIVE_ESSAY, span_text(spans))
        self.assertNotIn(SENSITIVE_KEY, span_text(spans))

        grammar_span = next(
            span for span in spans if span.name == "GET /grammar_correction"
        )
        self.assertEqual(grammar_span.attributes["url.query"], "[REDACTED]")
        self.assertEqual(
            grammar_span.attributes["client.address"],
            "[REDACTED]",
        )
        self.assertEqual(
            grammar_span.attributes["user_agent.original"],
            "[REDACTED]",
        )
        self.assertNotIn("answer=", repr(grammar_span.attributes))

    def test_environment_can_disable_telemetry(self):
        shutdown_telemetry()
        disabled_exporter = InMemorySpanExporter()
        with patch.dict(os.environ, {"OTEL_SDK_DISABLED": "true"}):
            runtime = initialize_telemetry(
                TelemetrySettings.from_environment(),
                disabled_exporter,
            )
            with workflow_span("evaluate", "generated", "sqlite"):
                pass

        self.assertFalse(runtime.enabled)
        self.assertEqual(disabled_exporter.get_finished_spans(), ())

    def test_invalid_disabled_flag_keeps_project_default(self):
        with patch.dict(os.environ, {"OTEL_SDK_DISABLED": "invalid"}):
            settings = TelemetrySettings.from_environment()

        self.assertTrue(settings.disabled)

    def test_otlp_runtime_can_be_created_without_sending_data(self):
        shutdown_telemetry()
        runtime = initialize_telemetry(
            TelemetrySettings(
                disabled=False,
                exporter="otlp",
                service_name="ielts-test",
                otlp_endpoint="http://127.0.0.1:4318/v1/traces",
            )
        )

        self.assertTrue(runtime.enabled)
        self.assertIsNotNone(runtime.provider)


if __name__ == "__main__":
    unittest.main()

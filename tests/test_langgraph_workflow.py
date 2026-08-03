import asyncio
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path


try:
    from langgraph.checkpoint.memory import InMemorySaver

    from backend.agents.ielts_graph import IELTSGraphDependencies
    from backend.agents.orchestrator import IELTSWritingOrchestrator

    LANGGRAPH_AVAILABLE = True
except ModuleNotFoundError:
    LANGGRAPH_AVAILABLE = False


def sample_feedback(overall_score: float) -> dict:
    return {
        "overall_score": overall_score,
        "evaluation_feedback": {
            "Task Achievement": {
                "suggested_band_score": 6.0,
                "feedback": "The position addresses the task.",
            },
            "Coherence and Cohesion": {
                "suggested_band_score": 6.0,
                "feedback": "The essay is logically organized.",
            },
            "Lexical Resource": {
                "suggested_band_score": 6.0,
                "feedback": "Vocabulary is generally appropriate.",
            },
            "Grammatical Range and Accuracy": {
                "suggested_band_score": 6.0,
                "feedback": "A mix of sentence forms is used.",
            },
        },
        "constructive_feedback": {
            "criteria": {
                "task_response": {
                    "score": 6.0,
                    "strengths": ["Clear position"],
                    "areas_for_improvement": ["Develop examples"],
                    "recommendations": ["Add specific evidence"],
                },
                "coherence_and_cohesion": {
                    "score": 6.0,
                    "strengths": ["Logical paragraphs"],
                    "areas_for_improvement": ["Improve transitions"],
                    "recommendations": ["Use referencing more clearly"],
                },
                "lexical_resource": {
                    "score": 6.0,
                    "strengths": ["Appropriate vocabulary"],
                    "areas_for_improvement": ["Some repetition"],
                    "recommendations": ["Use precise alternatives"],
                },
                "grammatical_range_and_accuracy": {
                    "score": 6.0,
                    "strengths": ["Some complex sentences"],
                    "areas_for_improvement": ["Agreement errors"],
                    "recommendations": ["Proofread verb forms"],
                },
            },
            "overall_feedback": {"summary": "A clear band 6 response."},
        },
    }


@unittest.skipUnless(LANGGRAPH_AVAILABLE, "LangGraph dependencies are not installed")
class LangGraphWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.calls = []

        async def score_tool(question: str, answer: str) -> float:
            self.calls.append("score")
            await asyncio.sleep(0)
            return 6.0

        async def grammar_tool(answer: str) -> dict:
            self.calls.append("grammar")
            await asyncio.sleep(0)
            return {
                "corrected_text": "Corrected essay.",
                "with_errors": "<span>Correction</span>",
                "fixed_only": "<p>Corrected essay.</p>",
            }

        async def feedback_tool(question: str, answer: str, score: float) -> dict:
            self.calls.append("feedback")
            return sample_feedback(score)

        self.dependencies = IELTSGraphDependencies(
            score_essay=score_tool,
            check_grammar=grammar_tool,
            generate_feedback=feedback_tool,
        )
        self.checkpointer = InMemorySaver()
        self.orchestrator = IELTSWritingOrchestrator(
            checkpointer=self.checkpointer,
            dependencies=self.dependencies,
        )

    def test_evaluation_graph_with_mock_tools(self):
        result = asyncio.run(
            self.orchestrator.evaluate_essay(
                "Do you agree?",
                "I agree because education matters.",
                session_id="evaluation-test",
            )
        )

        self.assertEqual(result["overall_criteria_scores"]["overall_score"], 6.0)
        self.assertIn("detailed_feedback", result)
        self.assertEqual(self.calls, ["score", "feedback"])

    def test_grammar_graph_with_mock_tool(self):
        result = asyncio.run(
            self.orchestrator.correct_grammar(
                "He go to school.",
                session_id="grammar-test",
            )
        )

        self.assertEqual(result["corrected_text"], "Corrected essay.")
        self.assertEqual(self.calls, ["grammar"])

    def test_combined_graph_and_checkpoint(self):
        result = asyncio.run(
            self.orchestrator.process_essay(
                "Do you agree?",
                "I agree because education matters.",
                session_id="combined-test",
            )
        )

        self.assertEqual(result["session_id"], "combined-test")
        self.assertEqual(result["corrected_text"], "Corrected essay.")
        self.assertCountEqual(self.calls[:2], ["score", "grammar"])
        self.assertEqual(self.calls[2], "feedback")

        checkpoints = list(
            self.checkpointer.list(
                {"configurable": {"thread_id": "combined-test"}}
            )
        )
        self.assertGreater(len(checkpoints), 0)

    def test_sqlite_checkpoint_persists_after_orchestrator_closes(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            checkpoint_path = Path(temporary_directory) / "checkpoints.sqlite"

            async def run_workflow():
                orchestrator = IELTSWritingOrchestrator(
                    checkpoint_path=checkpoint_path,
                    dependencies=self.dependencies,
                )
                try:
                    return await orchestrator.process_essay(
                        "Do you agree?",
                        "I agree because education matters.",
                        session_id="sqlite-checkpoint-test",
                    )
                finally:
                    await orchestrator.close()

            result = asyncio.run(run_workflow())

            self.assertEqual(result["session_id"], "sqlite-checkpoint-test")
            self.assertTrue(checkpoint_path.exists())

            with closing(sqlite3.connect(checkpoint_path)) as connection:
                checkpoint_count = connection.execute(
                    "SELECT COUNT(*) FROM checkpoints "
                    "WHERE thread_id = ?",
                    ("sqlite-checkpoint-test",),
                ).fetchone()[0]

            self.assertGreater(checkpoint_count, 0)


if __name__ == "__main__":
    unittest.main()

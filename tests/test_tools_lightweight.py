import unittest

from backend.tools.json_parser import read_json_from_string
from backend.tools.report_generator import (
    build_combined_report,
    build_evaluation_report,
    build_grammar_report,
)
from backend.tools.score_processor import extract_scores, postprocess_feedback, round_ielts


def sample_feedback():
    return {
        "overall_score": 6.0,
        "evaluation_feedback": {
            "Task Achievement": {
                "suggested_band_score": 6.0,
                "feedback": "Addresses the task.",
            },
            "Coherence and Cohesion": {
                "suggested_band_score": 6.0,
                "feedback": "Generally organized.",
            },
            "Lexical Resource": {
                "suggested_band_score": 5.5,
                "feedback": "Vocabulary is adequate.",
            },
            "Grammatical Range and Accuracy": {
                "suggested_band_score": 5.5,
                "feedback": "Some grammar errors remain.",
            },
            "Overall Band Score": {
                "suggested_overall_band_score": 6.0,
            },
        },
        "constructive_feedback": {
            "criteria": {
                "task_response": {"score": 6.0},
                "coherence_and_cohesion": {"score": 6.0},
                "lexical_resource": {"score": 6.0},
                "grammatical_range_and_accuracy": {"score": 6.0},
            },
            "overall_feedback": {"summary": "A clear but improvable essay."},
        },
    }


class JsonParserTests(unittest.TestCase):
    def test_reads_plain_json(self):
        result = read_json_from_string('{"score": 6.5}')

        self.assertTrue(result["valid_json"])
        self.assertEqual(result["parsed"]["score"], 6.5)

    def test_reads_fenced_json_and_normalizes_quotes(self):
        result = read_json_from_string('```json\n{“score”: 6.5}\n```')

        self.assertTrue(result["valid_json"])
        self.assertEqual(result["parsed"]["score"], 6.5)

    def test_reports_invalid_json(self):
        result = read_json_from_string('{"score": }')

        self.assertFalse(result["valid_json"])
        self.assertIn("error", result)


class ScoreProcessorTests(unittest.TestCase):
    def test_rounds_to_ielts_half_band(self):
        self.assertEqual(round_ielts(6.24), 6.0)
        self.assertEqual(round_ielts(6.25), 6.5)
        self.assertEqual(round_ielts(6.74), 6.5)
        self.assertEqual(round_ielts(6.75), 7.0)

    def test_extracts_scores_from_feedback(self):
        scores = extract_scores(sample_feedback())

        self.assertEqual(scores["overall_score"], 6.0)
        self.assertEqual(scores["criteria_scores"]["task_response"], 6.0)
        self.assertEqual(scores["criteria_scores"]["lexical_resource"], 6.0)

    def test_extract_scores_rejects_missing_criterion(self):
        feedback = sample_feedback()
        del feedback["evaluation_feedback"]["Lexical Resource"]
        del feedback["constructive_feedback"]["criteria"]["lexical_resource"]

        with self.assertRaisesRegex(ValueError, "lexical_resource"):
            extract_scores(feedback)

    def test_postprocess_removes_internal_score_fields(self):
        original = sample_feedback()
        cleaned = postprocess_feedback(original)

        self.assertNotIn("overall_score", cleaned)
        self.assertNotIn(
            "suggested_band_score",
            cleaned["evaluation_feedback"]["Task Achievement"],
        )
        self.assertNotIn(
            "score",
            cleaned["constructive_feedback"]["criteria"]["task_response"],
        )
        self.assertIn("overall_score", original)
        self.assertIn(
            "score",
            original["constructive_feedback"]["criteria"]["task_response"],
        )


class ReportGeneratorTests(unittest.TestCase):
    def test_builds_evaluation_report(self):
        report = build_evaluation_report({"feedback": "ok"}, {"overall_score": 6.0})

        self.assertEqual(report["detailed_feedback"]["feedback"], "ok")
        self.assertEqual(report["overall_criteria_scores"]["overall_score"], 6.0)

    def test_builds_grammar_report(self):
        report = build_grammar_report(
            {
                "corrected_text": "Corrected.",
                "with_errors": "<span>Error</span>",
                "fixed_only": "<p>Corrected.</p>",
            }
        )

        self.assertEqual(report["corrected_text"], "Corrected.")
        self.assertIn("span", report["with_errors"])

    def test_builds_combined_report(self):
        report = build_combined_report(
            "session-1",
            {"feedback": "ok"},
            {"overall_score": 6.0},
            {
                "corrected_text": "Corrected.",
                "with_errors": "<span>Error</span>",
                "fixed_only": "<p>Corrected.</p>",
            },
        )

        self.assertEqual(report["session_id"], "session-1")
        self.assertEqual(report["overall_criteria_scores"]["overall_score"], 6.0)
        self.assertEqual(report["corrected_text"], "Corrected.")


if __name__ == "__main__":
    unittest.main()

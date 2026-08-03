def build_evaluation_report(
    feedback: dict,
    scores: dict,
    session_id: str | None = None,
) -> dict:
    report = {
        "detailed_feedback": feedback,
        "overall_criteria_scores": scores,
    }
    if session_id:
        report["session_id"] = session_id
    return report


def build_grammar_report(
    grammar_result: dict,
    session_id: str | None = None,
) -> dict:
    report = {
        "corrected_text": grammar_result["corrected_text"],
        "with_errors": grammar_result["with_errors"],
        "fixed_only": grammar_result["fixed_only"],
    }
    if session_id:
        report["session_id"] = session_id
    return report


def build_combined_report(session_id: str, feedback: dict, scores: dict, grammar_result: dict) -> dict:
    return {
        "session_id": session_id,
        "detailed_feedback": feedback,
        "overall_criteria_scores": scores,
        "corrected_text": grammar_result["corrected_text"],
        "with_errors": grammar_result["with_errors"],
        "fixed_only": grammar_result["fixed_only"],
    }

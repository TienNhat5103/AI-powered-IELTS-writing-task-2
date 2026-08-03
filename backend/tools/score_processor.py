import copy


CRITERION_KEY_MAP = {
    "task_response": "Task Achievement",
    "coherence_and_cohesion": "Coherence and Cohesion",
    "lexical_resource": "Lexical Resource",
    "grammatical_range_and_accuracy": "Grammatical Range and Accuracy",
}


def round_ielts(score: float) -> float:
    integer_part = int(score)
    fractional_part = score - integer_part

    if fractional_part < 0.25:
        return float(integer_part)
    if 0.25 <= fractional_part < 0.75:
        return integer_part + 0.5
    return float(integer_part + 1)


def extract_scores(evaluation_json: dict) -> dict:
    criteria_scores = {}
    evaluation_feedback = evaluation_json.get("evaluation_feedback", {})
    constructive_criteria = evaluation_json.get("constructive_feedback", {}).get("criteria", {})

    for output_key, evaluation_key in CRITERION_KEY_MAP.items():
        evaluation_score = evaluation_feedback.get(evaluation_key, {}).get(
            "suggested_band_score"
        )
        constructive_score = constructive_criteria.get(output_key, {}).get("score")
        available_scores = [
            float(score)
            for score in (evaluation_score, constructive_score)
            if score is not None
        ]

        if not available_scores:
            raise ValueError(f"Missing score for IELTS criterion: {output_key}")

        criteria_scores[output_key] = round_ielts(
            sum(available_scores) / len(available_scores)
        )

    overall_score = round_ielts(sum(criteria_scores.values()) / len(criteria_scores))
    return {
        "overall_score": overall_score,
        "criteria_scores": criteria_scores,
    }


def postprocess_feedback(evaluation_json: dict) -> dict:
    data = copy.deepcopy(evaluation_json)
    data.pop("overall_score", None)

    evaluation_feedback = data.get("evaluation_feedback", {})
    for details in evaluation_feedback.values():
        details.pop("suggested_band_score", None)
    evaluation_feedback.pop("Overall Band Score", None)

    criteria = data.get("constructive_feedback", {}).get("criteria", {})
    for details in criteria.values():
        details.pop("score", None)

    return data


def extract_overall_criteria_scores(feedback: dict) -> dict:
    return extract_scores(feedback)


def clean_feedback_for_response(feedback: dict) -> dict:
    return postprocess_feedback(feedback)

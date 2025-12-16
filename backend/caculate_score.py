import json


def round_ielts(score: float) -> float:
    """
    Round to nearest 0.5 following IELTS convention
    if fractional part is exactly 0.25, round up to 0.5
    if 0.125, round down to 0.0
    if 0.375, round up to 0.5
    if 0.625, round up to 0.5
    if 0.75, round up to 1.0
    if 0.875, round up to 1.0

    """
    integer_part = int(score)
    fractional_part = score - integer_part

    if fractional_part < 0.25:
        return float(integer_part)
    elif 0.25 <= fractional_part < 0.75:
        return integer_part + 0.5
    else:  # fractional_part >= 0.75
        return float(integer_part + 1)
    

def extract_scores(evaluation_json: dict) -> dict:
    """
    expected format:
{
  "overall_score": 6,
  "evaluation_feedback": 
  {
    "task_achievement": {
      "suggested_band_score": 6
    },
    "coherence_and_cohesion": {
      "suggested_band_score": 6
    },
    "lexical_resource": {
      "suggested_band_score": 5.5
    },
    "grammatical_range_and_accuracy": {
      "suggested_band_score": 5.5
    },
    "overall_band_score": {
      "summary": "The essay adequately addresses the task by discussing both views on whether schools or parents should teach children about managing money and providing a personal opinion. However, the response lacks depth in exploring the arguments for each viewpoint and could benefit from more specific examples to support the claims made. The overall quality of writing is generally satisfactory but could be improved in terms of clarity, coherence, and sophistication.",
      "suggested_overall_band_score": 6
    }
  },
  "constructive_feedback": 
  {
    "criteria": 
    {
      "task_response": {
        "score": 6,
      },
      "coherence_and_cohesion": {
        "score": 6,
      },
      "lexical_resource": {
        "score": 6,
      },
      "grammatical_range_and_accuracy": {
        "score": 6,
      }
    },
    "overall_feedback": 
    {
      "summary": "This essay effectively addresses the prompt by discussing both viewpoints and offering a clear personal opinion. The structure is logical and cohesive, with clear paragraphing. The vocabulary is adequate for the task, and grammatical structures are generally accurate. However, to achieve a higher band score, the essay needs to develop its ideas more thoroughly with specific examples and analysis. Expanding the range and accuracy of complex grammatical structures and using more precise and sophisticated vocabulary would also significantly improve the overall quality."
    }
  }
}
    """
# tách điểm cho criteria và cộng tổng tương ứng 2 cách rồi round theo quy ước IELTS
    data = evaluation_json
    criteria_scores_1 = {}
    criteria_scores_2 = {}
    criteria_scores = {}

    try:
        evaluation_feedback = data["evaluation_feedback"]
        constructive_feedback = data["constructive_feedback"]
        criteria = constructive_feedback["criteria"]

        # Extract scores from evaluation feedback
        for criterion, details in evaluation_feedback.items():
            if "suggested_band_score" in details:
                score = float(details["suggested_band_score"])
                criteria_scores_1[criterion] = score

        # Extract scores from constructive feedback
        for criterion, details in criteria.items():
            if "score" in details:
                score = float(details["score"])
                criteria_scores_2[criterion] = score
        # Combine both scores
        values1 = list(criteria_scores_1.values())
        keys2 = list(criteria_scores_2.keys())
        values2 = list(criteria_scores_2.values())

        for i in range(4):
            if values1[i] is None:
                avg = values2[i]
            else:
                avg = (values1[i] + values2[i]) / 2
            criteria_scores[keys2[i]] = round_ielts(avg)

    except KeyError as e:
        print(f"Key error while extracting scores: {e}")
    
    overall_score = round_ielts(sum(criteria_scores.values()) / len(criteria_scores))
    return {
        "overall_score": overall_score,
        "criteria_scores": criteria_scores
    }


def postprocess_feedback(evaluation_json: dict) -> dict:
    ''' Xóa các cột overall_score, suggested_band_score, suggested_overall_band_score, score trong feedback trả về '''
    data = evaluation_json
    try:
        if "overall_score" in data:
            del data["overall_score"]
        
        evaluation_feedback = data["evaluation_feedback"]
        for criterion, details in evaluation_feedback.items():
            if "suggested_band_score" in details:
                del details["suggested_band_score"]
        if "Overall Band Score" in evaluation_feedback:
            del evaluation_feedback["Overall Band Score"]
        
        constructive_feedback = data["constructive_feedback"]
        criteria = constructive_feedback["criteria"]
        for criterion, details in criteria.items():
            if "score" in details:
                del details["score"]
    except KeyError as e:
        print(f"Key error while postprocessing feedback: {e}")
    
    return data

    



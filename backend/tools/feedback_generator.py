import asyncio
import logging
import os

from dotenv import load_dotenv
from google import genai
from google.genai import types
from pydantic import BaseModel, ConfigDict, Field


load_dotenv()
logger = logging.getLogger(__name__)

RETRY_DELAY = max(0.0, float(os.getenv("RETRY_DELAY", "2")))
MAX_RETRIES = max(1, int(os.getenv("MAX_RETRIES", "3")))
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_API_KEY_2 = os.getenv("GEMINI_API_KEY_2")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite")


class EvaluationCriterion(BaseModel):
    suggested_band_score: float = Field(ge=0, le=9)
    feedback: str = Field(min_length=1)


class EvaluationFeedback(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    task_achievement: EvaluationCriterion = Field(alias="Task Achievement")
    coherence_and_cohesion: EvaluationCriterion = Field(alias="Coherence and Cohesion")
    lexical_resource: EvaluationCriterion = Field(alias="Lexical Resource")
    grammatical_range_and_accuracy: EvaluationCriterion = Field(
        alias="Grammatical Range and Accuracy"
    )


class ConstructiveCriterion(BaseModel):
    score: float = Field(ge=0, le=9)
    strengths: list[str] = Field(min_length=1)
    areas_for_improvement: list[str] = Field(min_length=1)
    recommendations: list[str] = Field(min_length=1)


class ConstructiveCriteria(BaseModel):
    task_response: ConstructiveCriterion
    coherence_and_cohesion: ConstructiveCriterion
    lexical_resource: ConstructiveCriterion
    grammatical_range_and_accuracy: ConstructiveCriterion


class OverallFeedback(BaseModel):
    summary: str = Field(min_length=1)


class ConstructiveFeedback(BaseModel):
    criteria: ConstructiveCriteria
    overall_feedback: OverallFeedback


class IELTSFeedbackResponse(BaseModel):
    overall_score: float = Field(ge=0, le=9)
    evaluation_feedback: EvaluationFeedback
    constructive_feedback: ConstructiveFeedback


def create_feedback_prompt(question: str, essay: str, overall_score: float) -> str:
    return f"""
You are an IELTS Writing Task 2 examiner.

Evaluate the essay using the four official IELTS Writing Task 2 criteria:
Task Response, Coherence and Cohesion, Lexical Resource, and Grammatical
Range and Accuracy.

The fine-tuned scoring model estimated an overall band of {overall_score}.
Use this as the anchor score. Criterion scores may differ when the essay
provides clear evidence, but the final feedback must remain consistent with
the anchor score.

For every criterion:
- give a concise evidence-based evaluation;
- identify concrete strengths;
- identify concrete weaknesses;
- provide actionable recommendations;
- use IELTS band scores from 0 to 9 in half-band increments;
- cite short examples from the essay when useful.

Question:
{question}

Essay:
{essay}

Return only the structured response requested by the response schema.
""".strip()


def _configured_api_keys() -> list[str]:
    keys = [key for key in (GEMINI_API_KEY, GEMINI_API_KEY_2) if key]
    return list(dict.fromkeys(keys))


def _parse_feedback_response(response) -> dict:
    parsed = getattr(response, "parsed", None)

    if isinstance(parsed, IELTSFeedbackResponse):
        result = parsed
    elif parsed is not None:
        result = IELTSFeedbackResponse.model_validate(parsed)
    else:
        result = IELTSFeedbackResponse.model_validate_json(response.text)

    return result.model_dump(by_alias=True)


async def get_feedback_for_score(question: str, answer: str, overall_score: float) -> dict:
    keys = _configured_api_keys()
    if not keys:
        raise RuntimeError("GEMINI_API_KEY is required to generate IELTS feedback.")

    prompt = create_feedback_prompt(question, answer, overall_score)
    last_error = None

    for attempt in range(MAX_RETRIES):
        api_key = keys[min(attempt, len(keys) - 1)]

        def run_gemini():
            client = genai.Client(api_key=api_key)
            response = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=IELTSFeedbackResponse,
                    temperature=0.2,
                ),
            )
            return _parse_feedback_response(response)

        try:
            feedback = await asyncio.to_thread(run_gemini)
            feedback["overall_score"] = float(overall_score)
            return feedback
        except Exception as exc:
            last_error = exc
            if attempt + 1 < MAX_RETRIES:
                logger.warning(
                    "Gemini feedback attempt %s/%s failed with %s",
                    attempt + 1,
                    MAX_RETRIES,
                    type(exc).__name__,
                )
                await asyncio.sleep(RETRY_DELAY * (2**attempt))

    raise RuntimeError(
        f"Gemini feedback failed after {MAX_RETRIES} attempts."
    ) from last_error


async def get_feedback(question: str, answer: str) -> dict:
    from backend.tools.bert_scoring import score_essay

    overall_score = await asyncio.to_thread(score_essay, question, answer)
    return await get_feedback_for_score(question, answer, overall_score)


async def generate_feedback(question: str, answer: str, overall_score: float) -> dict:
    """Generate structured IELTS feedback with Gemini only."""
    return await get_feedback_for_score(question, answer, overall_score)


# ---------------------------------------------------------------------------
# Legacy Ollama/Llama pipeline - disabled for the current Gemini-only phase.
#
# Keep this code for a future fine-tuned Llama model. The intended future
# pipeline is:
#   fine-tuned Llama evaluation -> Gemini JSON formatter -> report processor
#
# Legacy environment variables:
# OLLAMA_CHAT_ENDPOINT = os.getenv("OLLAMA_CHAT_ENDPOINT")
# OLLAMA_GEN_ENDPOINT = os.getenv("OLLAMA_GEN_ENDPOINT")
#
# Legacy imports:
# import json
# import httpx
# from backend.tools.json_parser import read_json_from_string
#
# async def PromptMistral(band: float, question: str, essay: str) -> str:
#     prompt = """
#     Overall Band Score:
#
#     Evaluate the essay using Task Achievement, Coherence and Cohesion,
#     Lexical Resource, and Grammatical Range and Accuracy. Keep the detailed
#     evaluation consistent with the supplied overall IELTS band.
#
#     Overall band: {}
#     Prompt: {}
#     Essay: {}
#     Evaluation:
#     """
#     return prompt.format(band, question, essay)
#
#
# async def get_evaluation_mistral(
#     overall_score: float,
#     question: str,
#     answer: str,
#     gemini_formatter_client,
# ) -> str:
#     evaluation_prompt = await PromptMistral(
#         band=overall_score,
#         question=question,
#         essay=answer,
#     )
#     payload = {
#         "model": "ielts-mistral:latest",
#         "messages": [{"role": "user", "content": evaluation_prompt}],
#         "options": {"num_predict": 2048, "temperature": 0.7},
#     }
#     timeout = httpx.Timeout(180.0, connect=10.0)
#     async with httpx.AsyncClient(timeout=timeout) as http_client:
#         response = await http_client.post(OLLAMA_CHAT_ENDPOINT, json=payload)
#         response.raise_for_status()
#         evaluation_text = ""
#         for line in response.text.splitlines():
#             try:
#                 data = json.loads(line)
#                 evaluation_text += data["message"]["content"]
#             except (KeyError, json.JSONDecodeError):
#                 continue
#
#     formatter_prompt = (
#         "Convert the following Llama evaluation to the IELTS JSON schema. "
#         "Return JSON only.\n\n"
#         f"{evaluation_text}"
#     )
#     response = await asyncio.to_thread(
#         gemini_formatter_client.models.generate_content,
#         model=GEMINI_MODEL,
#         contents=formatter_prompt,
#     )
#     return response.text

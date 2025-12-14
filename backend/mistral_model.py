from bert_setup import get_overall_score
import asyncio
import httpx
from dotenv import load_dotenv
import os
import json
import time
from google import genai
from handle_json import read_json_from_string

# Load environment variables
load_dotenv()

# Environment variables with safe defaults
RETRY_DELAY = int(os.getenv("RETRY_DELAY", "3"))
MAX_RETRIES = int(os.getenv("MAX_RETRIES", "3"))
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_API_KEY_2 = os.getenv("GEMINI_API_KEY_2")
BAND_DISCRIPTIOR_FILE = os.getenv("BAND_DISCRIPTIOR_FILE")
OLLAMA_CHAT_ENDPOINT = os.getenv("OLLAMA_CHAT_ENDPOINT")
OLLAMA_GEN_ENDPOINT = os.getenv("OLLAMA_GEN_ENDPOINT")

async def PromptMistral(band: float, question: str, essay: str) -> str:
    PROMPT = """
    Overall Band Score: {}

    In this task, you are required to evaluate the following essay based on the official IELTS scoring criteria. 
    Please provide detailed feedback for each of the four criteria, always keeping in mind that the essay received the overall score above. 

    ## Task Achievement:
    - Evaluate how well the candidate has addressed the given task.
    - Assess the clarity and coherence of the response in presenting ideas.
    - Identify if the candidate has fully covered all parts of the task and supported arguments appropriately.

    ## Coherence and Cohesion:
    - Assess the overall organization and structure of the essay.
    - Evaluate the use of linking devices to connect ideas and paragraphs.
    - Identify if there is a logical flow of information.

    ## Lexical Resource (Vocabulary):
    - Examine the range and accuracy of vocabulary used in the essay.
    - Point out specific mistakes in vocabulary, such as inaccuracies or overuse of certain words and Suggest modified versions or alternatives for the identified mistakes. [list of mistakes and rectify]
    - Assess the appropriateness of vocabulary for the given context.

    ## Grammatical Range and Accuracy:
    - Evaluate the variety and complexity of sentence structures.
    - Point out specific grammatical errors, such as incorrect verb forms or sentence construction and Suggest modified versions or corrections for the identified mistakes. [list of mistakes and rectify]
    - Examine the use of punctuation and sentence formation.


    ## Feedback and Additional Comments:
    - Provide constructive feedback highlighting specific strengths and areas for improvement.
    - Suggest strategies for enhancement in weaker areas.

    ## Prompt:
    {}

    ## Essay:
    {}

    ## Evaluation:
    {}"""

    return PROMPT.format(
        band,
        question,
        essay,
        "",
    )

async def create_constructive_feedback_prompt(question: str, essay: str, overall_score: float) -> str:
    prompt = (
        f"You are an IELTS Writing Task 2 examiner.\n"
        f"Provide a constructive evaluation for the following essay based on the official IELTS scoring criteria.\n\n"
        f"Question:\n{question}\n\n"
        f"Essay:\n{essay}\n\n"
        f"The essay above received an overall IELTS Writing band score of {str(overall_score)}.\n\n"
        f"As an IELTS examiner, provide constructive feedback based on the official IELTS scoring criteria.\n\n"
        f"Return your evaluation strictly in the following JSON format:\n\n"
        f"{{\n"
        f'  "criteria": {{\n'
        f'    "task_response": {{\n'
        f'      "score": <score>,\n'
        f'      "strengths": [<list of specific strengths>],\n'
        f'      "areas_for_improvement": [<list of specific areas needing improvement>],\n'
        f'      "recommendations": [<list of actionable advice>]\n'
        f'    }},\n'
        f'    "coherence_and_cohesion": {{\n'
        f'      "score": <score>,\n'
        f'      "strengths": [<list of specific strengths>],\n'
        f'      "areas_for_improvement": [<list of specific areas needing improvement>],\n'
        f'      "recommendations": [<list of actionable advice>]\n'
        f'    }},\n'
        f'    "lexical_resource": {{\n'
        f'      "score": <score>,\n'
        f'      "strengths": [<list of specific strengths>],\n'
        f'      "areas_for_improvement": [<list of specific areas needing improvement>],\n'
        f'      "recommendations": [<list of actionable advice>]\n'
        f'    }},\n'
        f'    "grammatical_range_and_accuracy": {{\n'
        f'      "score": <score>,\n'
        f'      "strengths": [<list of specific strengths>],\n'
        f'      "areas_for_improvement": [<list of specific areas needing improvement>],\n'
        f'      "recommendations": [<list of actionable advice>]\n'
        f'    }}\n'
        f'  }},\n'
        f'  "overall_feedback": {{\n'
        f'    "summary": "<short paragraph summarizing key strengths and improvement directions>"\n'
        f'  }}\n'
        f"}}\n\n"
        f"Rules:\n"
        f"- All keys and strings must use double quotes (\"\") according to strict JSON format.\n"
        f"- Component scores must be consistent with the given overall band score.\n"
        f"- Focus on giving constructive feedback: mention what was done well, what needs improvement, and how to improve.\n"
        f"- Be specific and cite examples from the essay when possible.\n"
        f"- Return ONLY the JSON object. Do not add any explanations, headers, markdown, or extra text before or after.\n"
    )
    return prompt

async def get_evaluation_mistral(user_id: str, overall_score: float, question: str , answer: str, client) -> str:
    evaluation_prompt = await PromptMistral(band=overall_score, question=question, essay=answer)
    
    payload = {
        "model": "ielts-mistral:latest",
        "messages": [
            {"role": "user", "content": evaluation_prompt}
        ],
        "options": {
            "num_predict": 2048,
            "temperature": 0.7
        }
    }
    #payload = {
            #"model": "ielts-mistral:latest",
            #"prompt": evaluation_prompt,
            #"options": {
                #"num_predict": 2048,
                #"temperature": 0.7
            #}
        #}
    timeout = httpx.Timeout(180.0, connect=10.0)
    try:
        async with httpx.AsyncClient(timeout=timeout) as http_client:
            response = await http_client.post(OLLAMA_CHAT_ENDPOINT, json=payload)
            response.raise_for_status()

            # Ghép nội dung trả về dạng JSON line (stream)
            evaluation_text = ""
            for line in response.text.splitlines():
                try:
                    data = json.loads(line)
                    #evaluation_text += data.get("response", "") for generate endpoint
                    #evaluation_text += data["message"]["content"] for chat endpoint
                    evaluation_text += data["message"]["content"]
                except Exception:
                    continue

    except httpx.HTTPError as e:
        print(f"Error calling Ollama: {e}")
        return "Failed to get feedback from Ollama."

    gemini_prompt = (
            f"You are a strict JSON fixer and formatter.\n"
            f"Your task is to take the following possibly malformed JSON and output a strictly valid, properly formatted JSON object—nothing else.\n\n"
            f"---\n"
            f"{evaluation_text}\n"
            f"---\n\n"
            f"Rules:\n"
            f"- Output only the JSON object. No code fences or any extra text.\n"
            f"- Use only standard double quotes (\") for keys and string values.\n"
            f"- Remove any trailing or leading commas; commas may only separate items.\n"
            f"- Ensure all strings are properly opened, closed, and escaped (e.g. newlines as \\n, tabs as \\t).\n"
            f"- Validate that braces and brackets match exactly.\n"
            f"- The result must be parseable by JSON.parse() without errors.\n"
        )

    def run_gemini():
        return client.models.generate_content(
            model="gemini-2.5-flash-lite",#gemini-2.5-flash
            contents=gemini_prompt
        )

    gemini_response = await asyncio.to_thread(run_gemini)
    corrected_json = gemini_response.text
    return corrected_json

async def get_constructive_feedback(user_id: str, overall_score: float, question: str , answer: str, client, band_descriptors) -> str:
    constructive_prompt = await create_constructive_feedback_prompt(question, answer, overall_score)

    def run_gemini():
        start_time = time.time()  # Start the timer
        result = client.models.generate_content(
            model="gemini-2.5-flash-lite",#gemini-2.5-flash
            contents=[band_descriptors, constructive_prompt]
        )
        end_time = time.time()  # End the timer
        print(f"run_gemini execution time: {end_time - start_time:.2f} seconds")  # Log the execution time
        return result

    constructive_response = await asyncio.to_thread(run_gemini)
    constructive_text = constructive_response.text
    return constructive_text

async def get_feedback(user_id: str, question: str, answer: str) -> dict:
    """
    Compute overall score and return merged evaluation + constructive feedback.
    """
    # 1. Compute IELTS score
    overall_score = float(get_overall_score(question, answer))

    # 2. Initialize clients
    client = genai.Client(api_key=GEMINI_API_KEY)
    client_2 = genai.Client(api_key=GEMINI_API_KEY_2)
    band_descriptors = client.files.upload(file=BAND_DISCRIPTIOR_FILE)

    evaluation_task = get_evaluation_mistral(user_id, overall_score, question, answer, client_2) # sau nhớ xóa await
    constructive_task = get_constructive_feedback(user_id, overall_score, question, answer, client, band_descriptors)

    evaluation_text, constructive_text = await asyncio.gather(evaluation_task, constructive_task)

    # 5. Parse and merge
    eval_res = read_json_from_string(evaluation_text)
    const_res = read_json_from_string(constructive_text)

    if not eval_res["valid_json"]:
        raise ValueError(f"Evaluation JSON parse error: {eval_res['error']}")
    if not const_res["valid_json"]:
        raise ValueError(f"Constructive JSON parse error: {const_res['error']}")

    return {
        "user_id": user_id,
        "overall_score": overall_score,
        "evaluation_feedback": eval_res["parsed"],
        "constructive_feedback": const_res["parsed"]
    }
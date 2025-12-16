from fastapi import FastAPI
from pydantic import BaseModel
import uvicorn
import os
from dotenv import load_dotenv
from pymongo import MongoClient
import asyncio
import uuid
import datetime
# Import from our modules
from mistral_model import get_feedback
from grammar import get_annotated_fixed_essay
from caculate_score import extract_scores, postprocess_feedback
load_dotenv()

OLLAMA_GEN_ENDPOINT = os.getenv("OLLAMA_GEN_ENDPOINT")
OLLAMA_CHAT_ENDPOINT = os.getenv("OLLAMA_CHAT_ENDPOINT")
MONGO_URI = os.getenv("MONGO_URI")
PORT = int(os.getenv("PORT", 8000))
# async def get_evaluation_mistral(overall_score: float, question: str , answer: str, client) -> str:
#     """Get detailed evaluation feedback from Mistral model via Ollama."""
#     evaluation_prompt = await PromptMistral(band=overall_score, question=question, essay=answer)
    
#     payload = {
#         "model": "ielts-mistral:latest",
#         "prompt": evaluation_prompt,
#         "options": {
#             "num_predict": 2048,
#             "temperature": 0.7
#         }
#     }
#     timeout = httpx.Timeout(180.0, connect=10.0)
#     try:
#         async with httpx.AsyncClient(timeout=timeout) as http_client:
#             response = await http_client.post(OLLAMA_GEN_ENDPOINT, json=payload)
#             response.raise_for_status()

#             # Ghép nội dung trả về dạng JSON line (stream)
#             evaluation_text = ""
#             for line in response.text.splitlines():
#                 try:
#                     data = json.loads(line)
#                     #evaluation_text += data["message"]["content"] for chat endpoint
#                     evaluation_text += data.get("response", "") #for generate endpoint
#                 except Exception:
#                     continue
#     except httpx.HTTPError as e:
#         print(f"Error calling Ollama: {e}")
#         return "Failed to get feedback from Ollama."
#     return evaluation_text

# Initialize FastAPI app
#CONNECT TO MONGODB
client = MongoClient(MONGO_URI)
db = client.ielts_writing_evaluation

#define collections
evaluations_collection = db.evaluations
annotation = db.annotations

class EssayEvaluationRequest(BaseModel):
    question: str
    answer: str

app = FastAPI(
    title="IELTS Writing Task 2 Evaluation API",
    description="API for evaluating IELTS Writing Task 2 essays using BERT and Mistral models",
    version="1.0.0"
)

@app.get("/")
async def root():
    return {"message": "Welcome to the IELTS Writing Task 2 Evaluation API!"}
@app.get("/health")
async def health_check():
    return {"status": "ok"}
@app.get("/ready")
async def readiness_check():
    return {"status": "ready"}
@app.get("/live")
async def liveness_check():
    return {"status": "alive"}
@app.get("/version")
async def version_check():
    return {"version": "1.0.0"}



@app.post("/evaluate_essay")
async def evaluate_essay(request: EssayEvaluationRequest):    
    # Get detailed feedback from Mistral model
    detailed_feedback = await get_feedback(request.question, request.answer)
    overall_criteria_scores = extract_scores(detailed_feedback)
    detailed_feedback = postprocess_feedback(detailed_feedback)

    return {
        "detailed_feedback": detailed_feedback,
        "overall_criteria_scores": overall_criteria_scores
    }

@app.post("/grammar_correction")
async def grammar_correction(answer: str):
    """Get grammar corrections with error and fix highlights."""
    result = await get_annotated_fixed_essay(answer)
    return {
        "corrected_text": result['corrected_text'],
        "with_errors": result['with_errors'],
        "fixed_only": result['fixed_only']
    }

@app.post("/essay_process")
async def essay_process(request: EssayEvaluationRequest):
    """
    Combined endpoint to run evaluation and grammar correction in one session.
    Stores all results under a shared session_id.
    """
    session_id = str(uuid.uuid4())
    now = datetime.utcnow()

    # Get detailed feedback from Mistral model and grammar corrections
    detailed_feedback = get_feedback(request.question, request.answer)
    grammar_result = get_annotated_fixed_essay(request.answer)

    feedback, grammar_data = await asyncio.gather(detailed_feedback, grammar_result)
    overall_criteria_scores = extract_scores(feedback)
    feedback = postprocess_feedback(feedback)

    # Store evaluation results in MongoDB
    evaluations_collection.insert_one({
        "session_id": session_id,
        "question": request.question,
        "answer": request.answer,
        "detailed_feedback": feedback,
        "overall_criteria_scores": overall_criteria_scores,
        "created_at": now
    })
    
    # Store grammar correction results in MongoDB
    annotation_collection = db.grammar_corrections
    annotation_collection.insert_one({
        "session_id": session_id,
        "original_text": request.answer,
        "corrected_text": grammar_data['corrected_text'],
        "with_errors": grammar_data['with_errors'],
        "fixed_only": grammar_data['fixed_only'],
        "created_at": now
    })
    
    return {
        "session_id": session_id,
        "detailed_feedback": feedback,
        "overall_criteria_scores": overall_criteria_scores,
        "corrected_text": grammar_data['corrected_text'],
        "with_errors": grammar_data['with_errors'],
        "fixed_only": grammar_data['fixed_only']
    }

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=PORT, reload=True)
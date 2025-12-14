from fastapi import FastAPI
from pydantic import BaseModel
import uvicorn
import os
from dotenv import load_dotenv


# Import from our modules
from mistral_model import get_feedback

# Load environment variables
load_dotenv()

OLLAMA_GEN_ENDPOINT = os.getenv("OLLAMA_GEN_ENDPOINT")
# async def get_evaluation_mistral(user_id: str, overall_score: float, question: str , answer: str, client) -> str:
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
app = FastAPI(
    title="IELTS Writing Task 2 Evaluation API",
    description="API for evaluating IELTS Writing Task 2 essays using BERT and Mistral models",
    version="1.0.0"
)
class EssayRequest(BaseModel):
    user_id: str
    question: str
    answer: str
class EssayResponse(BaseModel):
    detailed_feedback: dict

@app.post("/evaluate", response_model=EssayResponse)
#  return {
#         "user_id": user_id,
#         "overall_score": overall_score,
#         "evaluation_feedback": eval_res["parsed"],
#         "constructive_feedback": const_res["parsed"]
#     }
async def evaluate_essay(request: EssayRequest):
    """Evaluate an IELTS Writing Task 2 essay."""
    user_id = request.user_id
    question = request.question
    answer = request.answer

    detailed_feedback = await get_feedback(user_id, question, answer)

    return EssayResponse(
        detailed_feedback=detailed_feedback
    )

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
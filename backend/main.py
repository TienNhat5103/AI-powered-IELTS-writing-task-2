import asyncio
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, field_validator
from pymongo import MongoClient
from pymongo.errors import PyMongoError

from backend.agents.orchestrator import IELTSWritingOrchestrator
from backend.observability.telemetry import (
    initialize_telemetry,
    instrument_fastapi,
    shutdown_telemetry,
)


load_dotenv()
logger = logging.getLogger(__name__)
telemetry_runtime = initialize_telemetry()

# Legacy Ollama settings are intentionally disabled. The previous
# Llama -> Gemini formatter flow is preserved as comments in
# tools/feedback_generator.py.
# OLLAMA_GEN_ENDPOINT = os.getenv("OLLAMA_GEN_ENDPOINT")
# OLLAMA_CHAT_ENDPOINT = os.getenv("OLLAMA_CHAT_ENDPOINT")

MONGO_URI = os.getenv("MONGO_URI")
PORT = int(os.getenv("PORT", 8000))

client = (
    MongoClient(MONGO_URI, serverSelectionTimeoutMS=2000)
    if MONGO_URI
    else None
)
db = client.ielts_writing_evaluation if client is not None else None
orchestrator = IELTSWritingOrchestrator()


class EssayEvaluationRequest(BaseModel):
    question: str
    answer: str

    @field_validator("question", "answer")
    @classmethod
    def must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value


@asynccontextmanager
async def lifespan(_: FastAPI):
    await orchestrator.start()
    try:
        yield
    finally:
        try:
            await orchestrator.close()
        finally:
            try:
                if client is not None:
                    client.close()
            finally:
                shutdown_telemetry()


app = FastAPI(
    title="IELTS Writing Task 2 Evaluation API",
    description="IELTS evaluation agent using LangGraph, BERT, Gemini, and CoEdit T5",
    version="1.1.0",
    lifespan=lifespan,
)
instrument_fastapi(app, telemetry_runtime)


@app.get("/")
async def root():
    return {"message": "Welcome to the IELTS Writing Task 2 Evaluation API!"}


@app.get("/health")
async def health_check():
    return {"status": "ok"}


@app.get("/ready")
async def readiness_check():
    return {
        "status": "ready",
        "langgraph": "checkpointed",
        "mongodb": "configured" if db is not None else "disabled",
    }


@app.get("/live")
async def liveness_check():
    return {"status": "alive"}


@app.get("/version")
async def version_check():
    return {"version": "1.1.0"}


@app.post("/evaluate_essay")
async def evaluate_essay(request: EssayEvaluationRequest):
    return await orchestrator.evaluate_essay(request.question, request.answer)


@app.post("/grammar_correction")
async def grammar_correction(answer: str):
    """Get grammar corrections with error and fix highlights."""
    if not answer.strip():
        raise HTTPException(status_code=422, detail="Essay answer must not be empty.")
    return await orchestrator.correct_grammar(answer)


@app.post("/essay_process")
async def essay_process(request: EssayEvaluationRequest):
    """Run evaluation and grammar correction under one LangGraph session."""
    now = datetime.now(timezone.utc)
    result = await orchestrator.process_essay(request.question, request.answer)

    if db is not None:
        try:
            await asyncio.gather(
                asyncio.to_thread(
                    db.evaluations.insert_one,
                    {
                        "session_id": result["session_id"],
                        "question": request.question,
                        "answer": request.answer,
                        "detailed_feedback": result["detailed_feedback"],
                        "overall_criteria_scores": result["overall_criteria_scores"],
                        "created_at": now,
                    },
                ),
                asyncio.to_thread(
                    db.grammar_corrections.insert_one,
                    {
                        "session_id": result["session_id"],
                        "original_text": request.answer,
                        "corrected_text": result["corrected_text"],
                        "with_errors": result["with_errors"],
                        "fixed_only": result["fixed_only"],
                        "created_at": now,
                    },
                ),
            )
        except PyMongoError:
            logger.exception("MongoDB persistence failed for session %s", result["session_id"])

    return result


if __name__ == "__main__":
    uvicorn.run("backend.main:app", host="0.0.0.0", port=PORT, reload=True)

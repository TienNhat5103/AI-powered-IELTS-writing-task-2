# IELTS Writing Task 2 Evaluation Agent

An IELTS Writing Task 2 evaluation workflow built with FastAPI and LangGraph.

## Active architecture

```text
FastAPI
  -> OpenTelemetry HTTP server span
  -> LangGraph orchestrator
      -> workflow root span
      -> LangGraph node spans
      -> fine-tuned BERT scoring
      -> CoEdit T5 grammar correction
      -> Gemini structured feedback
      -> score processor
      -> JSON report
```

BERT scoring and T5 grammar correction run as separate LangGraph nodes. In the
combined workflow they start in parallel, while Gemini feedback begins after
the BERT score is available. LangGraph stores checkpoints in local SQLite.
OpenTelemetry tracing is available but disabled by default.

Ollama is not required by the active pipeline. The previous Ollama/Llama code
is preserved as comments in `backend/tools/feedback_generator.py` for future
use with a fine-tuned Llama model and Gemini JSON formatting.

RAG and Temporal are not active.

## OpenTelemetry tracing

Tracing covers FastAPI requests, each IELTS workflow, and the important
LangGraph nodes. Telemetry does not include essay text, prompts, API keys,
feedback content, raw session IDs, or captured HTTP headers. Query strings are
redacted before spans are exported, together with client IP and user-agent
values.

Enable local console traces in `backend/.env`:

```env
OTEL_SDK_DISABLED=false
OTEL_SERVICE_NAME=ielts-writing-agent
OTEL_TRACES_EXPORTER=console
```

Disable tracing:

```env
OTEL_SDK_DISABLED=true
```

To send traces directly to an existing OTLP HTTP endpoint:

```env
OTEL_SDK_DISABLED=false
OTEL_TRACES_EXPORTER=otlp
OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=http://localhost:4318/v1/traces
```

The project does not start an OpenTelemetry Collector or tracing backend.

## Requirements

- Python 3.11, 3.12, or 3.13
- A Gemini API key
- Internet access on the first BERT/T5 run to cache the models
- MongoDB only when result persistence is wanted

## Run the backend

From PowerShell at the project root:

```powershell
.\run_backend.ps1 -Install
```

On first run, edit `backend/.env` and set:

```env
GEMINI_API_KEY=your_key
```

Then run without reinstalling:

```powershell
.\run_backend.ps1
```

API documentation is available at `http://localhost:8000/docs`.

## Run the frontend

Keep the backend running, then open a second PowerShell terminal:

```powershell
.\venv\Scripts\python.exe -m streamlit run frontend/app.py
```

The Streamlit UI is available at `http://localhost:8501`.

## Main endpoints

- `POST /evaluate_essay`: BERT score plus Gemini feedback
- `POST /grammar_correction`: CoEdit T5 correction
- `POST /essay_process`: evaluation and grammar correction in one session
- `GET /health`, `/ready`, `/live`, `/version`: service checks

MongoDB is optional. When `MONGO_URI` is empty, API responses still work and
only database persistence is skipped.

## Test

See `TESTING.md` for mock workflow tests and real model smoke tests.

```powershell
.\venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py"
```

## Project layout

```text
backend/
  agents/
    ielts_graph.py
    orchestrator.py
  observability/
    telemetry.py
  tools/
    bert_scoring.py
    feedback_generator.py
    grammar_checker.py
    json_parser.py
    report_generator.py
    score_processor.py
  main.py
frontend/
  app.py
tests/
run_backend.ps1
requirements.txt
```

# AGENTS.md

## Project Overview

This project is an IELTS Writing Task 2 Evaluation Agent built with FastAPI
and LangGraph.

The active system combines:

- a fine-tuned BERT model for IELTS band prediction;
- Google Gemini for structured IELTS feedback;
- CoEdit T5 for grammar correction;
- LangGraph for workflow orchestration and checkpointing;
- SQLite for local LangGraph checkpoints;
- OpenTelemetry for optional FastAPI and LangGraph tracing;
- optional MongoDB persistence;
- Streamlit as the current frontend.

RAG, MCP and Temporal are not active.

Ollama is disabled in the current runtime. The previous Llama/Ollama flow is
preserved as commented code in `backend/tools/feedback_generator.py` so a
future fine-tuned Llama model can produce the evaluation before Gemini formats
the final JSON.

## Active Architecture

```text
User
  -> Streamlit or API client
  -> FastAPI
  -> OpenTelemetry HTTP server span
  -> IELTSWritingOrchestrator
  -> workflow root span
  -> LangGraph workflow
       -> node spans
       -> BERT scoring
       -> CoEdit T5 grammar correction
       -> Gemini structured feedback
       -> score processor
       -> report generator
  -> optional MongoDB persistence
  -> JSON response
```

In the combined workflow, BERT scoring and T5 grammar correction start as
separate LangGraph nodes. Gemini feedback starts after the BERT score is
available. The report node waits for both the processed feedback and grammar
result.

## Workflows

### Evaluation Workflow

```text
validate_input
  -> score_essay
  -> generate_feedback
  -> process_scores
  -> build_report
```

### Grammar Workflow

```text
validate_input
  -> correct_grammar
  -> build_report
```

### Combined Workflow

```text
validate_input
  -> prepare_session
  -> score_essay --------> generate_feedback -> process_scores --\
  -> correct_grammar ---------------------------------------------> build_report
```

Every workflow receives a unique `session_id`. LangGraph uses that value as
the checkpoint `thread_id`.

## Component Responsibilities

### FastAPI

File: `backend/main.py`

- Validate incoming API requests.
- Call the orchestrator.
- Expose health and workflow endpoints.
- Persist combined results to MongoDB when `MONGO_URI` is configured.
- Return results even when optional MongoDB persistence fails.

### Orchestrator

File: `backend/agents/orchestrator.py`

- Initialize the SQLite checkpointer.
- Compile evaluation, grammar, and combined graphs.
- Assign or reuse a session ID.
- Invoke graphs with the correct LangGraph thread configuration.
- Close checkpoint resources during application shutdown.

### LangGraph

File: `backend/agents/ielts_graph.py`

- Define workflow state.
- Validate input.
- Coordinate tool execution.
- Run BERT and T5 as separate nodes in the combined workflow.
- Join tool results before report generation.
- Allow dependency injection for tests.

### OpenTelemetry

File: `backend/observability/telemetry.py`

- Instrument FastAPI requests when telemetry is enabled.
- Create one top-level application span for each workflow invocation.
- Trace validation, model tools, score processing, and report generation.
- Export traces to the console or an OTLP HTTP endpoint.
- Record sanitized exceptions and error status without provider messages.
- Redact HTTP query strings, client IP, and user-agent values, and disable HTTP
  header capture.
- Never add essays, prompts, API keys, feedback, or raw session IDs to spans.
- Leave tracing disabled by default through `OTEL_SDK_DISABLED=true`.

### BERT Scoring Tool

File: `backend/tools/bert_scoring.py`

Input:

- IELTS question;
- essay answer.

Output:

- estimated overall IELTS band score from 0 to 9.

The model is loaded lazily on the first scoring request. Inference is protected
by a lock so concurrent requests do not use the same model instance at the
same time.

### Grammar Tool

File: `backend/tools/grammar_checker.py`

Input:

- essay answer.

Output:

- corrected plain text;
- HTML with errors and fixes;
- HTML containing the corrected version.

The CoEdit T5 model is loaded lazily. Blocking inference runs outside the
FastAPI event loop.

### Gemini Feedback Tool

File: `backend/tools/feedback_generator.py`

Input:

- IELTS question;
- essay answer;
- BERT anchor score.

Output:

- evaluation feedback for four IELTS criteria;
- strengths;
- areas for improvement;
- recommendations;
- structured criterion scores.

Gemini uses a Pydantic response schema. The tool retries failed requests and
can use `GEMINI_API_KEY_2` as an optional fallback key.

### Score Processor

File: `backend/tools/score_processor.py`

- Match scores by criterion name.
- Combine evaluation and constructive scores.
- Round scores to IELTS half bands.
- Reject incomplete score responses.
- Remove internal score fields from user-facing feedback.

### Report Generator

File: `backend/tools/report_generator.py`

- Build evaluation-only reports.
- Build grammar-only reports.
- Build combined reports.
- Include `session_id` in workflow responses.

## API Endpoints

- `GET /health`
- `GET /ready`
- `GET /live`
- `GET /version`
- `POST /evaluate_essay`
- `POST /grammar_correction`
- `POST /essay_process`

The current API version is `1.1.0`.

## Folder Structure

```text
project/
  backend/
    agents/
      ielts_graph.py
      orchestrator.py
    tools/
      bert_scoring.py
      feedback_generator.py
      grammar_checker.py
      json_parser.py
      report_generator.py
      score_processor.py
    observability/
      telemetry.py
    main.py
    .env.example
  frontend/
    app.py
  tests/
    test_api_contract.py
    test_langgraph_workflow.py
    test_tools_lightweight.py
  README.md
  TESTING.md
  AGENTS.md
  requirements.txt
  run_backend.ps1
```

## Local Environment

Use `venv` as the only virtual environment folder:

```powershell
.\run_backend.ps1 -Install
```

Run later without reinstalling:

```powershell
.\run_backend.ps1
```

Do not introduce `.venv` or another environment folder in documentation or
scripts.

Required environment variable:

```env
GEMINI_API_KEY=your_key
```

Optional environment variables are documented in `backend/.env.example`.

Enable local console tracing:

```env
OTEL_SDK_DISABLED=false
OTEL_TRACES_EXPORTER=console
```

Use `OTEL_TRACES_EXPORTER=otlp` and
`OTEL_EXPORTER_OTLP_TRACES_ENDPOINT` for an existing OTLP HTTP endpoint.

## Testing

Run all automated tests from the project root:

```powershell
.\venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -v
```

Use `TESTING.md` for API smoke tests, direct tool tests, checkpoint inspection,
and Streamlit tests.

Automated tests must mock BERT, T5, and Gemini when testing graph behavior.
Tests should not download models or call external APIs unless explicitly
marked as real-tool smoke tests.

## Development Principles

- Keep each tool independent and replaceable.
- Keep orchestration inside `backend/agents`.
- Keep model and API logic inside `backend/tools`.
- Avoid loading models during module import.
- Keep blocking model inference outside the async event loop.
- Validate external AI output before processing it.
- Do not expose essays, API keys, or sensitive content in logs.
- Do not add essay text, prompts, raw session IDs, or exception messages to
  telemetry attributes and events.
- Preserve the legacy Ollama code as comments until the Llama path is
  intentionally restored.
- Do not add RAG unless the project requirements change.
- Add tests for graph routing, API contracts, and pure processing logic.

## Planned Next Steps

1. Evaluate trace output and sampling under realistic local workloads.
2. Add metrics only after trace naming and privacy rules are stable.
3. Add structured application logging without recording essay content.
4. Evaluate Temporal only when workflows become background jobs, need durable
   cross-process retries, or must survive service restarts.
5. Consider persistent production checkpoint storage such as PostgreSQL.
6. Add user progress tracking and human feedback integration.

## Deployment

Deployment remains postponed until the local workflow and observability are
stable.

Potential future platforms:

- Google Cloud Run;
- Google Compute Engine;
- Oracle Cloud;
- Azure Container Apps.

## License

For educational and research purposes.

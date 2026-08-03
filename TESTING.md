# Huong dan kiem thu

Pipeline dang hoat dong:

```text
FastAPI -> LangGraph -> BERT scoring
                     -> CoEdit T5 grammar
                     -> Gemini feedback
                     -> score processor
                     -> JSON report
```

Ollama dang bi vo hieu hoa va khong can khoi dong.

Huong dan nay gia dinh Uvicorn dang chay tai:

```text
http://localhost:8000
```

Tat ca lenh ben duoi chay trong PowerShell tai thu muc goc project.

## 1. Tao du lieu test dung chung

Mo mot PowerShell terminal moi:

```powershell
$baseUrl = "http://localhost:8000"

$question = "Some people believe that technology improves education, while others think it creates more problems. Discuss both views and give your opinion."

$essay = @"
Technology has become an important part of modern education. Some people believe
that digital tools give students more opportunities, while others argue that they
can reduce concentration. This essay will discuss both views before explaining why
I believe technology is beneficial when it is used carefully.

On the one hand, online platforms provide quick access to information. Students can
watch lectures, read articles, and practise skills without being limited by their
location. This is especially useful for learners who live far from good schools.
However, technology can also distract students because social media and games are
available on the same devices.

In my opinion, schools should not reject technology. Teachers should instead show
students how to use it responsibly and combine digital materials with classroom
discussion. In conclusion, technology creates some challenges, but its educational
benefits are greater when teachers provide clear guidance.
"@
```

Voi viec danh gia band score thuc te, nen dung bai viet gan 250 tu. Doan tren
chi phu hop cho smoke test nhanh.

## 2. Test server va API

### Health check

```powershell
Invoke-RestMethod "$baseUrl/health"
Invoke-RestMethod "$baseUrl/live"
Invoke-RestMethod "$baseUrl/ready"
Invoke-RestMethod "$baseUrl/version"
```

Ket qua mong doi:

```text
/health  -> status = ok
/live    -> status = alive
/ready   -> langgraph = checkpointed
/version -> version = 1.1.0
```

Swagger UI:

```text
http://localhost:8000/docs
```

## 3. Test feature cham diem va feedback

Endpoint nay chay:

```text
BERT score -> Gemini structured feedback -> score processor -> report
```

```powershell
$evaluationBody = @{
    question = $question
    answer = $essay
} | ConvertTo-Json

$evaluationResult = Invoke-RestMethod `
    -Method Post `
    -Uri "$baseUrl/evaluate_essay" `
    -ContentType "application/json" `
    -Body $evaluationBody

$evaluationResult | ConvertTo-Json -Depth 20
```

Kiem tra nhanh:

```powershell
$evaluationResult.session_id
$evaluationResult.overall_criteria_scores.overall_score
$evaluationResult.overall_criteria_scores.criteria_scores
$evaluationResult.detailed_feedback.evaluation_feedback
$evaluationResult.detailed_feedback.constructive_feedback
```

Feature pass khi:

- Co `session_id`.
- `overall_score` nam trong khoang 0-9.
- Co du bon score: `task_response`, `coherence_and_cohesion`,
  `lexical_resource`, `grammatical_range_and_accuracy`.
- Moi tieu chi co evaluation, strengths, areas for improvement va
  recommendations.
- Response la JSON hop le, khong co Markdown fence cua Gemini.

Lan dau goi endpoint co the cham hon do BERT duoc tai va cache tu Hugging Face.

## 4. Test feature grammar T5

`/grammar_correction` dang nhan `answer` bang query parameter. Nen dung cau ngan
cho smoke test de tranh URL qua dai.

```powershell
$grammarInput = "He go to school everyday and she do not likes mathematics."
$encodedGrammarInput = [uri]::EscapeDataString($grammarInput)

$grammarResult = Invoke-RestMethod `
    -Method Post `
    -Uri "$baseUrl/grammar_correction?answer=$encodedGrammarInput"

$grammarResult | ConvertTo-Json -Depth 10
```

Kiem tra nhanh:

```powershell
$grammarResult.session_id
$grammarResult.corrected_text
$grammarResult.with_errors
$grammarResult.fixed_only
```

Feature pass khi:

- Co `session_id`.
- `corrected_text` chua cau da sua.
- `with_errors` chua HTML danh dau loi va phan sua.
- `fixed_only` chua HTML cua noi dung sau khi sua.

Lan dau goi endpoint co the cham do model `grammarly/coedit-large` duoc tai va
cache.

## 5. Test full feature

Endpoint `/essay_process` chay workflow day du:

```text
                  -> BERT -> Gemini feedback -> score processor
validate -> session                                      -> report
                  -> CoEdit T5 grammar ------------------/
```

BERT va T5 bat dau o hai LangGraph node rieng. Report chi duoc tao sau khi
feedback va grammar deu hoan thanh.

```powershell
$fullBody = @{
    question = $question
    answer = $essay
} | ConvertTo-Json

$fullResult = Invoke-RestMethod `
    -Method Post `
    -Uri "$baseUrl/essay_process" `
    -ContentType "application/json" `
    -Body $fullBody

$fullResult | ConvertTo-Json -Depth 20
```

Kiem tra nhanh:

```powershell
$fullResult.session_id
$fullResult.overall_criteria_scores
$fullResult.detailed_feedback
$fullResult.corrected_text
$fullResult.with_errors
$fullResult.fixed_only
```

Full feature pass khi mot response co dong thoi:

- `session_id`;
- overall score va bon criteria scores;
- evaluation feedback va constructive feedback;
- corrected text va hai HTML grammar views.

Neu `MONGO_URI` duoc cau hinh, endpoint nay con luu:

- feedback vao collection `evaluations`;
- grammar result vao collection `grammar_corrections`.

MongoDB la optional. Neu MongoDB khong duoc cau hinh, report van duoc tra ve.
Neu da cau hinh nhung ket noi that bai, xem warning trong terminal Uvicorn.

## 6. Kiem tra LangGraph checkpoint

Sau khi goi bat ky endpoint workflow nao, kiem tra file:

```powershell
Test-Path "backend/data/langgraph_checkpoints.sqlite"
```

Ket qua mong doi:

```text
True
```

Liet ke cac bang va so record trong SQLite:

```powershell
@'
import sqlite3

path = "backend/data/langgraph_checkpoints.sqlite"
connection = sqlite3.connect(path)
tables = [
    row[0]
    for row in connection.execute(
        "SELECT name FROM sqlite_master "
        "WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    )
]

for table in tables:
    count = connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
    print(f"{table}: {count}")

connection.close()
'@ | .\venv\Scripts\python.exe -
```

Checkpoint feature pass khi co file SQLite, co cac bang checkpoint va so record
tang sau khi chay them workflow.

## 7. Test validation va error response

### Thieu essay

```powershell
$invalidBody = @{
    question = "Do you agree?"
    answer = "   "
} | ConvertTo-Json

try {
    Invoke-RestMethod `
        -Method Post `
        -Uri "$baseUrl/evaluate_essay" `
        -ContentType "application/json" `
        -Body $invalidBody
}
catch {
    $_.Exception.Response.StatusCode.value__
}
```

Ket qua mong doi: HTTP `422`.

### Thieu question

```powershell
$invalidBody = @{
    question = ""
    answer = "This is an essay."
} | ConvertTo-Json

try {
    Invoke-RestMethod `
        -Method Post `
        -Uri "$baseUrl/evaluate_essay" `
        -ContentType "application/json" `
        -Body $invalidBody
}
catch {
    $_.Exception.Response.StatusCode.value__
}
```

Ket qua mong doi: HTTP `422`.

## 8. Test truc tiep tung tool

Dung cach nay khi can xac dinh loi nam o tool hay o FastAPI/LangGraph.

### BERT tool

```powershell
@'
from backend.tools.bert_scoring import score_essay

question = "Do you agree that technology improves education?"
essay = "I agree because technology gives students access to useful resources."
print(score_essay(question, essay))
'@ | .\venv\Scripts\python.exe -
```

Ket qua mong doi: mot so band trong khoang `0-9`.

### Gemini feedback tool

```powershell
@'
import asyncio
import json

from backend.tools.feedback_generator import generate_feedback

result = asyncio.run(
    generate_feedback(
        "Do you agree that technology improves education?",
        "I agree because technology gives students access to useful resources.",
        6.0,
    )
)
print(json.dumps(result, indent=2))
'@ | .\venv\Scripts\python.exe -
```

Ket qua mong doi: JSON co `evaluation_feedback`,
`constructive_feedback` va `overall_score`.

### CoEdit T5 grammar tool

```powershell
@'
import asyncio
import json

from backend.tools.grammar_checker import check_grammar

result = asyncio.run(check_grammar("He go to school everyday."))
print(json.dumps(result, indent=2))
'@ | .\venv\Scripts\python.exe -
```

Ket qua mong doi: JSON co `corrected_text`, `with_errors`, `fixed_only`.

### LangGraph orchestrator

```powershell
@'
import asyncio
import json

from backend.agents.orchestrator import IELTSWritingOrchestrator

async def main():
    orchestrator = IELTSWritingOrchestrator()
    try:
        result = await orchestrator.process_essay(
            "Do you agree that technology improves education?",
            "I agree because technology gives students access to useful resources.",
        )
        print(json.dumps(result, indent=2))
    finally:
        await orchestrator.close()

asyncio.run(main())
'@ | .\venv\Scripts\python.exe -
```

Ket qua mong doi giong `/essay_process`.

Khong chay test orchestrator truc tiep dong thoi voi Uvicorn neu ca hai cung
dung mot file checkpoint SQLite.

## 9. Chay automated tests

Bo test mock khong tai BERT/T5 va khong goi Gemini:

```powershell
.\venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -v
```

## OpenTelemetry tracing

OpenTelemetry is disabled by default. To print traces in the backend terminal,
set these values in `backend/.env` before starting Uvicorn:

```env
OTEL_SDK_DISABLED=false
OTEL_TRACES_EXPORTER=console
```

Run any workflow endpoint and look for:

- one `ielts.workflow.*` span;
- child `ielts.node.*` spans;
- a FastAPI HTTP server span.

To disable tracing again:

```env
OTEL_SDK_DISABLED=true
```

For an existing OTLP HTTP endpoint:

```env
OTEL_SDK_DISABLED=false
OTEL_TRACES_EXPORTER=otlp
OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=http://localhost:4318/v1/traces
```

The automated telemetry tests use an in-memory exporter and do not call an
OTLP endpoint:

```powershell
.\venv\Scripts\python.exe -m unittest tests.test_telemetry -v
```

Bo test hien tai kiem tra:

- JSON parser;
- score processor;
- report generator;
- evaluation graph;
- grammar graph;
- combined graph;
- in-memory checkpoint creation;
- SQLite checkpoint persistence after orchestrator shutdown;
- FastAPI health va response contract;
- validation cua request.

Ket qua mong doi:

```text
Ran 17 tests
OK
```

Khong nen co test bi skip sau khi dependencies trong `requirements.txt` da
duoc cai day du.

## 10. Test qua Streamlit

Giu Uvicorn dang chay. Mo terminal thu hai:

```powershell
.\venv\Scripts\python.exe -m streamlit run frontend/app.py
```

Mo:

```text
http://localhost:8501
```

Test lan luot ba man hinh:

1. `Essay Evaluation`: phai hien overall score, bon criteria va feedback.
2. `Grammar Correction`: phai hien Errors & Fixes, Fixed Text va Plain Text.
3. `Combined Evaluation & Correction`: phai co ca score, feedback va grammar.

## 11. Loi thuong gap

### HTTP 500 khi evaluation

Kiem tra:

- `GEMINI_API_KEY` trong `backend/.env`;
- quota cua Gemini API;
- `GEMINI_MODEL`;
- terminal Uvicorn de xem exception cu the.

### BERT khong tai duoc

Kiem tra Internet, Hugging Face cache va `IELTS_HUGGINGFACE_API_KEY` neu
repository yeu cau authentication.

### T5 bi cham hoac het RAM

`grammarly/coedit-large` la model lon. Dong cac process Python khac va thu cau
ngan truoc khi test ca bai.

### Automated test bi skip

Chay:

```powershell
.\run_backend.ps1 -Install
```

Sau do chay lai test bang Python trong `venv`.

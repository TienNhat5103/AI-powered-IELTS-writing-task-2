# IELTS Writing Task 2 Evaluation API – Setup

## Tổng quan
Backend FastAPI chấm IELTS Writing Task 2:
- BERT: tính điểm tổng
- Mistral (Ollama): feedback chi tiết
- Grammar fixer (CoEdit): sửa lỗi, trả về highlight lỗi + bản đã sửa
- MongoDB: lưu phiên đánh giá

## Yêu cầu
- Python 3.10+ (hoặc dùng Docker Compose)
- Docker & Docker Compose (khuyến nghị)
- Ollama (nếu chạy native) và đã pull model Mistral

## Cấu hình môi trường (`.env`)
- `OLLAMA_GEN_ENDPOINT` (vd: http://localhost:11434/api/generate)
- `OLLAMA_CHAT_ENDPOINT` (vd: http://localhost:11434/api/chat)
- `MONGO_URI` (vd: mongodb://admin:password@localhost:27017/ielts_writing_evaluation?authSource=admin)
- `PORT` (mặc định 8000)

## Chạy bằng Docker Compose (đề xuất)
```bash

```
Services: Backend `:8000`, Frontend `:8501`, Ollama `:11434`, MongoDB `:27017`.

## Chạy thủ công (native)
```powershell
# 1) Start Ollama
ollama serve
ollama pull mistral

# 2) Start MongoDB (hoặc dùng service sẵn có)

# 3) Backend
cd backend
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

## API Endpoints (port 8000)

### Health
- `GET /` → { message }
- `GET /health`, `/ready`, `/live`, `/version`

### Đánh giá bài luận
- `POST /evaluate_essay`
  - body: `{ "question": "...", "answer": "..." }`
  - returns: `{ detailed_feedback, overall_criteria_scores }`

### Sửa ngữ pháp
- `POST /grammar_correction`
  - body JSON `{ "answer": "..." }` (hoặc query param `answer`)
  - returns: `corrected_text` (plain), `with_errors` (HTML lỗi+fix), `fixed_only` (HTML đã sửa)

### Kết hợp chấm + sửa
- `POST /essay_process`
  - body: `{ "question": "...", "answer": "..." }`
  - returns: feedback + scores + 3 dạng grammar như trên

## Test nhanh (PowerShell)
```powershell
$body = @{question = "Sample question"; answer = "Sample answer"} | ConvertTo-Json
Invoke-RestMethod -Uri "http://localhost:8000/evaluate_essay" -Method Post -Body $body -ContentType "application/json"
```

## Swagger
- `http://localhost:8000/docs`
- `http://localhost:8000/redoc`

## Troubleshooting
- Ollama lỗi: `docker-compose logs ollama` hoặc `ollama list`
- Model thiếu: `ollama pull mistral`
- Mongo lỗi: kiểm tra `MONGO_URI` và service Mongo đang chạy

## Cấu trúc chính
- backend/: FastAPI, models, grammar fixer
- frontend/: Streamlit UI
- docker-compose.yml: khởi động Ollama + Mongo + Backend + Frontend
  "question": "Some people believe that technology has made our lives more complicated. To what extent do you agree or disagree?",

# IELTS Writing Task 2 Evaluation API - Setup Guide

## Tổng quan

API này tự động chấm và đánh giá bài viết IELTS Writing Task 2 bằng cách kết hợp:
- **BERT model**: Tính điểm tổng (band score)
- **Mistral model** (via Ollama): Tạo feedback chi tiết
- **Google Gemini**: Tạo constructive feedback và sửa lỗi JSON

## Yêu cầu hệ thống

- Python 3.8+
- Ollama đã cài đặt và chạy
- Model Mistral đã được build trong Ollama

## Cài đặt

### 1. Cài đặt dependencies

```powershell
# Kích hoạt virtual environment
& "D:/AI-powered IELTS writing task 2/myvenv/Scripts/Activate.ps1"

# Cài đặt packages (nếu chưa có)
pip install fastapi uvicorn httpx python-dotenv google-generativeai pydantic
```

### 2. Cấu hình environment variables

```powershell
# Copy file template
Copy-Item .env.example .env

# Chỉnh sửa .env với thông tin của bạn
notepad .env
```

Cần điền:
- `GEMINI_API_KEY` và `GEMINI_API_KEY_2`: Lấy từ [Google AI Studio](https://ai.google.dev/)
- `IELTS_HUGGINGFACE_API_KEY`: Token từ [HuggingFace](https://huggingface.co/settings/tokens)
- `BAND_DISCRIPTIOR_FILE`: Đường dẫn tới file mô tả band descriptor

### 3. Build Ollama model

```powershell
cd models
ollama create ielts-mistral -f Modelfile
cd ..
```

### 4. Chạy Ollama server (terminal riêng)

```powershell
ollama serve
```

## Chạy ứng dụng

```powershell
cd backend
python main.py
```

API sẽ chạy tại: `http://localhost:8080`

## API Endpoints

### 1. Health Check
```
GET /
```

### 2. Chỉ tính điểm BERT
```
POST /api/score
```

**Request body:**
```json
{
  "question": "Some people believe that technology has made our lives more complicated. To what extent do you agree or disagree?",
  "essay": "In recent years, technology has become an integral part of our daily lives..."
}
```

**Response:**
```json
{
  "overall_score": 6.5
}
```

### 3. Đánh giá đầy đủ (BERT + Mistral + Gemini)
```
POST /api/feedback
```

**Request body:** (giống `/api/score`)

**Response:**
```json
{
  "user_id": "test_user_id",
  "overall_score": 6.5,
  "evaluation_feedback": {
    "criteria": {
      "task_response": {...},
      "coherence_and_cohesion": {...},
      "lexical_resource": {...},
      "grammatical_range_and_accuracy": {...}
    },
    "feedback": {...}
  },
  "constructive_feedback": {
    "criteria": {...},
    "overall_feedback": {...}
  }
}
```

## Test với curl/PowerShell

```powershell
# Test score endpoint
$body = @{
    question = "Some people believe that technology has made our lives more complicated. To what extent do you agree or disagree?"
    essay = "In recent years, technology has become an integral part of our daily lives. While some argue it complicates things, I believe technology has simplified many aspects of life."
} | ConvertTo-Json

Invoke-RestMethod -Uri "http://localhost:8080/api/score" -Method Post -Body $body -ContentType "application/json"
```

## Swagger Documentation

Sau khi chạy server, truy cập:
- Swagger UI: `http://localhost:8080/docs`
- ReDoc: `http://localhost:8080/redoc`

## Troubleshooting

### Lỗi: "OLLAMA_CHAT_ENDPOINT connection refused"
- Kiểm tra Ollama đang chạy: `ollama list`
- Khởi động: `ollama serve`

### Lỗi: "Model not found"
- Build lại model: `ollama create ielts-mistral -f backend/Modelfile`

### Lỗi: "GEMINI_API_KEY not found"
- Kiểm tra file `.env` đã tạo và điền API keys

## Cấu trúc project

```
backend/
├── main.py                 # FastAPI application
├── mistral_model.py        # Mistral + Gemini integration
├── bert_setup.py           # BERT model setup
├── bert_model.py           # BERT architecture
├── handle_json.py          # JSON parsing utilities
└── Modelfile              # Ollama model definition
```

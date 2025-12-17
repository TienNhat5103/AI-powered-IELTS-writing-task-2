# 🎯 IELTS Writing Task 2 Evaluation & Grammar Correction

An AI-powered application that provides comprehensive feedback on IELTS Writing Task 2 essays, including detailed evaluation based on IELTS criteria and automated grammar correction.

## ✨ Features

- **📊 Essay Evaluation**: Detailed feedback on 4 IELTS criteria:
  - Task Achievement
  - Coherence and Cohesion
  - Lexical Resource (Vocabulary)
  - Grammatical Range and Accuracy

- **✏️ Grammar Correction**: 
  - Annotated essay with error highlighting
  - Suggested corrections
  - Multiple view modes (errors & fixes, fixed text, plain text)

- **🚀 Combined Evaluation & Correction**: Get both evaluation and grammar corrections in one go

- **💾 MongoDB Storage**: All evaluations are saved for future reference

## � Demo Video

Watch the demo video to see the application in action:

📺 [View Demo Videos](https://drive.google.com/file/d/1-QJz7wNcu2qABMJfJ9nNFCIONQXlLHIj/view?usp=sharing)


## 📋 Tech Stack

**Frontend:**
- Streamlit (Web UI)
- Python requests (HTTP client)

**Backend:**
- FastAPI (Web framework)
- BERT (Essay evaluation)
- Mistral 7B (via Ollama) - Feedback generation
- CoEdit T5 - Grammar correction
- MongoDB - Data storage
- Pydantic (Data validation)

**Infrastructure:**
- Docker & Docker Compose
- Ollama (LLM serving)

## 🚀 Quick Start

### Prerequisites
- Python 3.10+
- Docker & Docker Compose (optional, for containerized setup)
- Ollama (for LLM features)

### Option 1: Docker Compose (Recommended)

```bash
# Start all services (Ollama, MongoDB, Backend, Frontend)
docker-compose up -d

# Access:
# Frontend: http://localhost:8501
# Backend: http://localhost:8000
```

### Option 2: Manual Setup

**1. Backend Setup:**
```bash
cd backend
python -m venv venv
source venv/bin/activate  # or `venv\Scripts\activate` on Windows

pip install -r requirements.txt

# Set up environment variables
cp .env.example .env  # Edit with your settings

# Start Ollama (in separate terminal)
ollama serve

# Start Backend
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

**2. Frontend Setup:**
```bash
cd frontend
python -m venv venv
source venv/bin/activate  # or `venv\Scripts\activate` on Windows

pip install -r requirements.txt

# Start Frontend
streamlit run app.py
```

## 📚 API Endpoints

### 1. Essay Evaluation
```
POST /evaluate_essay
Content-Type: application/json

Request:
{
  "question": "Do you agree or disagree with...",
  "answer": "I strongly agree that..."
}

Response:
{
  "overall_score": 6.5,
  "evaluation_feedback": {...},
  "constructive_feedback": {...}
}
```

### 2. Grammar Correction
```
POST /grammar_correction?answer=Your+essay+text+here

Response:
{
  "corrected_text": "Corrected essay...",
  "with_errors": "<span>error</span> <span>fix</span>...",
  "fixed_only": "Corrected essay..."
}
```

### 3. Combined Evaluation & Correction
```
POST /essay_process
Content-Type: application/json

Request:
{
  "question": "Do you agree or disagree with...",
  "answer": "I strongly agree that..."
}

Response:
{
  "session_id": "uuid",
  "overall_score": 6.5,
  "evaluation_feedback": {...},
  "constructive_feedback": {...},
  "corrected_text": "...",
  "with_errors": "...",
  "fixed_only": "..."
}
```

### Health Check Endpoints
```
GET /health         - Health check
GET /ready          - Readiness check
GET /live           - Liveness check
GET /version        - API version
```

## 📁 Project Structure

```
.
├── frontend/
│   ├── app.py                 # Streamlit application
│   ├── requirements.txt
│   └── Dockerfile
├── backend/
│   ├── main.py               # FastAPI application
│   ├── bert_setup.py         # BERT model setup
│   ├── bert_model.py         # BERT evaluation logic
│   ├── mistral_model.py      # Mistral feedback generation
│   ├── grammar.py            # Grammar correction using T5
│   ├── caculate_score.py     # Score calculation & extraction
│   ├── handle_json.py        # JSON handling utilities
│   ├── requirements.txt
│   ├── Dockerfile
│   └── .env.example
├── models/
│   └── mistral-7b-instruct-v0.3.Q4_K_M.gguf  # Mistral model file
├── docker-compose.yml
├── API_SETUP.md               # API documentation
├── DOCKER_SETUP.md            # Docker setup guide
└── README.md
```

## 🔧 Configuration

Create a `.env` file in the backend directory:

```env
# Ollama endpoints
OLLAMA_GEN_ENDPOINT=http://localhost:11434/api/generate
OLLAMA_CHAT_ENDPOINT=http://localhost:11434/api/chat

# MongoDB
MONGO_URI=mongodb://localhost:27017

# Server
PORT=8000
```

## 📊 Evaluation Criteria

### Task Achievement
- Addresses the question completely
- Provides relevant main points
- Develops ideas with supporting details

### Coherence and Cohesion
- Logical organization
- Clear paragraphing
- Effective use of linking words

### Lexical Resource
- Range of vocabulary
- Appropriate word choice
- Accurate spelling and usage

### Grammatical Range and Accuracy
- Variety of sentence structures
- Correct grammar
- Correct punctuation

## 🎯 Response Format

### Overall Score
- Ranges from 0-9
- Based on average of 4 criteria (IELTS standard)
- Rounded to nearest 0.5

### Feedback Components
1. **Strengths**: What the essay does well
2. **Evaluation**: Specific assessment feedback
3. **Areas for Improvement**: What needs enhancement

## 🐛 Troubleshooting

### Backend Connection Error
- Ensure backend is running: `uvicorn main:app --reload`
- Check if port 8000 is not in use
- Verify BACKEND_URL in frontend/app.py

### Ollama Connection Error
- Start Ollama: `ollama serve`
- Ensure Mistral model is loaded: `ollama pull mistral:latest`
- Check Ollama endpoints in .env

### MongoDB Connection Error
- Ensure MongoDB is running
- Verify MONGO_URI in .env
- Default: `mongodb://localhost:27017`

### Timeout Errors
- Increase timeout values in frontend/app.py
- Current settings: 600s for evaluation, 300s for grammar, 900s for combined
- Ensure backend has sufficient resources

## 📝 Example Usage

1. **Access the app**: Open http://localhost:8501
2. **Select evaluation type**: Choose from sidebar
3. **Enter essay question and answer**
4. **Click evaluate button**
5. **View results**: See overall score, criteria breakdown, and detailed feedback

## 🔐 Security Considerations

- Backend runs with CORS enabled for localhost
- MongoDB access should be restricted
- API endpoints should be authenticated in production
- Input validation is implemented for all endpoints

## 📈 Performance

- Average evaluation time: 2-5 minutes per essay
- Grammar correction time: 30-60 seconds
- Combined evaluation: 3-6 minutes

Times depend on:
- Server specifications
- Essay length
- Model load time
- Network latency

## 🛠️ Development

### Adding New Features

1. **Backend**: Add endpoint in main.py
2. **Frontend**: Add UI component in app.py
3. **Update API_SETUP.md**: Document new endpoint
4. **Test**: Use curl or Postman to test API

### Running Tests
```bash
# Backend tests (if implemented)
pytest backend/

# Frontend debug mode
streamlit run frontend/app.py --logger.level=debug
```

## 📄 License

This project is provided as-is for educational purposes.

## 👥 Support

For issues or questions:
1. Check API_SETUP.md for API documentation
2. Check DOCKER_SETUP.md for Docker setup
3. Review error messages in backend logs
4. Verify all services are running

## 🎓 Educational Notes

This tool is designed to help students improve their IELTS writing through:
- Immediate feedback on essay structure and quality
- Specific suggestions for improvement
- Grammar error identification and correction
- Understanding of IELTS evaluation criteria

**Note**: This tool provides guidance only. Official IELTS evaluation should be conducted by certified IELTS examiners.

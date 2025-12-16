# IELTS Writing Task 2 - Docker Setup

## Quick Start

### Option 1: Run with Docker Compose (Recommended)

Start all services (Ollama, MongoDB, Backend, Frontend) with one command:

```bash
docker-compose up -d
```

Services will be available at:
- **Backend API**: http://localhost:8000
- **Frontend**: http://localhost:8501
- **Ollama**: http://localhost:11434
- **MongoDB**: mongodb://admin:password@localhost:27017

### Option 2: Run Containers Separately

#### Start Ollama
```bash
docker run -d -p 11434:11434 --name ollama ollama/ollama
```

#### Pull and run a model
```bash
docker exec ollama ollama pull mistral
```

#### Start MongoDB
```bash
docker run -d -p 27017:27017 \
  -e MONGO_INITDB_ROOT_USERNAME=admin \
  -e MONGO_INITDB_ROOT_PASSWORD=password \
  --name mongodb mongo
```

#### Build and run Backend
```bash
cd backend
docker build -t ielts-backend .
docker run -d -p 8000:8000 \
  -e OLLAMA_GEN_ENDPOINT=http://ollama:11434/api/generate \
  -e OLLAMA_CHAT_ENDPOINT=http://ollama:11434/api/chat \
  -e MONGO_URI=mongodb://admin:password@mongodb:27017/ielts_writing_evaluation?authSource=admin \
  --link ollama \
  --link mongodb \
  --name backend ielts-backend
```

#### Build and run Frontend
```bash
cd frontend
docker build -t ielts-frontend .
docker run -d -p 8501:8501 \
  -e BACKEND_URL=http://backend:8000 \
  --link backend \
  --name frontend ielts-frontend
```

## Environment Variables

### Backend
- `OLLAMA_GEN_ENDPOINT`: Ollama generate endpoint (default: http://ollama:11434/api/generate)
- `OLLAMA_CHAT_ENDPOINT`: Ollama chat endpoint (default: http://ollama:11434/api/chat)
- `MONGO_URI`: MongoDB connection string
- `PORT`: Backend port (default: 8000)

### Frontend
- `BACKEND_URL`: Backend API URL (default: http://localhost:8000)

## Stop Services

```bash
# Stop all services
docker-compose down

# Stop and remove volumes
docker-compose down -v
```

## View Logs

```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f backend
docker-compose logs -f ollama
docker-compose logs -f mongodb
```

## Notes

1. **First Run**: Ollama will take time to download and run the model. Wait for health check to pass.
2. **GPU Support**: To enable GPU in Ollama, modify the docker-compose.yml:
   ```yaml
   ollama:
     ...
     runtime: nvidia
     environment:
       - NVIDIA_VISIBLE_DEVICES=all
   ```
3. **Persistence**: Data is stored in named volumes:
   - `ollama_data`: Ollama models
   - `mongodb_data`: MongoDB database

## Troubleshooting

### Ollama not responding
```bash
docker-compose logs ollama
# Check if model is loaded
docker-compose exec ollama ollama list
```

### Backend can't connect to Ollama
Make sure both are on the same network:
```bash
docker network ls
docker network inspect ielts-network
```

### MongoDB connection error
Check credentials in docker-compose.yml and .env file

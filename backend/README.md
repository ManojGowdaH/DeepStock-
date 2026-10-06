# Backend

This service runs the FastAPI API for the DeepStock AI project.

## Run locally

```powershell
cd "D:\Deep Learning\deepstock-ai"
.\.venv\Scripts\Activate.ps1
cd backend
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

## Docker deploy

```powershell
docker build -t deepstock-backend .
docker run --rm -p 8000:8000 deepstock-backend
```

## Health check

```text
http://localhost:8000/health
```

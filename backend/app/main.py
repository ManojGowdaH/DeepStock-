import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.api.routes import router as api_router
from app.database.db import initialize_db, seed_demo_stocks
from app.core.config import CORS_ALLOW_ORIGINS

@asynccontextmanager
async def lifespan(app: FastAPI):
    initialize_db()
    seed_demo_stocks()
    yield


app = FastAPI(
    title="DeepStock AI",
    description="Educational research system for evaluating deep learning approaches to financial time-series analysis.",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(CORS_ALLOW_ORIGINS),
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-API-Key"],
)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        return response


app.add_middleware(SecurityHeadersMiddleware)


app.include_router(api_router, prefix="/api")


@app.get("/health")
def health():
    return {"status": "ok", "message": "DeepStock AI backend is running."}


@app.get("/")
def root():
    return {
        "project": "DeepStock AI",
        "message": "This project is an educational research system for evaluating deep learning approaches to historical financial time-series analysis. Model predictions are experimental and must not be interpreted as financial advice.",
    }

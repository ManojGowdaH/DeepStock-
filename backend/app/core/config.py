import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[3] / ".env", override=True)

BASE_DIR = Path(__file__).resolve().parents[3]
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./deepstock_ai.db")
DATA_PROVIDER = os.getenv("DATA_PROVIDER", "csv")
MODEL_STORAGE_PATH = Path(os.getenv("MODEL_STORAGE_PATH", str(BASE_DIR / "models")))
API_PORT = int(os.getenv("API_PORT", "8000"))
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")
CORS_ALLOW_ORIGINS = tuple(
    origin.strip()
    for origin in os.getenv(
        "CORS_ALLOW_ORIGINS",
        f"{FRONTEND_URL},http://127.0.0.1:3000",
    ).split(",")
    if origin.strip()
)
MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_BYTES", str(10 * 1024 * 1024)))


MODEL_DIRS = {
    "ann": MODEL_STORAGE_PATH / "ann",
    "ffnn": MODEL_STORAGE_PATH / "ffnn",
    "cnn": MODEL_STORAGE_PATH / "cnn",
    "rnn": MODEL_STORAGE_PATH / "rnn",
    "lstm": MODEL_STORAGE_PATH / "lstm",
    "transformer": MODEL_STORAGE_PATH / "transformer",
}

for path in MODEL_DIRS.values():
    path.mkdir(parents=True, exist_ok=True)

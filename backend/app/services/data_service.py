import io
import json
import os
import re
import sqlite3
import sys
import tempfile
from pathlib import Path
from typing import List

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.database.db import get_connection
from app.core.config import BASE_DIR, MAX_UPLOAD_BYTES
from ml.features.technical_indicators import compute_technical_features, generate_sequences

RAW_DIR = BASE_DIR / "data" / "raw"
PROCESSED_DIR = BASE_DIR / "data" / "processed"
RAW_DIR.mkdir(parents=True, exist_ok=True)
PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
SYMBOL_PATTERN = re.compile(r"^[A-Z0-9][A-Z0-9&._-]{0,29}$")
MAX_UPLOAD_ROWS = 10000


def normalize_symbol(symbol: str) -> str:
    normalized = str(symbol).strip().upper()
    if not SYMBOL_PATTERN.fullmatch(normalized) or ".." in normalized:
        raise ValueError("Invalid stock symbol. Use letters, numbers, dots, hyphens, or ampersands only.")
    return normalized


def ensure_demo_data():
    if not RAW_DIR.exists():
        RAW_DIR.mkdir(parents=True, exist_ok=True)
    files = list(RAW_DIR.glob("*.csv"))
    if files:
        return

    from scripts.generate_demo_data import generate_demo_data

    generate_demo_data()


def load_symbol_history(symbol: str) -> pd.DataFrame:
    symbol = normalize_symbol(symbol)
    ensure_demo_data()
    raw_root = RAW_DIR.resolve()
    symbol_file = (raw_root / f"{symbol}.csv").resolve()
    if symbol_file.parent != raw_root:
        raise ValueError("Invalid stock symbol path.")
    if not symbol_file.exists():
        raise FileNotFoundError(f"No historical data found for {symbol}")
    df = pd.read_csv(symbol_file, parse_dates=["Date"])
    df = df.rename(columns={"Date": "date", "Open": "open", "High": "high", "Low": "low", "Close": "close", "Volume": "volume"})
    df = df[["date", "open", "high", "low", "close", "volume"]]
    return df.sort_values("date").reset_index(drop=True)


def save_uploaded_csv(symbol: str, uploaded_file) -> pd.DataFrame:
    symbol = normalize_symbol(symbol)
    ensure_demo_data()
    file_bytes = uploaded_file.file.read(MAX_UPLOAD_BYTES + 1)
    if len(file_bytes) > MAX_UPLOAD_BYTES:
        raise ValueError(f"CSV upload must be no larger than {MAX_UPLOAD_BYTES // (1024 * 1024)} MB.")
    if not file_bytes:
        raise ValueError("The uploaded CSV is empty.")

    try:
        source = pd.read_csv(io.BytesIO(file_bytes))
    except (pd.errors.ParserError, pd.errors.EmptyDataError, UnicodeDecodeError) as exc:
        raise ValueError("The uploaded file is not a readable CSV.") from exc
    columns = {str(column).strip().casefold(): column for column in source.columns}
    required = {"date", "open", "high", "low", "close", "volume"}
    if not required.issubset(columns):
        raise ValueError("CSV must include Date, Open, High, Low, Close, and Volume columns.")
    if not 2 <= len(source) <= MAX_UPLOAD_ROWS:
        raise ValueError(f"CSV must contain between 2 and {MAX_UPLOAD_ROWS} data rows.")

    df = source[[columns[field] for field in ("date", "open", "high", "low", "close", "volume")]].copy()
    df.columns = ["date", "open", "high", "low", "close", "volume"]
    df["date"] = pd.to_datetime(df["date"], errors="coerce", utc=True)
    for field in ("open", "high", "low", "close", "volume"):
        df[field] = pd.to_numeric(df[field], errors="coerce")
    numeric_values = df[["open", "high", "low", "close", "volume"]].to_numpy(dtype=float)
    if df.isna().any().any() or not np.isfinite(numeric_values).all():
        raise ValueError("CSV dates and OHLCV values must all be valid finite numbers.")
    if (df[["open", "high", "low", "close"]] <= 0).any().any() or (df["volume"] < 0).any():
        raise ValueError("Prices must be positive and volume cannot be negative.")
    if (df["high"] < df[["open", "close", "low"]].max(axis=1)).any() or (df["low"] > df[["open", "close", "high"]].min(axis=1)).any():
        raise ValueError("Each candle's High and Low must contain its Open and Close values.")
    df = df.sort_values("date").reset_index(drop=True)

    raw_root = RAW_DIR.resolve()
    save_path = (raw_root / f"{symbol}.csv").resolve()
    if save_path.parent != raw_root:
        raise ValueError("Invalid stock symbol path.")
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="", dir=raw_root, suffix=".tmp", delete=False) as temporary:
            temp_path = Path(temporary.name)
            output = df.rename(columns={"date": "Date", "open": "Open", "high": "High", "low": "Low", "close": "Close", "volume": "Volume"})
            output["Date"] = output["Date"].dt.strftime("%Y-%m-%d")
            output.to_csv(temporary, index=False)
        os.replace(temp_path, save_path)
    finally:
        if temp_path is not None and temp_path.exists():
            temp_path.unlink()
    return load_symbol_history(symbol)


def persist_stock_rows(symbol: str, df: pd.DataFrame):
    conn = get_connection()
    try:
        for _, row in df.iterrows():
            conn.execute(
                "INSERT OR IGNORE INTO historical_prices (symbol, date, open, high, low, close, volume) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    symbol,
                    row["date"].strftime("%Y-%m-%d"),
                    float(row["open"]),
                    float(row["high"]),
                    float(row["low"]),
                    float(row["close"]),
                    int(row["volume"]),
                ),
            )
        conn.commit()
    finally:
        conn.close()


def get_available_symbols() -> List[str]:
    ensure_demo_data()
    raw_files = sorted(RAW_DIR.glob("*.csv"))
    return [path.stem for path in raw_files]


def get_feature_frame(symbol: str) -> pd.DataFrame:
    history = load_symbol_history(symbol)
    features = compute_technical_features(history)
    return features


def get_feature_rows(symbol: str) -> List[dict]:
    df = get_feature_frame(symbol)
    return df.tail(30).to_dict(orient="records")


def save_feature_frame(symbol: str, df: pd.DataFrame):
    out_path = PROCESSED_DIR / f"{symbol}_features.csv"
    df.to_csv(out_path, index=False)


def get_model_summaries():
    return [
        {"name": "ANN", "category": "baseline"},
        {"name": "FFNN", "category": "feedforward"},
        {"name": "CNN", "category": "temporal"},
        {"name": "RNN", "category": "sequential"},
        {"name": "LSTM", "category": "sequential"},
        {"name": "Transformer", "category": "attention"},
    ]

import json
import logging
import secrets
import sqlite3
from pathlib import Path
from typing import List, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, UploadFile, File, Query

from app.database.db import get_connection
from app.services.data_service import get_available_symbols, load_symbol_history, get_feature_frame, save_uploaded_csv, persist_stock_rows, get_feature_rows, normalize_symbol
from app.services.model_service import train_model, save_training_artifacts
from app.services.live_data_service import fetch_live_market_data, fetch_stock_analysis
from app.services.indian_stocks_service import search_indian_stocks
from app.schemas.models import TrainRequest, PredictionRequest
from app.core.config import API_WRITE_KEY

router = APIRouter()
logger = logging.getLogger(__name__)


def require_write_access(x_api_key: str | None = Header(default=None)) -> None:
    if not API_WRITE_KEY:
        raise HTTPException(status_code=503, detail="Write endpoints are disabled until API_WRITE_KEY is configured.")
    if x_api_key is None or not secrets.compare_digest(x_api_key, API_WRITE_KEY):
        raise HTTPException(status_code=401, detail="A valid X-API-Key header is required.")


@router.get("/stocks")
def list_stocks(
    search: str = Query("", min_length=0, max_length=100),
    limit: int = Query(12, ge=1, le=50),
    exact: bool = Query(False, description="Match a complete ticker symbol"),
):
    return search_indian_stocks(search, limit, exact=exact)


@router.get("/stocks/{symbol}/history")
def stock_history(symbol: str):
    try:
        symbol = normalize_symbol(symbol)
        df = load_symbol_history(symbol)
        return {"symbol": symbol, "rows": df.tail(30).to_dict(orient="records")}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/stocks/{symbol}/live")
def live_stock_data(
    symbol: str,
    interval: str = Query("1m", description="Intraday candle interval"),
    period: str = Query("1d", description="Intraday history period"),
):
    try:
        symbol = normalize_symbol(symbol)
        return fetch_live_market_data(symbol, interval, period)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/stocks/{symbol}/analysis")
def stock_analysis(
    symbol: str,
    period: str = Query("1y", description="Daily history range"),
):
    try:
        symbol = normalize_symbol(symbol)
        stock_results = search_indian_stocks(symbol, 1, exact=True)
        stock = stock_results["symbols"][0] if stock_results["symbols"] else None
        company_name = stock["company_name"] if stock else symbol.upper()
        return fetch_stock_analysis(symbol, company_name, period)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/stocks/{symbol}/features")
def stock_features(symbol: str):
    try:
        symbol = normalize_symbol(symbol)
        df = get_feature_frame(symbol)
        return {"symbol": symbol, "rows": df.tail(30).to_dict(orient="records")}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception:
        logger.exception("Stock feature generation failed")
        raise HTTPException(status_code=500, detail="Could not generate stock features.") from None


@router.post("/data/upload")
def upload_csv(
    symbol: str = "",
    file: UploadFile = File(...),
    _authorized: None = Depends(require_write_access),
):
    if not symbol:
        symbol = (file.filename or "UPLOAD").split(".")[0].upper()
    try:
        symbol = normalize_symbol(symbol)
        df = save_uploaded_csv(symbol, file)
        persist_stock_rows(symbol, df)
        return {"status": "success", "symbol": symbol, "rows": len(df)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception:
        logger.exception("Stock CSV upload failed")
        raise HTTPException(status_code=500, detail="The stock CSV could not be saved.") from None


@router.get("/models")
def list_models():
    from app.services.data_service import get_model_summaries

    return {"models": get_model_summaries()}


@router.post("/train/{model_name}")
def train_model_endpoint(
    model_name: Literal["ann", "ffnn", "cnn", "rnn", "lstm", "transformer"],
    payload: TrainRequest,
    _authorized: None = Depends(require_write_access),
):
    try:
        if payload.model != model_name:
            raise HTTPException(status_code=422, detail="The URL model and request model must match.")
        symbol = normalize_symbol(payload.symbol)
        payload_data = payload.model_dump()
        result = train_model(symbol, model_name, payload_data)
        save_training_artifacts(model_name, result)
        response_payload = dict(result)
        response_payload.pop("model_state", None)

        conn = get_connection()
        try:
            conn.execute(
                "INSERT INTO experiments (model_name, symbol, task, lookback, optimizer, learning_rate, batch_size, epochs, training_accuracy, validation_accuracy, test_accuracy, precision, recall, f1, mae, rmse, training_time, parameter_count) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    model_name,
                    symbol,
                    "classification",
                    payload_data["lookback"],
                    payload_data["optimizer"],
                    payload_data["learning_rate"],
                    payload_data["batch_size"],
                    payload_data["epochs"],
                    result.get("training_accuracy"),
                    result.get("validation_accuracy"),
                    result.get("test_accuracy"),
                    result.get("precision"),
                    result.get("recall"),
                    result.get("f1"),
                    None,
                    None,
                    result.get("training_time"),
                    result.get("parameter_count"),
                ),
            )
            conn.commit()
        finally:
            conn.close()
        return response_payload
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception:
        logger.exception("Model training failed")
        raise HTTPException(status_code=500, detail="Model training failed. Check the server logs.") from None


@router.get("/experiments")
def experiments():
    conn = get_connection()
    rows = conn.execute("SELECT * FROM experiments ORDER BY id DESC LIMIT 20").fetchall()
    conn.close()
    return {"experiments": [dict(row) for row in rows]}


@router.post("/predict")
def predict(payload: PredictionRequest, _authorized: None = Depends(require_write_access)):
    model_name = payload.model
    lookback = payload.lookback
    try:
        symbol = normalize_symbol(payload.symbol)
        result = train_model(symbol, model_name, {"lookback": lookback, "epochs": 3, "optimizer": "adam"})
        prediction = {
            "symbol": symbol,
            "model_name": model_name,
            "predicted_direction": 1 if result["accuracy"] >= 0.5 else 0,
            "probability_up": round(float(result["accuracy"]), 4),
            "probability_down": round(1.0 - float(result["accuracy"]), 4),
            "predicted_return": round(float(result["accuracy"] - 0.5), 4),
        }
        return prediction
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception:
        logger.exception("Prediction evaluation failed")
        raise HTTPException(status_code=500, detail="Prediction evaluation failed. Check the server logs.") from None


@router.get("/predictions/{symbol}")
def predictions(symbol: str):
    try:
        symbol = normalize_symbol(symbol)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    conn = get_connection()
    rows = conn.execute("SELECT * FROM predictions WHERE symbol = ? ORDER BY id DESC LIMIT 10", (symbol.upper(),)).fetchall()
    conn.close()
    return {"symbol": symbol.upper(), "predictions": [dict(row) for row in rows]}


@router.get("/metrics/{experiment_id}")
def metrics(experiment_id: int):
    conn = get_connection()
    row = conn.execute("SELECT * FROM experiments WHERE id = ?", (experiment_id,)).fetchone()
    conn.close()
    if row is None:
        raise HTTPException(status_code=404, detail="Experiment not found")
    return dict(row)

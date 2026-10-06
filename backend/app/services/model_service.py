import json
import os
import sys
import time
from pathlib import Path
from typing import Dict, Any

import numpy as np
import pandas as pd
import torch
from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score, mean_absolute_error, mean_squared_error, r2_score

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.core.config import BASE_DIR, MODEL_DIRS
from ml.features.technical_indicators import compute_technical_features, generate_sequences
from ml.models.ann import ANNClassifier
from ml.models.cnn import TemporalCNN
from ml.models.rnn import SimpleRNNClassifier
from ml.models.lstm import LSTMClassifier
from ml.models.transformer import TemporalTransformer
from ml.training.training import train_and_evaluate


MODEL_REGISTRY = {
    "ann": ANNClassifier,
    "ffnn": ANNClassifier,
    "cnn": TemporalCNN,
    "rnn": SimpleRNNClassifier,
    "lstm": LSTMClassifier,
    "transformer": TemporalTransformer,
}


def _ensure_seed(seed: int = 42):
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def _training_config(model_name: str, request: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "symbol": request.get("symbol", "TCS"),
        "model_name": model_name,
        "lookback": int(request.get("lookback", 30)),
        "optimizer": request.get("optimizer", "adam"),
        "learning_rate": float(request.get("learning_rate", 0.001)),
        "batch_size": int(request.get("batch_size", 32)),
        "epochs": int(request.get("epochs", 10)),
        "hidden_units": int(request.get("hidden_units", 64)),
        "dropout": float(request.get("dropout", 0.1)),
        "device": "cuda" if torch.cuda.is_available() else "cpu",
    }


def train_model(symbol: str, model_name: str, request: Dict[str, Any]):
    _ensure_seed()
    history = pd.read_csv(BASE_DIR / "data" / "raw" / f"{symbol}.csv")
    history = history.rename(columns={"Date": "date", "Open": "open", "High": "high", "Low": "low", "Close": "close", "Volume": "volume"})
    history = history[["date", "open", "high", "low", "close", "volume"]]
    features = compute_technical_features(history)
    features = features.dropna().reset_index(drop=True)
    if len(features) < 60:
        raise ValueError("Dataset is too small for a meaningful training run.")

    X, y = generate_sequences(features, lookback=int(request.get("lookback", 30)), threshold=0.0)
    n = len(X)
    split_train = int(n * 0.7)
    split_val = int(n * 0.85)

    X_train, y_train = X[:split_train], y[:split_train]
    X_val, y_val = X[split_train:split_val], y[split_train:split_val]
    X_test, y_test = X[split_val:], y[split_val:]

    if model_name not in MODEL_REGISTRY:
        raise ValueError(f"Unsupported model: {model_name}")

    start_time = time.time()
    result = train_and_evaluate(
        model_name=model_name,
        X_train=X_train,
        y_train=y_train,
        X_val=X_val,
        y_val=y_val,
        X_test=X_test,
        y_test=y_test,
        config=_training_config(model_name, request),
    )
    elapsed = time.time() - start_time
    result["training_time"] = round(elapsed, 2)
    result["parameter_count"] = int(result.get("parameter_count", 0))
    result["model_name"] = model_name
    result["symbol"] = symbol
    result["task"] = "classification"
    return result


def save_training_artifacts(model_name: str, result: Dict[str, Any]):
    model_dir = MODEL_DIRS.get(model_name, BASE_DIR / "models" / model_name)
    model_dir.mkdir(parents=True, exist_ok=True)
    model_state = result.get("model_state")
    serializable_result = dict(result)
    serializable_result.pop("model_state", None)
    payload = {
        "model_name": model_name,
        "metrics": serializable_result,
    }
    with open(model_dir / "metadata.json", "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    if model_state is not None:
        path = model_dir / "model.pt"
        torch.save(model_state, path)

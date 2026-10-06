from typing import Dict, Any

import numpy as np
import torch
from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score, mean_absolute_error, mean_squared_error, r2_score

from ml.models.ann import ANNClassifier
from ml.models.cnn import TemporalCNN
from ml.models.rnn import SimpleRNNClassifier
from ml.models.lstm import LSTMClassifier
from ml.models.transformer import TemporalTransformer


def _to_tensor(x, dtype=torch.float32):
    return torch.tensor(x, dtype=dtype)


def train_and_evaluate(model_name: str, X_train, y_train, X_val, y_val, X_test, y_test, config: Dict[str, Any]):
    device = torch.device(config.get("device", "cpu"))

    if model_name in {"ann", "ffnn"}:
        model = ANNClassifier(
            input_dim=X_train.shape[-1],
            hidden_units=config.get("hidden_units", 64),
            output_dim=1,
            dropout=config.get("dropout", 0.1),
            device=device,
        )
    elif model_name == "cnn":
        model = TemporalCNN(
            input_dim=X_train.shape[-1],
            hidden_channels=config.get("hidden_units", 32),
            device=device,
        )
    elif model_name == "rnn":
        model = SimpleRNNClassifier(
            input_dim=X_train.shape[-1],
            hidden_size=config.get("hidden_units", 32),
            device=device,
        )
    elif model_name == "lstm":
        model = LSTMClassifier(
            input_dim=X_train.shape[-1],
            hidden_size=config.get("hidden_units", 32),
            num_layers=2,
            device=device,
        )
    elif model_name == "transformer":
        model = TemporalTransformer(
            input_dim=X_train.shape[-1],
            d_model=min(32, max(8, config.get("hidden_units", 32))),
            nhead=4,
            num_layers=2,
            device=device,
        )
    else:
        raise ValueError(f"Unsupported model name: {model_name}")

    optimizer_name = config.get("optimizer", "adam").lower()
    optimizer = model.get_optimizer(optimizer_name, lr=config.get("learning_rate", 0.001))

    criterion = torch.nn.BCELoss() if model_name in {"ann", "ffnn", "cnn", "rnn", "lstm", "transformer"} else torch.nn.MSELoss()

    train_x = _to_tensor(X_train)
    train_y = _to_tensor(y_train.reshape(-1, 1), dtype=torch.float32)
    val_x = _to_tensor(X_val)
    val_y = _to_tensor(y_val.reshape(-1, 1), dtype=torch.float32)
    test_x = _to_tensor(X_test)
    test_y = _to_tensor(y_test.reshape(-1, 1), dtype=torch.float32)

    for epoch in range(int(config.get("epochs", 10))):
        model.train()
        optimizer.zero_grad()
        logits = model(train_x)
        loss = criterion(logits, train_y)
        loss.backward()
        optimizer.step()

    model.eval()
    with torch.no_grad():
        val_probs = model(val_x).cpu().numpy().reshape(-1)
        test_probs = model(test_x).cpu().numpy().reshape(-1)
        val_pred = (val_probs >= 0.5).astype(int)
        test_pred = (test_probs >= 0.5).astype(int)

    val_acc = accuracy_score(val_y.cpu().numpy().reshape(-1), val_pred)
    test_acc = accuracy_score(test_y.cpu().numpy().reshape(-1), test_pred)
    precision = precision_score(test_y.cpu().numpy().reshape(-1), test_pred, zero_division=0)
    recall = recall_score(test_y.cpu().numpy().reshape(-1), test_pred, zero_division=0)
    f1 = f1_score(test_y.cpu().numpy().reshape(-1), test_pred, zero_division=0)

    metrics = {
        "accuracy": round(float(test_acc), 4),
        "precision": round(float(precision), 4),
        "recall": round(float(recall), 4),
        "f1": round(float(f1), 4),
        "validation_accuracy": round(float(val_acc), 4),
        "test_accuracy": round(float(test_acc), 4),
        "training_accuracy": round(float(val_acc), 4),
        "parameter_count": sum(p.numel() for p in model.parameters()),
        "model_state": model.state_dict(),
    }
    return metrics

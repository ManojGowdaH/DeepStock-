import sys
from pathlib import Path

import pandas as pd
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'backend'))

from app.main import app
from ml.features.technical_indicators import compute_technical_features, generate_sequences

client = TestClient(app)


def build_demo_frame(rows=120):
    dates = pd.date_range('2020-01-01', periods=rows, freq='B')
    base = 100.0
    close = []
    value = base
    for i in range(rows):
        value = value * (1 + (i % 9) / 1000 - 0.002)
        close.append(round(value, 2))

    data = {
        'date': dates,
        'open': [round(v * 0.998, 2) for v in close],
        'high': [round(v * 1.01, 2) for v in close],
        'low': [round(v * 0.99, 2) for v in close],
        'close': close,
        'volume': [1000 + i * 10 for i in range(rows)],
    }
    return pd.DataFrame(data)


def test_feature_generation_and_sequence_shape():
    df = build_demo_frame(150)
    features = compute_technical_features(df)
    X, y = generate_sequences(features, lookback=10, threshold=0.0)

    assert 'daily_return' in features.columns
    assert 'next_day_direction' in features.columns
    assert X.shape[1] == 10
    assert y.shape[0] == X.shape[0]
    assert len(y) > 0


def test_application_health_and_stock_listing():
    health_response = client.get('/health')
    assert health_response.status_code == 200
    assert health_response.json()['status'] == 'ok'

    stocks_response = client.get('/api/stocks')
    assert stocks_response.status_code == 200
    data = stocks_response.json()
    assert 'symbols' in data
    assert len(data['symbols']) > 0

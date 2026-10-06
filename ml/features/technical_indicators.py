import numpy as np
import pandas as pd


def compute_technical_features(df: pd.DataFrame) -> pd.DataFrame:
    """Build a feature table using only historical information up to time t."""
    working = df.copy().sort_values("date").reset_index(drop=True)
    if "close" not in working.columns:
        raise ValueError("close column is required")

    working["daily_return"] = working["close"].pct_change().fillna(0.0)
    working["log_return"] = np.log(working["close"]).diff().fillna(0.0)
    working["price_change"] = working["close"].diff().fillna(0.0)
    working["volume_change"] = working["volume"].pct_change().fillna(0.0)

    for window in [10, 20, 50]:
        working[f"sma_{window}"] = working["close"].rolling(window, min_periods=1).mean()

    for window in [10, 20]:
        working[f"ema_{window}"] = working["close"].ewm(span=window, adjust=False).mean()

    delta = working["close"].diff()
    gain = delta.clip(lower=0).rolling(window=14, min_periods=1).mean()
    loss = (-delta.clip(upper=0)).rolling(window=14, min_periods=1).mean()
    rs = gain / loss.replace(0, np.nan)
    working["rsi"] = 100 - (100 / (1 + rs)).fillna(50)

    short_ema = working["close"].ewm(span=12, adjust=False).mean()
    long_ema = working["close"].ewm(span=26, adjust=False).mean()
    working["macd"] = short_ema - long_ema
    working["macd_signal"] = working["macd"].ewm(span=9, adjust=False).mean()

    rolling_mean = working["close"].rolling(window=20, min_periods=1).mean()
    rolling_std = working["close"].rolling(window=20, min_periods=1).std().fillna(0)
    working["bollinger_upper"] = rolling_mean + (2 * rolling_std)
    working["bollinger_lower"] = rolling_mean - (2 * rolling_std)
    working["bollinger_width"] = working["bollinger_upper"] - working["bollinger_lower"]

    working["rolling_volatility"] = working["daily_return"].rolling(window=20, min_periods=1).std().fillna(0)
    working["high_low_ratio"] = (working["high"] / working["low"]).replace([np.inf], np.nan).fillna(1.0)
    working["open_close_ratio"] = (working["open"] / working["close"]).replace([np.inf], np.nan).fillna(1.0)

    working["next_day_return"] = working["close"].shift(-1) / working["close"] - 1
    working["next_day_direction"] = (working["next_day_return"] > 0).astype(int)
    working = working.dropna().reset_index(drop=True)
    return working


def generate_sequences(df: pd.DataFrame, lookback: int = 30, threshold: float = 0.0):
    feature_cols = [
        "daily_return",
        "log_return",
        "price_change",
        "volume_change",
        "sma_10",
        "sma_20",
        "sma_50",
        "ema_10",
        "ema_20",
        "rsi",
        "macd",
        "macd_signal",
        "bollinger_upper",
        "bollinger_lower",
        "bollinger_width",
        "rolling_volatility",
        "high_low_ratio",
        "open_close_ratio",
    ]
    feature_matrix = df[feature_cols].astype(float).values
    target = (df["next_day_return"] > threshold).astype(int).values

    X, y = [], []
    for i in range(lookback, len(feature_matrix)):
        X.append(feature_matrix[i - lookback : i])
        y.append(target[i])

    if not X:
        raise ValueError("Not enough rows to generate sequences for the requested lookback.")

    X = np.asarray(X, dtype=np.float32)
    y = np.asarray(y, dtype=np.int64)
    return X, y

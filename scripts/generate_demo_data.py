from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

BASE_DIR = Path(__file__).resolve().parents[1]
RAW_DIR = BASE_DIR / "data" / "raw"
RAW_DIR.mkdir(parents=True, exist_ok=True)


def generate_demo_data():
    start = datetime(2020, 1, 1)
    rng = np.random.default_rng(42)
    symbols = {
        "TCS": 3200.0,
        "INFY": 1450.0,
        "WIPRO": 470.0,
        "HCLTECH": 1120.0,
        "TECHM": 980.0,
        "NIFTYIT": 28700.0,
    }

    for symbol, base_price in symbols.items():
        dates = [start + timedelta(days=i) for i in range(500)]
        trend = np.linspace(0, 1.2, len(dates))
        cycle = np.sin(np.linspace(0, 12 * np.pi, len(dates))) * 0.035
        noise = rng.normal(0, 0.015, len(dates))
        close = np.asarray([base_price * (1 + trend_i + cycle_i + noise_i) for trend_i, cycle_i, noise_i in zip(trend, cycle, noise)])
        open_prices = close * (1 + rng.normal(0, 0.006, len(dates)))
        high = np.maximum(open_prices, close) * (1 + rng.uniform(0.004, 0.018, len(dates)))
        low = np.minimum(open_prices, close) * (1 - rng.uniform(0.004, 0.018, len(dates)))
        volume = rng.integers(50_000, 500_000, len(dates))

        df = pd.DataFrame(
            {
                "Date": dates,
                "Open": np.round(open_prices, 2),
                "High": np.round(high, 2),
                "Low": np.round(low, 2),
                "Close": np.round(close, 2),
                "Volume": volume.astype(int),
            }
        )
        df.to_csv(RAW_DIR / f"{symbol}.csv", index=False)

    print(f"Generated {len(symbols)} demo files in {RAW_DIR}")


if __name__ == "__main__":
    generate_demo_data()

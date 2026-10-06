import os
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parents[3] / "deepstock_ai.db"


CREATE_TABLES = [
    """
    CREATE TABLE IF NOT EXISTS stocks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol TEXT UNIQUE NOT NULL,
        company_name TEXT,
        sector TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS historical_prices (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol TEXT NOT NULL,
        date TEXT NOT NULL,
        open REAL,
        high REAL,
        low REAL,
        close REAL,
        volume INTEGER,
        UNIQUE(symbol, date)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS features (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol TEXT NOT NULL,
        date TEXT NOT NULL,
        daily_return REAL,
        log_return REAL,
        price_change REAL,
        volume_change REAL,
        sma_10 REAL,
        sma_20 REAL,
        sma_50 REAL,
        ema_10 REAL,
        ema_20 REAL,
        rsi REAL,
        macd REAL,
        macd_signal REAL,
        bollinger_upper REAL,
        bollinger_lower REAL,
        bollinger_width REAL,
        rolling_volatility REAL,
        high_low_ratio REAL,
        open_close_ratio REAL,
        next_day_return REAL,
        next_day_direction INTEGER,
        UNIQUE(symbol, date)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS experiments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        model_name TEXT,
        symbol TEXT,
        task TEXT,
        lookback INTEGER,
        optimizer TEXT,
        learning_rate REAL,
        batch_size INTEGER,
        epochs INTEGER,
        training_accuracy REAL,
        validation_accuracy REAL,
        test_accuracy REAL,
        precision REAL,
        recall REAL,
        f1 REAL,
        mae REAL,
        rmse REAL,
        training_time REAL,
        parameter_count INTEGER,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS predictions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol TEXT,
        model_name TEXT,
        prediction_date TEXT,
        predicted_direction INTEGER,
        probability_up REAL,
        probability_down REAL,
        predicted_return REAL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS model_metrics (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        experiment_id INTEGER,
        model_name TEXT,
        metric_name TEXT,
        metric_value REAL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        email TEXT,
        role TEXT DEFAULT 'student',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
    """,
]


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def initialize_db():
    conn = get_connection()
    try:
        for statement in CREATE_TABLES:
            conn.execute(statement)
        conn.commit()
    finally:
        conn.close()


def seed_demo_stocks():
    conn = get_connection()
    try:
        symbols = [
            ("TCS", "Tata Consultancy Services", "IT"),
            ("INFY", "Infosys", "IT"),
            ("WIPRO", "Wipro", "IT"),
            ("HCLTECH", "HCL Technologies", "IT"),
            ("TECHM", "Tech Mahindra", "IT"),
            ("NIFTYIT", "Nifty IT Index", "IT"),
        ]
        for symbol, company_name, sector in symbols:
            conn.execute(
                "INSERT OR IGNORE INTO stocks (symbol, company_name, sector) VALUES (?, ?, ?)",
                (symbol, company_name, sector),
            )
        conn.commit()
    finally:
        conn.close()

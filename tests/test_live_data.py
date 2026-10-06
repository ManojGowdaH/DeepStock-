import json
import io
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

from app.api import routes
from app.main import app
from app.services import live_data_service, indian_stocks_service, data_service
from app.schemas.models import TrainRequest

client = TestClient(app)


def test_live_feed_parses_intraday_candles(monkeypatch):
    timestamps = [1_700_000_000 + minute * 60 for minute in range(20)]
    closes = [100 + minute * 0.25 for minute in range(20)]
    result = {
        "timestamp": timestamps,
        "meta": {
            "currency": "INR",
            "regularMarketPrice": closes[-1],
            "regularMarketTime": timestamps[-1],
            "chartPreviousClose": 99.0,
        },
        "indicators": {
            "quote": [{
                "open": closes,
                "high": [value + 1 for value in closes],
                "low": [value - 1 for value in closes],
                "close": closes,
                "volume": [100] * len(closes),
            }]
        },
    }
    response = MagicMock()
    response.__enter__.return_value.read.return_value = json.dumps({"chart": {"result": [result]}}).encode()
    monkeypatch.setattr(live_data_service, "urlopen", lambda request, timeout: response)

    data = live_data_service.fetch_live_market_data("TCS", "1m", "1d")

    assert data["provider_symbol"] == "TCS.NS"
    assert data["price"] == closes[-1]
    assert len(data["rows"]) == 20
    assert data["analysis"]["rsi_14"] == 100.0
    assert data["analysis"]["trend"] == "above_ema_20"
    assert data["analysis"]["market_report"]["category"] == "Positive technical conditions"
    assert data["analysis"]["market_report"]["evidence"]
    assert data["analysis"]["market_report"]["cautions"]


def test_market_conditions_report_stays_educational():
    rows = [
        {"close": 100 + i * 0.1, "high": 101 + i * 0.1, "low": 99 + i * 0.1, "volume": 100}
        for i in range(20)
    ]

    report = live_data_service._technical_summary(rows, 0.5)["market_report"]

    assert report["status"] in {"positive", "neutral", "caution"}
    assert report["evidence"]
    assert any("not personalized financial advice" in caution for caution in report["cautions"])


def test_live_route_returns_provider_data(monkeypatch):
    expected = {
        "symbol": "TCS",
        "provider": "Yahoo Finance chart feed",
        "price": 123.45,
        "rows": [],
    }
    monkeypatch.setattr(routes, "fetch_live_market_data", lambda symbol, interval, period: expected)

    response = client.get("/api/stocks/TCS/live?interval=5m&period=1d")

    assert response.status_code == 200
    assert response.json() == expected


def test_live_route_rejects_unsupported_interval():
    response = client.get("/api/stocks/TCS/live?interval=2m&period=1d")

    assert response.status_code == 400
    assert "Unsupported interval" in response.json()["detail"]


def test_nse_catalog_parser_includes_every_series():
    csv_content = (
        "SYMBOL,NAME OF COMPANY,SERIES\n"
        "INFY,Infosys Limited,EQ\n"
        "RESTRICTED,Restricted Security,SM\n"
        "TESTBE,Example Trade-to-Trade,BE\n"
        "RELIANCE,Reliance Industries Limited,EQ\n"
    )

    stocks = indian_stocks_service.parse_nse_equity_csv(csv_content)

    assert [stock["symbol"] for stock in stocks] == ["INFY", "RESTRICTED", "TESTBE", "RELIANCE"]
    assert stocks[0]["company_name"] == "Infosys Limited"


def test_candlestick_patterns_are_reported_with_date():
    rows = [
        {"date": "2026-10-01", "open": 105, "high": 106, "low": 99, "close": 100, "volume": 100},
        {"date": "2026-10-02", "open": 98, "high": 107, "low": 97, "close": 106, "volume": 100},
    ]

    patterns = live_data_service.detect_candlestick_patterns(rows)

    assert any(pattern["name"] == "Bullish engulfing" and pattern["date"] == "2026-10-02" for pattern in patterns)


def test_stock_analysis_route_returns_combined_report(monkeypatch):
    expected = {
        "symbol": "INFY",
        "company_name": "Infosys Limited",
        "rows": [{"date": "2026-10-02T00:00:00+00:00", "open": 100, "high": 105, "low": 99, "close": 104, "volume": 1000}],
        "patterns": [],
        "news": [],
        "report": {"timing_outlook": "Mixed conditions · wait for clarity"},
    }
    monkeypatch.setattr(routes, "search_indian_stocks", lambda search, limit, exact=False: {"symbols": [{"symbol": "INFY", "company_name": "Infosys Limited"}]})
    monkeypatch.setattr(routes, "fetch_stock_analysis", lambda symbol, company_name, period: expected)

    response = client.get("/api/stocks/INFY/analysis?period=1y")

    assert response.status_code == 200
    assert response.json()["company_name"] == "Infosys Limited"
    assert "report" in response.json()


def test_recent_news_rss_returns_source_and_publication_date(monkeypatch):
    rss = b"""<rss><channel><item><title>Infosys announces results</title><link>https://example.com/news</link><pubDate>Mon, 05 Oct 2026 10:00:00 GMT</pubDate><source>Example News</source></item></channel></rss>"""
    response = MagicMock()
    response.__enter__.return_value.read.return_value = rss
    monkeypatch.setattr(live_data_service, "urlopen", lambda request, timeout: response)

    articles = live_data_service._fetch_recent_news("INFY", "Infosys Limited")

    assert articles[0]["title"] == "Infosys announces results"
    assert articles[0]["publisher"] == "Example News"
    assert articles[0]["published_at"].startswith("2026-10-05T10:00:00")


def test_security_headers_and_cors_allowlist():
    allowed = client.get("/health", headers={"Origin": "http://localhost:3000"})
    denied = client.options(
        "/api/stocks",
        headers={
            "Origin": "https://untrusted.example",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert allowed.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert allowed.headers["x-content-type-options"] == "nosniff"
    assert allowed.headers["x-frame-options"] == "DENY"
    assert "access-control-allow-origin" not in denied.headers


def test_write_endpoints_fail_closed_without_api_key(monkeypatch):
    monkeypatch.setattr(routes, "API_WRITE_KEY", "")

    response = client.post(
        "/api/data/upload?symbol=INFY",
        files={"file": ("prices.csv", b"Date,Open,High,Low,Close,Volume\n", "text/csv")},
    )

    assert response.status_code == 503
    assert "API_WRITE_KEY" in response.json()["detail"]


def test_upload_rejects_path_traversal_with_api_key(monkeypatch):
    monkeypatch.setattr(routes, "API_WRITE_KEY", "test-only-secret")

    response = client.post(
        "/api/data/upload?symbol=..%2F..%2Foutside",
        headers={"X-API-Key": "test-only-secret"},
        files={"file": ("prices.csv", b"Date,Open,High,Low,Close,Volume\n", "text/csv")},
    )

    assert response.status_code == 400
    assert "Invalid stock symbol" in response.json()["detail"]


def test_invalid_upload_is_rejected_before_any_file_is_written(tmp_path, monkeypatch):
    monkeypatch.setattr(data_service, "RAW_DIR", tmp_path)
    monkeypatch.setattr(data_service, "ensure_demo_data", lambda: None)
    malformed_csv = (
        b"Date,Open,High,Low,Close,Volume\n"
        b"2026-10-01,100,99,95,101,1000\n"
        b"2026-10-02,101,105,99,104,1200\n"
    )

    with pytest.raises(ValueError, match="High and Low"):
        data_service.save_uploaded_csv("INFY", SimpleNamespace(file=io.BytesIO(malformed_csv)))

    assert not (tmp_path / "INFY.csv").exists()


def test_training_request_bounds_compute_parameters():
    with pytest.raises(ValueError):
        TrainRequest(
            symbol="INFY",
            model="lstm",
            lookback=30,
            epochs=5000,
        )
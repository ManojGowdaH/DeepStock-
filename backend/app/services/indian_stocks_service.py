"""Searchable NSE equity catalogue with an offline fallback."""

import csv
import io
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.core.config import BASE_DIR

NSE_EQUITY_URL = "https://archives.nseindia.com/content/equities/EQUITY_L.csv"
CACHE_SECONDS = 24 * 60 * 60
FALLBACK_STOCKS = [
    ("RELIANCE", "Reliance Industries Limited"), ("TCS", "Tata Consultancy Services Limited"),
    ("HDFCBANK", "HDFC Bank Limited"), ("ICICIBANK", "ICICI Bank Limited"),
    ("INFY", "Infosys Limited"), ("BHARTIARTL", "Bharti Airtel Limited"),
    ("ITC", "ITC Limited"), ("SBIN", "State Bank of India"),
    ("LICI", "Life Insurance Corporation of India"), ("HINDUNILVR", "Hindustan Unilever Limited"),
    ("LT", "Larsen & Toubro Limited"), ("BAJFINANCE", "Bajaj Finance Limited"),
    ("HCLTECH", "HCL Technologies Limited"), ("MARUTI", "Maruti Suzuki India Limited"),
    ("SUNPHARMA", "Sun Pharmaceutical Industries Limited"), ("TATAMOTORS", "Tata Motors Limited"),
    ("WIPRO", "Wipro Limited"), ("AXISBANK", "Axis Bank Limited"),
    ("KOTAKBANK", "Kotak Mahindra Bank Limited"), ("NTPC", "NTPC Limited"),
    ("ONGC", "Oil and Natural Gas Corporation Limited"), ("TATASTEEL", "Tata Steel Limited"),
    ("TECHM", "Tech Mahindra Limited"), ("ULTRACEMCO", "UltraTech Cement Limited"),
    ("ADANIENT", "Adani Enterprises Limited"), ("ADANIPORTS", "Adani Ports and Special Economic Zone Limited"),
    ("ASIANPAINT", "Asian Paints Limited"), ("NESTLEIND", "Nestle India Limited"),
    ("POWERGRID", "Power Grid Corporation of India Limited"),
]

_catalog: list[dict] | None = None
_catalog_fetched_at = 0.0
_catalog_source = "Fallback catalogue"


def parse_nse_equity_csv(content: str) -> list[dict]:
    """Parse every named symbol in the public NSE equity master."""
    result = []
    for row in csv.DictReader(io.StringIO(content)):
        normalized = {str(key or "").strip().upper(): str(value or "").strip() for key, value in row.items()}
        symbol = normalized.get("SYMBOL", "").upper()
        company = normalized.get("NAME OF COMPANY", "")
        series = normalized.get("SERIES", "").upper()
        if symbol and company:
            result.append({"symbol": symbol, "company_name": company, "exchange": "NSE", "series": series})
    return result


def _read_local_symbols() -> list[dict]:
    raw_dir = BASE_DIR / "data" / "raw"
    local = []
    for path in raw_dir.glob("*.csv") if raw_dir.exists() else []:
        if path.stem.upper() == "NIFTYIT":
            continue
        local.append({"symbol": path.stem.upper(), "company_name": path.stem.upper(), "exchange": "Local demo data"})
    return local


def _fetch_catalog() -> list[dict]:
    global _catalog, _catalog_fetched_at, _catalog_source
    if _catalog and time.time() - _catalog_fetched_at < CACHE_SECONDS:
        return _catalog

    request = Request(NSE_EQUITY_URL, headers={"User-Agent": "Mozilla/5.0 DeepStock/1.0", "Accept": "text/csv,*/*"})
    try:
        with urlopen(request, timeout=6) as response:
            content = response.read().decode("utf-8-sig")
        catalog = parse_nse_equity_csv(content)
        if catalog:
            _catalog = catalog
            _catalog_fetched_at = time.time()
            _catalog_source = "NSE equity list"
            return catalog
    except (HTTPError, URLError, TimeoutError, OSError, UnicodeDecodeError):
        pass

    # Keep stale successful data usable during an exchange-host outage.
    if _catalog:
        _catalog_fetched_at = time.time()
        return _catalog
    fallback = [
        {"symbol": symbol, "company_name": name, "exchange": "NSE (fallback catalogue)"}
        for symbol, name in FALLBACK_STOCKS
    ]
    by_symbol = {stock["symbol"]: stock for stock in fallback}
    for stock in _read_local_symbols():
        by_symbol.setdefault(stock["symbol"], stock)
    _catalog = list(by_symbol.values())
    _catalog_fetched_at = time.time()
    _catalog_source = "Fallback catalogue"
    return _catalog


def search_indian_stocks(query: str = "", limit: int = 12, exact: bool = False) -> dict:
    """Return featured stocks or fuzzy matches from NSE's EQ-series listing."""
    normalized_query = query.strip().casefold()
    if not normalized_query:
        featured_symbols = {symbol for symbol, _ in FALLBACK_STOCKS}
        featured = [stock for stock in _fetch_catalog() if stock["symbol"] in featured_symbols]
        return {"symbols": featured[:limit], "source": _catalog_source, "catalogue": "NSE equity master", "total_count": len(_fetch_catalog())}

    catalog = _fetch_catalog()
    if exact:
        matches = [stock for stock in catalog if stock["symbol"].casefold() == normalized_query]
        return {"symbols": matches[:1], "source": _catalog_source, "catalogue": "NSE-listed equity and BE-series shares"}
    matches = [stock for stock in catalog if normalized_query in stock["symbol"].casefold() or normalized_query in stock["company_name"].casefold()]
    matches.sort(key=lambda stock: (
        not stock["symbol"].casefold().startswith(normalized_query),
        not stock["company_name"].casefold().startswith(normalized_query),
        stock["company_name"].casefold(),
    ))
    return {
        "symbols": matches[:max(1, min(limit, 50))],
        "source": _catalog_source,
        "catalogue": "NSE equity master",
        "total_count": len(catalog),
    }

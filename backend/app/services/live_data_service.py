import json
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen
from xml.etree import ElementTree


YAHOO_TICKERS = {
    "NIFTYIT": "^CNXIT",
}
SUPPORTED_INTERVALS = {"1m", "5m", "15m", "30m", "60m"}
SUPPORTED_RANGES = {"1d", "5d"}
SUPPORTED_HISTORY_RANGES = {"1y", "2y", "5y"}


def _technical_summary(rows: list[dict], change_percent: float | None = None) -> dict:
    closes = [row["close"] for row in rows]
    ema = None
    if closes:
        alpha = 2 / 21
        ema = closes[0]
        for close in closes[1:]:
            ema = alpha * close + (1 - alpha) * ema

    rsi = None
    if len(closes) >= 15:
        changes = [current - previous for previous, current in zip(closes[-15:-1], closes[-14:])]
        average_gain = sum(max(change, 0) for change in changes) / 14
        average_loss = sum(max(-change, 0) for change in changes) / 14
        rsi = 100.0 if average_loss == 0 and average_gain else (
            50.0 if average_loss == 0 else 100 - 100 / (1 + average_gain / average_loss)
        )

    volume_sum = sum(row["volume"] for row in rows)
    vwap = None
    if volume_sum:
        vwap = sum(
            ((row["high"] + row["low"] + row["close"]) / 3) * row["volume"]
            for row in rows
        ) / volume_sum

    latest = closes[-1] if closes else None
    trend = "above_ema_20" if latest is not None and ema is not None and latest >= ema else (
        "below_ema_20" if latest is not None and ema is not None else "unavailable"
    )

    evidence = []
    positive_checks = 0
    caution_checks = 0
    if latest is not None and ema is not None:
        above_ema = latest >= ema
        positive_checks += int(above_ema)
        caution_checks += int(not above_ema)
        evidence.append(f"Price is {'above' if above_ema else 'below'} the intraday EMA(20).")
    if latest is not None and vwap is not None:
        above_vwap = latest >= vwap
        positive_checks += int(above_vwap)
        caution_checks += int(not above_vwap)
        evidence.append(f"Latest price is {'above' if above_vwap else 'below'} session VWAP.")
    if change_percent is not None:
        positive_checks += int(change_percent > 0)
        caution_checks += int(change_percent < 0)
        direction = "up" if change_percent > 0 else "down" if change_percent < 0 else "flat"
        evidence.append(f"Provider-reported daily change is {direction} ({change_percent:+.2f}%).")
    if rsi is not None:
        if 45 <= rsi <= 65:
            positive_checks += 1
            evidence.append(f"RSI(14) is {rsi:.1f}, within the report's middle range (45–65).")
        elif rsi >= 70:
            caution_checks += 1
            evidence.append(f"RSI(14) is {rsi:.1f}; this is a high reading that may indicate short-term overextension.")
        elif rsi <= 30:
            caution_checks += 1
            evidence.append(f"RSI(14) is {rsi:.1f}; this is a low reading and does not by itself imply a reversal.")
        else:
            evidence.append(f"RSI(14) is {rsi:.1f}, outside the report's middle range.")

    if positive_checks >= 3 and caution_checks <= 1:
        category = "Positive technical conditions"
        description = "Several short-term indicators are supportive, but they are not a prediction or an instruction to invest."
        report_status = "positive"
    elif caution_checks >= 3:
        category = "Cautious technical conditions"
        description = "Several short-term indicators are weak or conflicting; consider the risks and avoid relying on this report alone."
        report_status = "caution"
    else:
        category = "Mixed technical conditions"
        description = "The indicators do not give a clear short-term picture. This report cannot determine a universally right time to invest."
        report_status = "neutral"

    return {
        "ema_20": round(ema, 4) if ema is not None else None,
        "rsi_14": round(rsi, 2) if rsi is not None else None,
        "vwap": round(vwap, 4) if vwap is not None else None,
        "trend": trend,
        "market_report": {
            "category": category,
            "status": report_status,
            "description": description,
            "evidence": evidence,
            "cautions": [
                "Intraday technical indicators are noisy and can reverse quickly.",
                "This is not personalized financial advice or a guaranteed buy/sell timing signal.",
                "Check your objectives, risk tolerance, diversification, and other market information independently.",
            ],
        },
    }


def fetch_live_market_data(symbol: str, interval: str = "1m", period: str = "1d") -> dict:
    """Fetch intraday candles from Yahoo Finance's chart endpoint."""
    if interval not in SUPPORTED_INTERVALS:
        raise ValueError(f"Unsupported interval: {interval}")
    if period not in SUPPORTED_RANGES:
        raise ValueError(f"Unsupported period: {period}")

    normalized_symbol = symbol.upper()
    ticker = YAHOO_TICKERS.get(normalized_symbol, f"{normalized_symbol}.NS")
    query = urlencode({"range": period, "interval": interval, "includePrePost": "false"})
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{quote(ticker, safe='')}?{query}"
    request = Request(url, headers={"User-Agent": "Mozilla/5.0 DeepStockAI/1.0"})

    try:
        with urlopen(request, timeout=12) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Live market data provider is unavailable: {exc}") from exc

    chart = payload.get("chart", {})
    if chart.get("error"):
        message = chart["error"].get("description", "Provider returned an error")
        raise RuntimeError(f"Live market data provider error: {message}")
    results = chart.get("result") or []
    if not results:
        raise RuntimeError(f"No live market data is currently available for {normalized_symbol}.")

    result = results[0]
    timestamps = result.get("timestamp") or []
    quote_data = (result.get("indicators", {}).get("quote") or [{}])[0]
    rows = []
    for index, timestamp in enumerate(timestamps):
        values = {
            field: (quote_data.get(field) or [None] * len(timestamps))[index]
            for field in ("open", "high", "low", "close", "volume")
        }
        if any(values[field] is None for field in ("open", "high", "low", "close")):
            continue
        rows.append({
            "date": datetime.fromtimestamp(timestamp, timezone.utc).isoformat(),
            "open": float(values["open"]),
            "high": float(values["high"]),
            "low": float(values["low"]),
            "close": float(values["close"]),
            "volume": int(values["volume"] or 0),
        })

    if not rows:
        raise RuntimeError(f"No intraday candles are currently available for {normalized_symbol}.")

    meta = result.get("meta", {})
    price = float(meta.get("regularMarketPrice") or rows[-1]["close"])
    previous_close = meta.get("chartPreviousClose") or meta.get("previousClose")
    change = price - float(previous_close) if previous_close is not None else None
    change_percent = (change / float(previous_close) * 100) if previous_close else None
    market_timestamp = meta.get("regularMarketTime") or timestamps[-1]

    return {
        "symbol": normalized_symbol,
        "provider_symbol": ticker,
        "provider": "Yahoo Finance chart feed",
        "interval": interval,
        "period": period,
        "currency": meta.get("currency"),
        "price": price,
        "previous_close": float(previous_close) if previous_close is not None else None,
        "change": round(change, 4) if change is not None else None,
        "change_percent": round(change_percent, 4) if change_percent is not None else None,
        "timestamp": datetime.fromtimestamp(market_timestamp, timezone.utc).isoformat(),
        "rows": rows,
        "analysis": _technical_summary(rows, change_percent),
        "disclaimer": "Market data may be delayed or unavailable. Educational analysis only; not financial advice.",
    }


def detect_candlestick_patterns(rows: list[dict]) -> list[dict]:
    """Identify a small set of common single- and two-candle formations."""
    patterns = []
    recent_rows = rows[-8:]
    for index, candle in enumerate(recent_rows):
        open_price = float(candle["open"])
        high = float(candle["high"])
        low = float(candle["low"])
        close = float(candle["close"])
        candle_range = high - low
        if candle_range <= 0:
            continue
        body = abs(close - open_price)
        upper_shadow = high - max(open_price, close)
        lower_shadow = min(open_price, close) - low
        date = str(candle.get("date", ""))[:10]

        if body <= candle_range * 0.1:
            patterns.append({"name": "Doji", "date": date, "description": "Open and close were close together; this shows indecision, not a predicted reversal."})
        if body > 0 and lower_shadow >= body * 2 and upper_shadow <= body * 0.6:
            patterns.append({"name": "Hammer-shaped candle", "date": date, "description": "A long lower wick with a small body; context and confirmation matter."})
        if body > 0 and upper_shadow >= body * 2 and lower_shadow <= body * 0.6:
            patterns.append({"name": "Shooting-star-shaped candle", "date": date, "description": "A long upper wick with a small body; this shape alone is not a sell signal."})

        if index == 0:
            continue
        previous = recent_rows[index - 1]
        previous_open = float(previous["open"])
        previous_close = float(previous["close"])
        previous_body_low = min(previous_open, previous_close)
        previous_body_high = max(previous_open, previous_close)
        current_body_low = min(open_price, close)
        current_body_high = max(open_price, close)
        if previous_close < previous_open and close > open_price and current_body_low <= previous_body_low and current_body_high >= previous_body_high:
            patterns.append({"name": "Bullish engulfing", "date": date, "description": "The current body covers the previous down-candle body; this is a historical pattern, not a forecast."})
        elif previous_close > previous_open and close < open_price and current_body_low <= previous_body_low and current_body_high >= previous_body_high:
            patterns.append({"name": "Bearish engulfing", "date": date, "description": "The current body covers the previous up-candle body; this is a historical pattern, not a forecast."})
    return patterns[-8:]


def _fetch_recent_news(symbol: str, company_name: str = "") -> list[dict]:
    search_term = company_name or symbol.upper()
    rss_query = quote(f'"{search_term}" stock when:7d')
    rss_url = f"https://news.google.com/rss/search?q={rss_query}&hl=en-IN&gl=IN&ceid=IN:en"
    rss_request = Request(rss_url, headers={"User-Agent": "Mozilla/5.0 DeepStockAI/1.0", "Accept": "application/rss+xml,application/xml,text/xml"})
    try:
        with urlopen(rss_request, timeout=8) as response:
            root = ElementTree.fromstring(response.read())
        articles = []
        for item in root.findall("./channel/item")[:8]:
            title = item.findtext("title")
            link = item.findtext("link")
            if not title or not link:
                continue
            published = item.findtext("pubDate")
            published_at = None
            if published:
                try:
                    from email.utils import parsedate_to_datetime

                    published_at = parsedate_to_datetime(published).astimezone(timezone.utc).isoformat()
                except (TypeError, ValueError, OverflowError):
                    pass
            articles.append({
                "title": title,
                "publisher": item.findtext("source") or "Google News",
                "url": link,
                "published_at": published_at,
            })
        if articles:
            return articles
    except (HTTPError, URLError, TimeoutError, OSError, ElementTree.ParseError):
        pass

    # Yahoo Finance can still return useful ticker-oriented results if RSS is unavailable.
    ticker = YAHOO_TICKERS.get(symbol.upper(), f"{symbol.upper()}.NS")
    query = urlencode({"q": ticker, "newsCount": 8, "quotesCount": 0})
    url = f"https://query1.finance.yahoo.com/v1/finance/search?{query}"
    request = Request(url, headers={"User-Agent": "Mozilla/5.0 DeepStockAI/1.0"})
    try:
        with urlopen(request, timeout=8) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError):
        return []

    articles = []
    for item in payload.get("news") or []:
        link = item.get("link")
        title = item.get("title")
        if not link or not title:
            continue
        published = item.get("providerPublishTime")
        articles.append({
            "title": str(title),
            "publisher": str(item.get("publisher") or "News provider"),
            "url": str(link),
            "published_at": datetime.fromtimestamp(published, timezone.utc).isoformat() if published else None,
        })
    return articles[:8]


def fetch_stock_analysis(symbol: str, company_name: str = "", period: str = "1y") -> dict:
    """Fetch daily history and news, then return a descriptive technical snapshot."""
    if period not in SUPPORTED_HISTORY_RANGES:
        raise ValueError(f"Unsupported history period: {period}")
    normalized_symbol = symbol.upper()
    ticker = YAHOO_TICKERS.get(normalized_symbol, f"{normalized_symbol}.NS")
    query = urlencode({"range": period, "interval": "1d", "includePrePost": "false"})
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{quote(ticker, safe='')}?{query}"
    request = Request(url, headers={"User-Agent": "Mozilla/5.0 DeepStockAI/1.0"})
    try:
        with urlopen(request, timeout=12) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Historical market data provider is unavailable: {exc}") from exc

    chart_data = payload.get("chart", {})
    if chart_data.get("error"):
        message = chart_data["error"].get("description", "Provider returned an error")
        raise RuntimeError(f"Historical market data provider error: {message}")
    results = chart_data.get("result") or []
    if not results:
        raise RuntimeError(f"No historical market data is currently available for {normalized_symbol}.")

    result = results[0]
    timestamps = result.get("timestamp") or []
    quote_data = (result.get("indicators", {}).get("quote") or [{}])[0]
    rows = []
    for index, timestamp in enumerate(timestamps):
        values = {
            field: (quote_data.get(field) or [None] * len(timestamps))[index]
            for field in ("open", "high", "low", "close", "volume")
        }
        if any(values[field] is None for field in ("open", "high", "low", "close")):
            continue
        rows.append({
            "date": datetime.fromtimestamp(timestamp, timezone.utc).isoformat(),
            "open": float(values["open"]),
            "high": float(values["high"]),
            "low": float(values["low"]),
            "close": float(values["close"]),
            "volume": int(values["volume"] or 0),
        })
    if not rows:
        raise RuntimeError(f"No daily candles are currently available for {normalized_symbol}.")

    closes = [row["close"] for row in rows]
    ema = closes[0]
    alpha = 2 / 21
    for close in closes[1:]:
        ema = alpha * close + (1 - alpha) * ema
    recent_changes = [current - previous for previous, current in zip(closes[-15:-1], closes[-14:])]
    rsi = None
    if len(recent_changes) == 14:
        average_gain = sum(max(change, 0) for change in recent_changes) / 14
        average_loss = sum(max(-change, 0) for change in recent_changes) / 14
        rsi = 100.0 if average_loss == 0 and average_gain else (
            50.0 if average_loss == 0 else 100 - 100 / (1 + average_gain / average_loss)
        )

    latest_price = closes[-1]
    above_ema = latest_price >= ema
    trend = "Above 20-day EMA" if above_ema else "Below 20-day EMA"
    patterns = detect_candlestick_patterns(rows)
    bullish_patterns = sum("Bullish" in pattern["name"] or "Hammer" in pattern["name"] for pattern in patterns)
    bearish_patterns = sum("Bearish" in pattern["name"] or "Shooting" in pattern["name"] for pattern in patterns)
    supportive = int(above_ema) + int(rsi is not None and 45 <= rsi <= 65) + int(bullish_patterns > bearish_patterns)
    cautionary = int(not above_ema) + int(rsi is not None and (rsi >= 70 or rsi <= 30)) + int(bearish_patterns > bullish_patterns)
    if supportive >= 2 and cautionary == 0:
        timing_outlook = "Conditions lean positive · observe"
    elif cautionary >= 2 and supportive == 0:
        timing_outlook = "Conditions look cautious · observe"
    else:
        timing_outlook = "Mixed conditions · wait for clarity"

    evidence = [f"Latest close is {'above' if above_ema else 'below'} its 20-day exponential moving average."]
    if rsi is not None:
        evidence.append(f"14-day RSI is {rsi:.1f}; readings can remain elevated or low for extended periods.")
    if patterns:
        evidence.append(f"{len(patterns)} defined candle pattern(s) were detected among the most recent daily candles.")
    else:
        evidence.append("No defined candle pattern was detected among the most recent daily candles.")
    report_summary = " ".join(evidence) + " This is a snapshot of historical data, not a buy/sell instruction or a prediction."

    meta = result.get("meta", {})
    return {
        "symbol": normalized_symbol,
        "company_name": company_name or normalized_symbol,
        "provider_symbol": ticker,
        "provider": "Yahoo Finance chart and news feeds",
        "period": period,
        "currency": meta.get("currency", "INR"),
        "price": latest_price,
        "latest_date": rows[-1]["date"][:10],
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "rows": rows,
        "patterns": patterns,
        "news": _fetch_recent_news(normalized_symbol, company_name),
        "report": {
            "title": "Historical market snapshot",
            "summary": report_summary,
            "timing_outlook": timing_outlook,
            "trend": trend,
            "rsi_14": round(rsi, 2) if rsi is not None else None,
            "disclaimer": "Informational analysis only; no guaranteed or personalized buy/sell timing.",
        },
    }
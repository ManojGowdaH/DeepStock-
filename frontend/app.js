const BACKEND_URL = 'http://localhost:8000';
const searchInput = document.getElementById('stock-search');
const suggestionBox = document.getElementById('stock-suggestions');
const searchError = document.getElementById('search-error');
const analyzeButton = document.getElementById('analyze-button');
const analysisView = document.getElementById('analysis-view');
let priceChart;
let chartResizeObserver;
let analysisRows = [];
let selectedChartRange = '1m';
let currentAnalysisSymbol = '';
let currentChartIsIntraday = false;
let suggestionTimer;
let searchController;
let searchSequence = 0;
let highlightedSuggestion = -1;
let lastSuggestions = [];

async function checkBackend() {
  const status = document.getElementById('backend-status');
  try {
    const response = await fetch(`${BACKEND_URL}/health`);
    if (!response.ok) throw new Error('Unavailable');
    status.textContent = 'Market analysis ready';
    document.getElementById('backend-indicator').className = 'status-pill status-ready';
  } catch {
    status.textContent = 'Backend unavailable';
    document.getElementById('backend-indicator').className = 'status-pill status-error';
  }
}

function closeSuggestions() {
  suggestionBox.hidden = true;
  searchInput.setAttribute('aria-expanded', 'false');
  highlightedSuggestion = -1;
}

function selectSuggestion(stock) {
  searchInput.value = `${stock.company_name} (${stock.symbol})`;
  searchInput.dataset.symbol = stock.symbol;
  closeSuggestions();
}

async function searchStocks(query) {
  if (query.trim().length < 2) {
    closeSuggestions();
    return;
  }
  try {
    const requestSequence = ++searchSequence;
    if (searchController) searchController.abort();
    searchController = new AbortController();
    const response = await fetch(`${BACKEND_URL}/api/stocks?search=${encodeURIComponent(query.trim())}&limit=12`, { signal: searchController.signal });
    if (!response.ok) throw new Error('Could not search companies right now.');
    const data = await response.json();
    if (requestSequence !== searchSequence) return;
    const normalizedQuery = query.trim().toLocaleLowerCase();
    lastSuggestions = (data.symbols || []).filter(stock =>
      `${stock.symbol} ${stock.company_name}`.toLocaleLowerCase().includes(normalizedQuery)
    );
    document.getElementById('catalogue-status').textContent = data.source === 'NSE equity list'
      ? `Searching ${Number(data.total_count || 0).toLocaleString()} NSE-listed symbols. BSE-only listings may not appear.`
      : 'The NSE catalogue is offline; searching a limited local fallback list.';
    suggestionBox.replaceChildren();
    if (!lastSuggestions.length) {
      const empty = document.createElement('div');
      empty.className = 'suggestion-empty';
      empty.textContent = 'No matching NSE-listed company found';
      suggestionBox.append(empty);
    } else {
      lastSuggestions.forEach((stock, index) => {
        const button = document.createElement('button');
        button.type = 'button';
        button.className = 'suggestion-option';
        button.setAttribute('role', 'option');
        button.setAttribute('aria-selected', 'false');
        const name = document.createElement('span');
        name.className = 'suggestion-company';
        name.textContent = stock.company_name;
        const symbol = document.createElement('span');
        symbol.className = 'suggestion-symbol';
        symbol.textContent = stock.symbol;
        button.append(name, symbol);
        button.addEventListener('click', () => selectSuggestion(stock));
        button.dataset.index = String(index);
        suggestionBox.append(button);
      });
    }
    suggestionBox.hidden = false;
    searchInput.setAttribute('aria-expanded', 'true');
  } catch (error) {
    if (error.name === 'AbortError') return;
    lastSuggestions = [];
    suggestionBox.replaceChildren();
    const empty = document.createElement('div');
    empty.className = 'suggestion-empty';
    empty.textContent = error.message;
    suggestionBox.append(empty);
    suggestionBox.hidden = false;
    searchInput.setAttribute('aria-expanded', 'true');
  }
}

function selectHighlightedSuggestion() {
  if (highlightedSuggestion >= 0 && lastSuggestions[highlightedSuggestion]) {
    selectSuggestion(lastSuggestions[highlightedSuggestion]);
    return true;
  }
  return false;
}

function applyVisibleChartRange(range = selectedChartRange) {
  if (!priceChart || !analysisRows.length) return;
  selectedChartRange = range;
  if (range === '1d' && currentChartIsIntraday) {
    priceChart.timeScale().fitContent();
    document.querySelectorAll('#range-controls [data-range]').forEach(button => {
      button.classList.toggle('is-active', button.dataset.range === range);
    });
    return;
  }
  const candles = analysisRows.map(row => ({ time: row.date.slice(0, 10) }));
  const toDate = new Date(`${candles[candles.length - 1].time}T00:00:00Z`);
  const fromDate = new Date(toDate);
  const rangeDelta = { '1d': [0, 0], '1m': [-1, 0], '3m': [-3, 0], '6m': [-6, 0], '1y': [0, -1], '3y': [0, -3], '5y': [0, -5] }[range] || [-1, 0];
  if (rangeDelta[0]) fromDate.setUTCMonth(fromDate.getUTCMonth() + rangeDelta[0]);
  if (rangeDelta[1]) fromDate.setUTCFullYear(fromDate.getUTCFullYear() + rangeDelta[1]);
  const to = toDate.toISOString().slice(0, 10);
  const from = fromDate.toISOString().slice(0, 10);
  priceChart.timeScale().setVisibleRange({ from, to });
  document.querySelectorAll('#range-controls [data-range]').forEach(button => {
    button.classList.toggle('is-active', button.dataset.range === range);
  });
}

function formatChartTick(time) {
  if (typeof time === 'number') {
    return new Intl.DateTimeFormat('en-IN', { hour: '2-digit', minute: '2-digit', timeZone: 'Asia/Kolkata' }).format(new Date(time * 1000));
  }
  let date;
  if (typeof time === 'string') {
    date = new Date(`${time}T00:00:00Z`);
  } else if (time && typeof time === 'object' && 'year' in time) {
    date = new Date(Date.UTC(time.year, time.month - 1, time.day));
  } else {
    return '';
  }
  if (Number.isNaN(date.getTime())) return '';

  return new Intl.DateTimeFormat('en-IN', { day: '2-digit', month: 'short', timeZone: 'UTC' }).format(date);
}

function renderChart(rows, { intraday = false } = {}) {
  const container = document.getElementById('stock-chart');
  if (!window.LightweightCharts) {
    container.textContent = 'Candlestick chart library could not be loaded.';
    return;
  }
  currentChartIsIntraday = intraday;
  if (chartResizeObserver) chartResizeObserver.disconnect();
  if (priceChart) priceChart.remove();
  priceChart = LightweightCharts.createChart(container, {
    width: container.clientWidth,
    height: container.clientHeight,
    layout: { background: { color: '#ffffff' }, textColor: '#738091', fontFamily: 'Inter, Arial, sans-serif' },
    grid: { vertLines: { color: '#f0f2f5' }, horzLines: { color: '#f0f2f5' } },
    rightPriceScale: { borderColor: '#e8ebef' },
    localization: { priceFormatter: value => `₹${Number(value).toLocaleString('en-IN', { maximumFractionDigits: 2 })}` },
    timeScale: {
      borderColor: '#e8ebef',
      timeVisible: intraday,
      rightOffset: 5,
      barSpacing: 8,
      minBarSpacing: 0.1,
      tickMarkFormatter: time => formatChartTick(time),
    },
    handleScroll: { mouseWheel: true, pressedMouseMove: true, horzTouchDrag: true },
    handleScale: { axisPressedMouseMove: true, mouseWheel: true, pinch: true },
    crosshair: { mode: LightweightCharts.CrosshairMode.Normal },
  });
  const candles = priceChart.addCandlestickSeries({
    upColor: '#15966a', downColor: '#df5962', borderUpColor: '#15966a', borderDownColor: '#df5962',
    wickUpColor: '#15966a', wickDownColor: '#df5962',
    priceLineVisible: true,
    lastValueVisible: true,
  });
  const candleData = rows.map(row => ({
    time: intraday ? Math.floor(new Date(row.date).getTime() / 1000) : row.date.slice(0, 10),
    open: Number(row.open), high: Number(row.high), low: Number(row.low), close: Number(row.close), volume: Number(row.volume || 0),
  }));
  candles.setData(candleData);
  const volume = priceChart.addHistogramSeries({
    priceFormat: { type: 'volume' },
    priceScaleId: 'volume',
    lastValueVisible: false,
    priceLineVisible: false,
  });
  volume.setData(candleData.map(candle => ({
    time: candle.time,
    value: candle.volume,
    color: candle.close >= candle.open ? 'rgba(21, 150, 106, 0.22)' : 'rgba(223, 89, 98, 0.22)',
  })));
  priceChart.priceScale('volume').applyOptions({ scaleMargins: { top: 0.82, bottom: 0 }, visible: false });
  applyVisibleChartRange(selectedChartRange);
  document.getElementById('chart-title').textContent = intraday ? 'Today · 5-minute candlesticks' : 'Daily candlesticks';
  const readout = document.getElementById('chart-readout');
  const updateReadout = candle => {
    if (!candle) return;
    const changePercent = candle.open ? ((candle.close - candle.open) / candle.open) * 100 : 0;
    const changeClass = changePercent >= 0 ? 'readout-up' : 'readout-down';
    readout.replaceChildren();
    const date = document.createElement('span');
    date.className = 'readout-date';
    date.textContent = intraday
      ? new Intl.DateTimeFormat('en-IN', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit', timeZone: 'Asia/Kolkata' }).format(new Date(Number(candle.time) * 1000))
      : formatChartTick(candle.time);
    readout.append(date);
    [['O', candle.open], ['H', candle.high], ['L', candle.low], ['C', candle.close]].forEach(([label, value]) => {
      const item = document.createElement('span');
      item.className = 'readout-item';
      item.textContent = `${label} ${Number(value).toLocaleString('en-IN', { maximumFractionDigits: 2 })}`;
      readout.append(item);
    });
    const change = document.createElement('span');
    change.className = `readout-change ${changeClass}`;
    change.textContent = `${changePercent >= 0 ? '+' : ''}${changePercent.toFixed(2)}%`;
    readout.append(change);
  };
  updateReadout(candleData[candleData.length - 1]);
  priceChart.subscribeCrosshairMove(param => {
    if (!param.time || !param.seriesData) {
      updateReadout(candleData[candleData.length - 1]);
      return;
    }
    const candle = param.seriesData.get(candles);
    if (candle) updateReadout({ ...candle, time: param.time });
  });
  chartResizeObserver = new ResizeObserver(entries => {
    if (priceChart && entries[0]) priceChart.applyOptions({ width: entries[0].contentRect.width });
  });
  chartResizeObserver.observe(container);
}

function addTextItem(list, title, detail, href) {
  const item = document.createElement('li');
  const heading = document.createElement('strong');
  heading.textContent = title;
  item.append(heading);
  if (detail) {
    const text = document.createElement('span');
    text.className = 'item-detail';
    text.textContent = detail;
    item.append(text);
  }
  if (href) {
    try {
      const safeUrl = new URL(href, window.location.href);
      if (safeUrl.protocol === 'https:') {
        const link = document.createElement('a');
        link.href = safeUrl.href;
        link.target = '_blank';
        link.rel = 'noopener noreferrer';
        link.textContent = 'Read article ↗';
        item.append(link);
      }
    } catch {
      // Ignore malformed provider links.
    }
  }
  list.append(item);
}

function renderAnalysis(data) {
  const report = data.report || {};
  currentAnalysisSymbol = data.symbol;
  analysisRows = data.rows || [];
  selectedChartRange = '1m';
  document.querySelectorAll('#range-controls [data-range]').forEach(button => {
    button.classList.toggle('is-active', button.dataset.range === selectedChartRange);
  });
  document.getElementById('company-title').textContent = data.company_name || data.symbol;
  document.getElementById('company-symbol').textContent = `${data.symbol} · NSE`;
  document.getElementById('latest-price').textContent = data.price == null ? '—' : `₹${Number(data.price).toLocaleString('en-IN', { maximumFractionDigits: 2 })}`;
  document.getElementById('price-date').textContent = data.latest_date ? `Latest daily close · ${data.latest_date}` : 'Latest price unavailable';
  document.getElementById('report-title').textContent = report.title || 'Analysis summary';
  document.getElementById('report-summary').textContent = report.summary || 'Analysis is unavailable.';
  document.getElementById('timing-badge').textContent = report.timing_outlook || 'Informational only';
  document.getElementById('trend-snapshot').textContent = report.trend || 'Unavailable';
  document.getElementById('rsi-value').textContent = report.rsi_14 == null ? 'Unavailable' : Number(report.rsi_14).toFixed(1);
  document.getElementById('pattern-count').textContent = `${(data.patterns || []).length} found`;
  document.getElementById('history-meta').textContent = `${data.rows.length.toLocaleString()} daily candles · ${data.period} of history`;
  document.getElementById('price-source').textContent = `Source: ${data.provider}. Prices may be delayed. Updated ${new Date(data.timestamp).toLocaleString()}.`;
  document.getElementById('data-updated').textContent = `Report generated ${new Date(data.timestamp).toLocaleTimeString()}`;
  renderChart(data.rows || []);

  const patternsList = document.getElementById('patterns-list');
  patternsList.replaceChildren();
  if (!data.patterns || !data.patterns.length) {
    const item = document.createElement('li');
    item.className = 'empty-state';
    item.textContent = 'No defined patterns were detected in the latest candles.';
    patternsList.append(item);
  } else {
    data.patterns.forEach(pattern => addTextItem(patternsList, `${pattern.name} · ${pattern.date}`, pattern.description));
  }

  const newsList = document.getElementById('news-list');
  newsList.replaceChildren();
  if (!data.news || !data.news.length) {
    const item = document.createElement('li');
    item.className = 'empty-state';
    item.textContent = 'No recent related news was returned by the provider.';
    newsList.append(item);
  } else {
    data.news.forEach(article => {
      const published = article.published_at ? ` · ${new Date(article.published_at).toLocaleDateString()}` : '';
      addTextItem(newsList, article.title, `${article.publisher || 'News source'}${published}`, article.url);
    });
  }
  analysisView.hidden = false;
}

async function selectChartRange(range) {
  if (!analysisRows.length) return;
  if (range !== '1d') {
    selectedChartRange = range;
    renderChart(analysisRows);
    document.getElementById('history-meta').textContent = `${analysisRows.length.toLocaleString()} daily candles · ${range.toUpperCase()} range`;
    document.getElementById('price-source').textContent = 'Daily historical candles · Yahoo Finance. Prices may be delayed.';
    return;
  }

  const historyMeta = document.getElementById('history-meta');
  const priceSource = document.getElementById('price-source');
  const rangeButtons = document.querySelectorAll('#range-controls [data-range]');
  rangeButtons.forEach(button => { button.disabled = true; });
  historyMeta.textContent = 'Loading today’s intraday candles…';
  try {
    const response = await fetch(`${BACKEND_URL}/api/stocks/${encodeURIComponent(currentAnalysisSymbol)}/live?interval=5m&period=1d`);
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || 'Intraday candles are not available right now.');
    if (!data.rows || !data.rows.length) throw new Error('No intraday candles are available yet for today.');
    selectedChartRange = '1d';
    renderChart(data.rows, { intraday: true });
    historyMeta.textContent = `${data.rows.length} five-minute candles · ${new Date(data.timestamp).toLocaleDateString()}`;
    priceSource.textContent = `Today’s intraday data · ${data.provider} · Quotes may be delayed.`;
    rangeButtons.forEach(button => { button.classList.toggle('is-active', button.dataset.range === '1d'); });
  } catch (error) {
    historyMeta.textContent = 'Showing daily history';
    priceSource.textContent = `${error.message} Select a longer range to return to daily candles.`;
    rangeButtons.forEach(button => { button.classList.toggle('is-active', button.dataset.range === selectedChartRange); });
  } finally {
    rangeButtons.forEach(button => { button.disabled = false; });
  }
}

async function analyzeStock(symbol) {
  if (!symbol) return;
  searchError.hidden = true;
  analyzeButton.disabled = true;
  analyzeButton.innerHTML = '<span class="spinner" aria-hidden="true"></span> Analyzing…';
  analysisView.hidden = false;
  document.getElementById('report-summary').textContent = 'Loading stock history, candle patterns, and recent news…';
  analysisView.scrollIntoView({ behavior: 'smooth', block: 'start' });
  try {
    const response = await fetch(`${BACKEND_URL}/api/stocks/${encodeURIComponent(symbol)}/analysis?period=5y`);
    const data = await response.json();
    if (response.status === 502) throw new Error('Market history is unavailable for this stock from the data provider right now. The stock can still appear in the NSE list; please try again later.');
    if (!response.ok) throw new Error(data.detail || 'Analysis could not be completed.');
    renderAnalysis(data);
  } catch (error) {
    analysisView.hidden = true;
    searchError.textContent = error.message;
    searchError.hidden = false;
  } finally {
    analyzeButton.disabled = false;
    analyzeButton.innerHTML = 'Analyze stock <span aria-hidden="true">→</span>';
  }
}

searchInput.addEventListener('input', () => {
  delete searchInput.dataset.symbol;
  searchSequence += 1;
  if (searchController) searchController.abort();
  window.clearTimeout(suggestionTimer);
  suggestionTimer = window.setTimeout(() => searchStocks(searchInput.value), 220);
});
searchInput.addEventListener('keydown', event => {
  if (suggestionBox.hidden) return;
  const options = [...suggestionBox.querySelectorAll('.suggestion-option')];
  if (!options.length) return;
  if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
    event.preventDefault();
    highlightedSuggestion = (highlightedSuggestion + (event.key === 'ArrowDown' ? 1 : -1) + options.length) % options.length;
    options.forEach((option, index) => {
      option.classList.toggle('is-highlighted', index === highlightedSuggestion);
      option.setAttribute('aria-selected', String(index === highlightedSuggestion));
    });
  } else if (event.key === 'Enter' && selectHighlightedSuggestion()) {
    event.preventDefault();
  } else if (event.key === 'Escape') closeSuggestions();
});
document.addEventListener('click', event => {
  if (!event.target.closest('.search-field-wrap')) closeSuggestions();
});
document.getElementById('search-form').addEventListener('submit', event => {
  event.preventDefault();
  const symbol = searchInput.dataset.symbol || searchInput.value.trim().split(/\s|\(/)[0].toUpperCase();
  analyzeStock(symbol.replace(/\)$/, ''));
});

document.getElementById('range-controls').addEventListener('click', event => {
  const button = event.target.closest('[data-range]');
  if (button) selectChartRange(button.dataset.range);
});

checkBackend();

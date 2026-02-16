from __future__ import annotations

from typing import Any, Dict, List, Optional


def analyze_sentiment(call_gateway, messages, model, timeout_s, dry_run, api_key):
    return call_gateway(
        None,
        messages + [{"role": "user", "content": "判斷市場情緒（正向/中性/負向）與驚喜程度（超預期/符合/低於），簡短繁體中文回答。"}],
        model,
        timeout_s,
        dry_run,
        category="sentiment",
        llm_log_path=None,
        api_key=api_key,
    )


def trader_insights(call_gateway, messages, model, timeout_s, dry_run, api_key):
    return call_gateway(
        None,
        messages + [{"role": "user", "content": (
            "以交易員視角（繁體中文）列出3-5點可交易洞見與因果理由，包含可能觸發與風險；"
            "不得出現明確下單指令或保證語句。以條列重點輸出。"
        )}],
        model,
        timeout_s,
        dry_run,
        category="trader",
        llm_log_path=None,
        api_key=api_key,
    )


def overview_bullets(call_gateway, messages, model, timeout_s, dry_run, api_key):
    return call_gateway(
        None,
        messages + [{"role": "user", "content": "請撰寫一份最新的股票研究摘要（繁體中文），包含：1) 可交易但不涉及執行指令的重點要點、2) 事件時間線、3) 核心結論與需要留意的風險。"}],
        model,
        timeout_s,
        dry_run,
        category="bullets",
        llm_log_path=None,
        api_key=api_key,
    )


def watchlist(call_gateway, messages, model, timeout_s, dry_run, api_key):
    return call_gateway(
        None,
        messages + [{"role": "user", "content": (
            "請輸出JSON，鍵watch為陣列，每項包含：metric(觀測指標)、rationale(理由)、suggested_check(建議檢核方式或閾值)、priority(1-3)。"
            "僅輸出JSON，不要額外說明。"
        )}],
        model,
        timeout_s,
        dry_run,
        category="watch",
        llm_log_path=None,
        api_key=api_key,
    )

def _normalize_ticker(ticker: str) -> str:
    t = (ticker or '').strip()
    if not t:
        return t
    # Heuristic: Taiwan tickers need suffix .TW (listed) or .TWO (OTC). Default to .TW when pure digits.
    if t.isdigit() and '.TW' not in t and '.TWO' not in t:
        return t + '.TW'
    return t


def fetch_yfinance_prices(ticker: str) -> Dict[str, Dict[str, Any]]:
    """Fetch open/close (and a few intraday fields) via yfinance.

    Returns a dict like: {"kpis": {"open":..., "prev_close":..., "day_high":..., "day_low":..., "price":..., "volume":...}}
    If yfinance isn't available, returns {}.
    """
    try:
        import yfinance as yf  # type: ignore
    except Exception:
        return {}
    try:
        tk = yf.Ticker(_normalize_ticker(ticker))
        info = getattr(tk, "info", {}) or {}
        kpis: Dict[str, Any] = {}
        # current price
        if info.get("regularMarketPrice") is not None:
            kpis["price"] = info.get("regularMarketPrice")
        # open / close / day range / volume
        for src_key, out_key in [
            ("regularMarketOpen", "open"),
            ("regularMarketPreviousClose", "prev_close"),
            ("regularMarketDayHigh", "day_high"),
            ("regularMarketDayLow", "day_low"),
            ("regularMarketVolume", "volume"),
        ]:
            if info.get(src_key) is not None:
                kpis[out_key] = info.get(src_key)
        return {"kpis": kpis} if kpis else {}
    except Exception:
        return {}

def fetch_yfinance_series(ticker: str, period: str = "1mo", interval: str = "1d") -> Dict[str, Dict[str, Any]]:
    """Fetch recent close series for sparkline via yfinance.

    Returns {"series": {"close": [float,...]}} or {} if unavailable.
    """
    try:
        import yfinance as yf  # type: ignore
    except Exception:
        return {}
    try:
        tk = yf.Ticker(_normalize_ticker(ticker))
        hist = tk.history(period=period, interval=interval)
        closes = []
        try:
            closes = [float(x) for x in hist["Close"].tolist() if x is not None]
        except Exception:
            pass
        return {"series": {"close": closes[-60:]}} if closes else {}
    except Exception:
        return {}

def analyze_kpi_impact(call_gateway, micro: Dict[str, Any], kpis: Dict[str, Any], messages: List[Dict[str, str]], model, timeout_s, dry_run, api_key):
    """Infer KPI impacts per news item.

    Returns JSON like:
      { revenue: {direction: 上/下/持平}, gross_margin: {direction: 上/下/持平}, eps: {direction: 上/下/持平} }
    """
    t = str(micro.get('title') or '')[:160]
    s = str(micro.get('summary') or '')[:220]
    base = []
    for k in ['price','change','change_percent','gross_margin_pct','latest_eps','target_mean_price']:
        if k in (kpis or {}):
            base.append(f"{k}={kpis[k]}")
    prompt = (
        "根據以下單則新聞重點與現有KPIs，判斷對主要財務指標的方向（上/下/持平）。\n"
        "僅輸出JSON: {\"revenue\":{\"direction\":上|下|持平},\"gross_margin\":{\"direction\":上|下|持平},\"eps\":{\"direction\":上|下|持平}}。\n"
        "避免過度推論與保證語句。\n\n"
        f"新聞：{t} ｜ {s}\nKPIs: {'; '.join(base) if base else '(無)'}\n"
    )
    return call_gateway(
        None,
        messages + [{"role": "user", "content": prompt}],
        model,
        timeout_s,
        dry_run,
        category="kpi_impact",
        llm_log_path=None,
        api_key=api_key,
    )


def analyze_financials(call_gateway, news_micro: List[Dict[str, Any]], kpis: Dict[str, Any], messages: List[Dict[str, str]], model, timeout_s, dry_run, api_key):
    """Quant/finance summary based on per-news notes + KPIs.

    Expects JSON:
      { thesis: str, drivers: [str], risks: [str], positioning: [str], metrics_to_watch: [str], timeframe: str, expected_move_pct: number, confidence: 1-5 }
    """
    # Condense micro notes for context
    bullets = []
    for m in news_micro[:10]:
        t = str(m.get('title') or '')[:120]
        s = str(m.get('summary') or '')[:160]
        sent = m.get('sentiment') or ''
        bullets.append(f"- {t} ｜ {s} ｜ 情緒:{sent}")
    kpi_lines = []
    for k in ['price','change','change_percent','gross_margin_pct','latest_eps','target_mean_price','recommendation']:
        if k in kpis:
            kpi_lines.append(f"{k}={kpis[k]}")
    prompt = (
        "你是量化交易與財務分析結合的分析師，使用繁體中文作答。\n"
        "綜合以下新聞重點與KPIs，輸出JSON："
        "{\"thesis\":str,\"drivers\":[str],\"risks\":[str],\"positioning\":[str],\"metrics_to_watch\":[str],\"timeframe\":str,\"expected_move_pct\":number,\"confidence\":1-5}.\n"
        "避免明確下單指令與保證語句。\n\n"
        f"KPIs: {'; '.join(kpi_lines) if kpi_lines else '(無)'}\n"
        f"News bullets:\n{chr(10).join(bullets) if bullets else '(無)'}\n"
    )
    return call_gateway(
        None,
        messages + [{"role": "user", "content": prompt}],
        model,
        timeout_s,
        dry_run,
        category="fin_analysis",
        llm_log_path=None,
        api_key=api_key,
    )

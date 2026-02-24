from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

try:
    import yfinance as yf
except Exception:  # pragma: no cover - fallback when yfinance missing
    yf = None  # type: ignore


CHINESE_RE = re.compile(r'[\u4e00-\u9fff]')


def _symbol_candidates(ticker: str) -> List[str]:
    """Expand bare ticker to possible Yahoo suffix combos."""
    base = (ticker or '').strip()
    if not base:
        return []
    candidates = [base]
    if base.isdigit() and not base.endswith('.TW'):
        candidates.append(f"{base}.TW")
        candidates.append(f"{base}.TWO")
    elif base.endswith('.TW'):
        candidates.append(base.replace('.TW', '.TWO'))
    return list(dict.fromkeys(candidates))


def _clean_company_name(name: Optional[str], ticker: str) -> str:
    """Strip repeated ticker strings + generic words from company names."""
    if not name:
        return ''
    cleaned = name.strip()
    if not cleaned:
        return ''
    cleaned = re.sub(r'\s+', ' ', cleaned)
    base = (ticker or '').split('.')[0]
    if base:
        base_re = re.escape(base)
        cleaned = re.sub(rf'[（(]\s*{base_re}(?:\.[A-Z]+)?\s*[)）]', ' ', cleaned, flags=re.I)
        cleaned = re.sub(rf'{base_re}(?:\.[A-Z]+)?', ' ', cleaned, flags=re.I)
    cleaned = cleaned.strip(' -–—')
    low = cleaned.lower()
    if any(bad in low for bad in ["yahoo", "股市", "奇摩", "行情", "指數"]):
        return ''
    return cleaned


def _extract_chinese_from_html(html: str, ticker: str) -> Optional[str]:
    """Search Yahoo HTML for localized names to display in UI."""
    from html import unescape
    patterns = [
        r'<h1[^>]*>(.*?)</h1>',
        r'<h2[^>]*>(.*?)</h2>',
        r'"companyName"\s*:\s*"(.*?)"',
        r'"shortName"\s*:\s*"(.*?)"',
        r'"longName"\s*:\s*"(.*?)"',
    ]
    for pattern in patterns:
        try:
            matches = re.findall(pattern, html, flags=re.S | re.I)
        except re.error:
            continue
        for raw in matches:
            text = re.sub(r'<[^>]+>', '', raw)
            text = unescape(text).strip()
            if not text or not CHINESE_RE.search(text):
                continue
            cleaned = _clean_company_name(text, ticker)
            if cleaned:
                return cleaned
    return None


def _fetch_yahoo_company_name(symbol: str, ticker: str) -> Optional[str]:
    """Fetch Yahoo quote page to find a Chinese alias when APIs lack it."""
    try:
        import httpx
    except Exception:
        return None
    paths = []
    base = (symbol or '').split('.')[0]
    if symbol:
        paths.append(symbol)
    if base:
        paths.extend([base, f"{base}.TW", f"{base}.TWO"])
    seen: set[str] = set()
    for ref in paths:
        if not ref or ref in seen:
            continue
        seen.add(ref)
        url = f"https://tw.stock.yahoo.com/quote/{ref}"
        try:
            with httpx.Client(timeout=6.0, headers={"User-Agent": "Mozilla/5.0"}) as client:
                resp = client.get(url)
                if resp.status_code != 200:
                    continue
                name = _extract_chinese_from_html(resp.text, ticker or ref)
                if name:
                    return name
        except Exception:
            continue
    return None


def _choose_company_name(candidates: List[Optional[str]], ticker: str) -> Optional[str]:
    """Pick the best name, preferring Chinese text then Yahoo fallback."""
    normalized: List[str] = []
    for raw in candidates:
        cleaned = _clean_company_name(raw, ticker)
        if cleaned:
            normalized.append(cleaned)
    for name in normalized:
        if CHINESE_RE.search(name):
            return name
    yahoo_hint = candidates[-1] if candidates else ticker
    yahoo_name = _fetch_yahoo_company_name(yahoo_hint, ticker)
    if yahoo_name:
        return yahoo_name
    return normalized[0] if normalized else ((ticker or '').strip() or None)


def _safe_info(ticker_obj: Any) -> Dict[str, Any]:
    """Defensively unwrap yfinance info dictionaries."""
    for attr in ("info", "get_info"):
        getter = getattr(ticker_obj, attr, None)
        if getter:
            try:
                result = getter() if callable(getter) else getter
                if isinstance(result, dict) and result:
                    return result
            except Exception:
                continue
    return {}


def _build_kpis(fast: Dict[str, Any], info: Dict[str, Any]) -> Dict[str, Any]:
    """Assemble the KPI dictionary used elsewhere in the agent."""
    kpis: Dict[str, Any] = {}
    currency = fast.get('currency') or info.get('currency')
    price = fast.get('last_price') or fast.get('lastClose') or fast.get('last_close') or info.get('regularMarketPrice')
    prev = fast.get('previous_close') or fast.get('regular_market_previous_close') or info.get('previousClose')
    if price is not None:
        kpis['price'] = price
        if currency:
            kpis['currency'] = currency
    if prev is not None:
        kpis['prev_close'] = prev
    if price is not None and prev:
        kpis['change'] = price - prev
        if prev:
            try:
                kpis['change_percent'] = (price - prev) / prev * 100
            except Exception:
                pass
    for key_src, key_dst in [
        ('open', 'open'),
        ('day_high', 'day_high'),
        ('day_low', 'day_low'),
        ('regular_market_day_high', 'day_high'),
        ('regular_market_day_low', 'day_low'),
    ]:
        val = fast.get(key_src)
        if val is not None:
            kpis[key_dst] = val
    volume = fast.get('last_volume') or fast.get('volume') or info.get('regularMarketVolume')
    if volume is not None:
        kpis['volume'] = volume
    avg_vol = fast.get('average_volume') or fast.get('three_month_average_volume') or info.get('averageDailyVolume3Month')
    if avg_vol is not None:
        kpis['avg_volume_3m'] = avg_vol
    if info.get('marketCap') is not None:
        kpis['market_cap'] = info.get('marketCap')
    if info.get('forwardPE') is not None:
        kpis['pe_fwd'] = info.get('forwardPE')
    if info.get('dividendYield') is not None:
        try:
            dy = float(info['dividendYield'])
            kpis['dividend_yield_pct'] = dy * 100 if dy < 1 else dy
        except Exception:
            pass
    return {k: v for k, v in kpis.items() if v is not None}


def _build_analysis(kpis: Dict[str, Any]) -> Dict[str, Any]:
    """Derive narrative-ready drivers/risks from raw KPIs."""
    drivers: List[str] = []
    risks: List[str] = []
    positioning: List[str] = []
    metrics_to_watch: List[str] = []

    change_pct = kpis.get('change_percent')
    if isinstance(change_pct, (int, float)):
        if change_pct >= 1:
            drivers.append('短線動能偏多，價格動能 > +1%')
        elif change_pct <= -1:
            risks.append('價格壓力，短線跌幅 > 1%')
    pe_fwd = kpis.get('pe_fwd')
    if isinstance(pe_fwd, (int, float)):
        if pe_fwd <= 18:
            drivers.append('Forward P/E 偏低，估值具吸引力')
        elif pe_fwd >= 25:
            risks.append('估值溢價，需留意修正風險')
    yield_pct = kpis.get('dividend_yield_pct')
    if isinstance(yield_pct, (int, float)) and yield_pct > 1:
        drivers.append(f'殖利率約 {yield_pct:.1f}%，提供下檔保護')
    volume = kpis.get('volume')
    avg_vol = kpis.get('avg_volume_3m')
    if isinstance(volume, (int, float)) and isinstance(avg_vol, (int, float)) and avg_vol > 0:
        ratio = volume / avg_vol
        if ratio >= 1.3:
            drivers.append('量能高於 3M 平均，可能有買盤進場')
        elif ratio <= 0.7:
            risks.append('量能趨緩，需留意信心不足')

    if not positioning:
        positioning.append('逢回承接：靠近支撐佈局，守前低/季線')
    metrics_to_watch.extend(['法人籌碼', '台幣匯率', '晶圓代工報價'])

    thesis = drivers[0] if drivers else '短線等待催化與成交量確認方向。'

    analysis = {
        'drivers': drivers,
        'risks': risks,
        'positioning': positioning,
        'metrics_to_watch': metrics_to_watch,
        'thesis': thesis,
        'confidence': 3,
        'timeframe': '1個月',
    }

    change_abs = abs(change_pct) if isinstance(change_pct, (int, float)) else None
    if change_abs is not None:
        analysis['expected_move_pct'] = round(max(1.5, min(8.0, change_abs * 2)), 2)
    return analysis


def _normalize_ticker(ticker: str) -> str:
    """Ensure we always request TW suffix when user passes digits only."""
    t = (ticker or '').strip()
    if not t:
        return t
    if t.isdigit() and '.TW' not in t and '.TWO' not in t:
        return t + '.TW'
    return t


def _fetch_snapshot(ticker: str) -> Dict[str, Any]:
    """Try multiple symbol variants to return KPIs + localized company name."""
    if not ticker or yf is None:  # pragma: no cover - network dependency
        return {}
    for symbol in _symbol_candidates(ticker):
        try:
            t = yf.Ticker(symbol)
            fast = getattr(t, 'fast_info', {}) or {}
            info = _safe_info(t)
            kpis = _build_kpis(fast, info)
            if not kpis:
                continue
            analysis = _build_analysis(kpis)
            candidates = [
                info.get('shortName'),
                info.get('longName'),
                info.get('displayName'),
                info.get('symbol'),
                symbol,
            ]
            company = _choose_company_name(candidates, ticker)
            return {
                'symbol': symbol,
                'company_name': company,
                'kpis': kpis,
                'analysis': analysis,
            }
        except Exception:
            continue
    return {}


def _fetch_intraday_prices(ticker: str) -> Dict[str, Dict[str, Any]]:
    """Simplified snapshot of current price/volume fields."""
    if yf is None:
        return {}
    try:
        tk = yf.Ticker(_normalize_ticker(ticker))
        info = getattr(tk, "info", {}) or {}
        kpis: Dict[str, Any] = {}
        if info.get("regularMarketPrice") is not None:
            kpis["price"] = info.get("regularMarketPrice")
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


def _fetch_price_series(ticker: str, period: str = "1mo", interval: str = "1d") -> Dict[str, Dict[str, Any]]:
    """Download price history for trader indicators with lightweight cleanup."""
    if yf is None:
        return {}
    try:
        tk = yf.Ticker(_normalize_ticker(ticker))
        hist = tk.history(period=period, interval=interval)
        closes = []
        highs = []
        lows = []
        try:
            closes = [float(x) for x in hist["Close"].tolist() if x is not None]
            if "High" in hist.columns:
                highs = [float(x) for x in hist["High"].tolist() if x is not None]
            if "Low" in hist.columns:
                lows = [float(x) for x in hist["Low"].tolist() if x is not None]
        except Exception:
            pass
        out: Dict[str, Any] = {"close": closes[-60:]}
        if highs:
            out["high"] = highs[-60:]
        if lows:
            out["low"] = lows[-60:]
        prev_day_high = None
        prev_day_low = None
        try:
            if len(highs) >= 2:
                prev_day_high = highs[-2]
            if len(lows) >= 2:
                prev_day_low = lows[-2]
        except Exception:
            prev_day_high = None
            prev_day_low = None
        if prev_day_high is not None or prev_day_low is not None:
            out["prev_day_high"] = prev_day_high
            out["prev_day_low"] = prev_day_low
        return {"series": out} if closes else {}
    except Exception:
        return {}


class YFinanceAgent:
    """Yahoo Finance data helper (prices, KPIs, Chinese names)."""

    def fetch_snapshot(self, ticker: str) -> Dict[str, Any]:
        """Return KPIs + analysis summary if yfinance succeeds."""
        return _fetch_snapshot(ticker)

    def fetch_intraday_kpis(self, ticker: str) -> Dict[str, Dict[str, Any]]:
        """Expose intraday-only helper for orchestrator."""
        return _fetch_intraday_prices(ticker)

    def fetch_price_series(self, ticker: str, period: str = "1mo", interval: str = "1d") -> Dict[str, Dict[str, Any]]:
        """Expose yfinance history fetch for trader agent consumption."""
        return _fetch_price_series(ticker, period, interval)


__all__ = ["YFinanceAgent"]

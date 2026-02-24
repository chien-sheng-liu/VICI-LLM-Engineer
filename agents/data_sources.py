from __future__ import annotations

from typing import Any, Dict, Optional


def _normalize_ticker(ticker: str) -> str:
    """Ensure numeric tickers point to TW exchanges for yfinance."""
    t = (ticker or '').strip()
    if not t:
        return t
    if t.isdigit() and '.TW' not in t and '.TWO' not in t:
        return t + '.TW'
    return t


def fetch_yfinance_data(ticker: str) -> Dict[str, Dict[str, Any]]:
    """Fetch OHLC, Volume, and basic financials via yfinance (optional).

    Returns a dict with partial updates:
      {
        "kpis": { "open":..., "day_high":..., "day_low":..., "prev_close":..., "volume":..., "avg_volume_3m":...,
                   "market_cap":..., "pe_ttm":..., "pe_fwd":..., "pb":..., "dividend_yield_pct":... },
        "finance_basic": { "revenue":..., "gross_margin_pct":..., "operating_margin_pct":..., "profit_margin_pct":...,
                            "roe_pct":..., "roa_pct":..., "ebitda":..., "revenue_growth_pct":..., "earnings_growth_pct":... }
      }

    If yfinance or network is unavailable, returns {}.
    """
    try:
        import yfinance as yf  # type: ignore
    except Exception:
        return {}

    try:
        tk = yf.Ticker(_normalize_ticker(ticker))
        info = getattr(tk, "info", {}) or {}
        out_kpis: Dict[str, Any] = {}
        out_fin: Dict[str, Any] = {}

        # Price + OHLC + Volume
        out_kpis["price"] = info.get("regularMarketPrice")
        out_kpis["open"] = info.get("regularMarketOpen")
        out_kpis["day_high"] = info.get("regularMarketDayHigh")
        out_kpis["day_low"] = info.get("regularMarketDayLow")
        out_kpis["prev_close"] = info.get("regularMarketPreviousClose")
        out_kpis["volume"] = info.get("regularMarketVolume")
        out_kpis["avg_volume_3m"] = (
            info.get("averageVolume")
            or info.get("averageVolume3Month")
            or info.get("averageDailyVolume3Month")
        )

        # Basic valuation
        out_kpis["market_cap"] = info.get("marketCap")
        out_kpis["pe_ttm"] = info.get("trailingPE")
        out_kpis["pe_fwd"] = info.get("forwardPE")
        out_kpis["pb"] = info.get("priceToBook")
        dy = info.get("dividendYield")
        if isinstance(dy, (int, float)):
            out_kpis["dividend_yield_pct"] = dy * 100 if dy < 1 else dy

        # Financials (margins / growth)
        def as_pct(x: Any) -> Optional[float]:
            try:
                fx = float(x)
                return fx * 100 if fx <= 1 else fx
            except Exception:
                return None

        out_fin["revenue"] = info.get("totalRevenue")
        for key_in, key_out in [
            ("grossMargins", "gross_margin_pct"),
            ("operatingMargins", "operating_margin_pct"),
            ("profitMargins", "profit_margin_pct"),
            ("returnOnEquity", "roe_pct"),
            ("returnOnAssets", "roa_pct"),
            ("earningsGrowth", "earnings_growth_pct"),
            ("revenueGrowth", "revenue_growth_pct"),
        ]:
            v = as_pct(info.get(key_in))
            if v is not None:
                out_fin[key_out] = v
        if info.get("ebitda") is not None:
            out_fin["ebitda"] = info.get("ebitda")

        updates: Dict[str, Dict[str, Any]] = {}
        if any(v is not None for v in out_kpis.values()):
            updates["kpis"] = out_kpis
        if any(v is not None for v in out_fin.values()):
            updates["finance_basic"] = out_fin
        return updates
    except Exception:
        return {}

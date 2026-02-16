from __future__ import annotations

from typing import Any, Dict, List, Optional


def _ema(values: List[float], span: int) -> List[float]:
    if not values or span <= 1:
        return values[:]
    k = 2.0 / (span + 1)
    ema: List[float] = []
    for i, v in enumerate(values):
        if i == 0:
            ema.append(v)
        else:
            ema.append(v * k + ema[-1] * (1 - k))
    return ema


def _rsi(values: List[float], period: int = 14) -> Optional[float]:
    if not values or len(values) < period + 1:
        return None
    gains: List[float] = []
    losses: List[float] = []
    for i in range(1, len(values)):
        ch = values[i] - values[i - 1]
        gains.append(max(0.0, ch))
        losses.append(max(0.0, -ch))
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def compute_signals(price_series: List[float], kpis: Dict[str, Any]) -> Dict[str, Any]:
    signals: Dict[str, Any] = {}
    insights: List[str] = []
    if not price_series or len(price_series) < 5:
        return {"signals": signals, "insights": insights}

    closes = [float(x) for x in price_series if isinstance(x, (int, float))]
    if len(closes) < 5:
        return {"signals": signals, "insights": insights}

    # Moving averages
    sma5 = sum(closes[-5:]) / 5.0 if len(closes) >= 5 else None
    sma20 = sum(closes[-20:]) / 20.0 if len(closes) >= 20 else None
    ema12 = _ema(closes, 12)
    ema26 = _ema(closes, 26)
    macd = None
    macd_sig = None
    macd_hist = None
    if len(ema12) == len(closes) and len(ema26) == len(closes):
        macd_line = [a - b for a, b in zip(ema12, ema26)]
        sig_line = _ema(macd_line, 9)
        macd = macd_line[-1]
        macd_sig = sig_line[-1]
        macd_hist = macd - macd_sig
    rsi14 = _rsi(closes, 14)

    # Volatility (simple stdev of daily returns)
    rets: List[float] = []
    for i in range(1, len(closes)):
        p0, p1 = closes[i - 1], closes[i]
        if p0 > 0:
            rets.append((p1 / p0) - 1.0)
    vol = None
    if rets:
        try:
            import statistics
            vol = statistics.pstdev(rets) * 100.0
        except Exception:
            pass

    price = float(kpis.get("price") or closes[-1])
    volume = kpis.get("volume")
    avg_vol = kpis.get("avg_volume_3m")
    vol_ratio = None
    if isinstance(volume, (int, float)) and isinstance(avg_vol, (int, float)) and avg_vol > 0:
        vol_ratio = float(volume) / float(avg_vol)

    signals.update({
        "price": price,
        "sma5": sma5,
        "sma20": sma20,
        "rsi14": rsi14,
        "macd": macd,
        "macd_signal": macd_sig,
        "macd_hist": macd_hist,
        "volatility_pct": vol,
        "volume_ratio": vol_ratio,
    })

    # Insights
    if sma5 and sma20:
        if sma5 > sma20:
            insights.append("短均線高於長均線，趨勢偏多（SMA5>SMA20）")
        elif sma5 < sma20:
            insights.append("短均線低於長均線，趨勢偏空（SMA5<SMA20）")
    if isinstance(rsi14, (int, float)):
        if rsi14 >= 70:
            insights.append("RSI>70，動能偏強但短線需留意過熱")
        elif rsi14 <= 30:
            insights.append("RSI<30，動能偏弱但短線反彈機率提升")
    if isinstance(macd_hist, (int, float)):
        if macd_hist > 0:
            insights.append("MACD 柱體為正，短線動能偏多")
        elif macd_hist < 0:
            insights.append("MACD 柱體為負，短線動能偏空")
    if isinstance(vol_ratio, (int, float)):
        if vol_ratio >= 1.5:
            insights.append(f"量能放大（{vol_ratio:.2f}x 3M），留意趨勢延續/反轉訊號")
        elif vol_ratio <= 0.7:
            insights.append(f"量能低迷（{vol_ratio:.2f}x 3M），短線波動可能收斂")
    if isinstance(vol, (int, float)):
        insights.append(f"近月波動約 {vol:.2f}%；建議以分段/均倉控管風險")

    # Scoring breakdown
    trend_score = 0.0
    momentum_score = 0.0
    volume_score = 0.0
    try:
        # Trend: SMA cross
        if sma5 and sma20:
            # normalized distance contributes
            dist = (sma5 - sma20) / sma20 if sma20 else 0.0
            trend_score = 0.5 + max(-0.5, min(0.5, dist))
        # Momentum: RSI neutral range and MACD histogram sign
        if isinstance(rsi14, (int, float)):
            if 40 <= rsi14 <= 60:
                momentum_score += 0.3
            elif rsi14 > 60:
                momentum_score += 0.15
            else:
                momentum_score += 0.0
        if isinstance(macd_hist, (int, float)):
            momentum_score += 0.3 if macd_hist > 0 else -0.3
        # Volume: prefer 0.8–1.5x of 3M
        if isinstance(vol_ratio, (int, float)):
            if 0.8 <= vol_ratio <= 1.5:
                volume_score = 0.4
            elif vol_ratio > 1.5:
                volume_score = 0.2
            else:
                volume_score = 0.1
    except Exception:
        pass

    composite = max(1, min(5, int(round(3 + trend_score + momentum_score + volume_score))))
    signals.update({
        "trend_score": round(trend_score, 2),
        "momentum_score": round(momentum_score, 2),
        "volume_score": round(volume_score, 2),
        "composite_score": composite,
    })
    # Confidence heuristic aligns with composite
    signals["confidence"] = composite

    return {"signals": signals, "insights": insights}

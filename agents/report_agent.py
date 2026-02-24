from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

CallGateway = Callable[[Optional[str], List[Dict[str, str]], str, float, bool, str, Optional[Any], Optional[str]], Dict[str, Any]]


class ReportAgent:
    """Produces a holistic research narrative that fuses KPIs, news, and trader context."""

    def __init__(self, call_gateway: CallGateway) -> None:
        self._call_gateway = call_gateway

    def generate(
        self,
        *,
        ticker: str,
        company: Optional[str],
        source: Optional[str],
        kpis: Dict[str, Any],
        fin_analysis: Dict[str, Any],
        trader_signals: Optional[Dict[str, Any]],
        watch_items: List[Dict[str, Any]],
        news_summary: Optional[str],
        news_insights: List[str],
        news_micro: List[Dict[str, Any]],
        model: str,
        timeout_s: float,
        dry_run: bool,
        api_key: Optional[str],
    ) -> Dict[str, Any]:
        """Call gateway with a structured prompt for final Markdown report."""
        kpi_lines: List[str] = []
        for key, label in [
            ("price", "Price"),
            ("change_percent", "Change %"),
            ("market_cap", "Market Cap"),
            ("pe_fwd", "Fwd PE"),
            ("dividend_yield_pct", "Yield %"),
            ("gross_margin_pct", "Gross Margin %"),
        ]:
            val = kpis.get(key)
            if val is None:
                continue
            kpi_lines.append(f"{label}: {val}")
        news_lines: List[str] = []
        for item in news_micro[:8]:
            title = str(item.get("title") or "")[:160]
            summary = str(item.get("summary") or "")[:200]
            sentiment = item.get("sentiment") or "中性"
            news_lines.append(f"- {title} ｜ {summary} ｜ Sentiment: {sentiment}")
        trader_lines: List[str] = []
        if trader_signals:
            for key, label in [
                ("trend_score", "Trend"),
                ("momentum_score", "Momentum"),
                ("volume_score", "Volume"),
                ("volatility_pct", "Volatility %"),
            ]:
                val = trader_signals.get(key)
                if val is not None:
                    trader_lines.append(f"{label}: {val}")
        drivers = fin_analysis.get("drivers") if isinstance(fin_analysis, dict) else None
        risks = fin_analysis.get("risks") if isinstance(fin_analysis, dict) else None
        prompt = (
            "請作為資深研究主管（繁體中文）撰寫一份完整研究報告摘要，結構包含：\n"
            "1) Executive Summary（50-80字）\n"
            "2) 財務與交易觀點（Drivers / Risks / Positioning），避免下單指令與保證語句\n"
            "3) KPI & Valuation 觀察\n"
            "4) News + Catalysts（合併上述新聞與洞見）\n"
            "5) Watchlist 與行動建議（僅列出觀測重點，不要出現進出場價格）\n"
            "請以 Markdown 輸出，使用段落與條列混合呈現。\n\n"
            f"Ticker: {ticker}\n公司: {company or '(未取得)'}\n來源: {source or '(未指定)'}\n"
            f"Fin Analysis: {fin_analysis}\n"
            f"Drivers: {drivers}\nRisks: {risks}\n"
            f"KPIs: {'; '.join(kpi_lines) if kpi_lines else '(無)'}\n"
            f"Trader Signals: {'; '.join(trader_lines) if trader_lines else '(無)'}\n"
            f"Watch Items: {watch_items}\n"
            f"News Summary: {news_summary or '(無)'}\n"
            f"News Insights: {news_insights}\n"
            f"News Items:\n{chr(10).join(news_lines) if news_lines else '(無)'}\n"
        )
        messages = [
            {"role": "system", "content": "你是首席台股研究總監，需整合財務、新聞與交易資訊，輸出繁體中文Markdown報告。"},
            {"role": "user", "content": prompt},
        ]
        return self._call_gateway(
            None,
            messages,
            model,
            timeout_s,
            dry_run,
            category="report_agent",
            llm_log_path=None,
            api_key=api_key,
        )


__all__ = ["ReportAgent"]

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional


CallGateway = Callable[[Optional[str], List[Dict[str, str]], str, float, bool, str, Optional[Any], Optional[str]], Dict[str, Any]]


class FinanceAgent:
    """LLM-facing finance/trader analysis agent."""

    def __init__(self, call_gateway: CallGateway) -> None:
        self._call_gateway = call_gateway

    def generate_sentiment(self, messages, model, timeout_s, dry_run, api_key):
        return self._call_gateway(
            None,
            messages + [{"role": "user", "content": "判斷市場情緒（正向/中性/負向）與驚喜程度（超預期/符合/低於），簡短繁體中文回答。"}],
            model,
            timeout_s,
            dry_run,
            category="sentiment",
            llm_log_path=None,
            api_key=api_key,
        )

    def trader_insights(self, messages, model, timeout_s, dry_run, api_key):
        return self._call_gateway(
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

    def overview_bullets(self, messages, model, timeout_s, dry_run, api_key):
        return self._call_gateway(
            None,
            messages + [{"role": "user", "content": "請撰寫一份最新的股票研究摘要（繁體中文），包含：1) 可交易但不涉及執行指令的重點要點、2) 事件時間線、3) 核心結論與需要留意的風險。"}],
            model,
            timeout_s,
            dry_run,
            category="bullets",
            llm_log_path=None,
            api_key=api_key,
        )

    def watchlist(self, messages, model, timeout_s, dry_run, api_key):
        return self._call_gateway(
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

    def analyze_financials(self, news_micro: List[Dict[str, Any]], kpis: Dict[str, Any], messages, model, timeout_s, dry_run, api_key):
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
        return self._call_gateway(
            None,
            messages + [{"role": "user", "content": prompt}],
            model,
            timeout_s,
            dry_run,
            category="fin_analysis",
            llm_log_path=None,
            api_key=api_key,
        )

    def analyze_kpi_impact(self, micro: Dict[str, Any], kpis: Dict[str, Any], messages, model, timeout_s, dry_run, api_key):
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
        return self._call_gateway(
            None,
            messages + [{"role": "user", "content": prompt}],
            model,
            timeout_s,
            dry_run,
            category="kpi_impact",
            llm_log_path=None,
            api_key=api_key,
        )


__all__ = ["FinanceAgent"]

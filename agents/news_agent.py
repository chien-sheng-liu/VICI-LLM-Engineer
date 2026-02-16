from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Tuple

from .scoring import combine_confidence


CallGateway = Callable[[Optional[str], List[Dict[str, str]], str, float, bool, str, Optional[Any], Optional[str]], Dict[str, Any]]


class NewsAgent:
    """Encapsulates news collection + summarization responsibilities."""

    def __init__(self, call_gateway: Optional[CallGateway] = None) -> None:
        self._call_gateway = call_gateway

    def bind_gateway(self, call_gateway: CallGateway) -> None:
        self._call_gateway = call_gateway

    def collect(
        self,
        ticker: str,
        base_url: Optional[str],
        logs_dir,
        dry_run: bool,
        company_name: Optional[str] = None,
    ) -> List[Dict[str, str]]:
        return _collect_news(ticker, base_url, logs_dir, dry_run, company_name)

    def summarize_item(
        self,
        system_msgs: List[Dict[str, str]],
        item: Dict[str, Any],
        model: str,
        timeout_s: float,
        dry_run: bool,
        api_key: Optional[str],
    ) -> Tuple[Dict[str, Any], Optional[str], int]:
        if not self._call_gateway:
            raise RuntimeError("NewsAgent requires a call_gateway for summarization")
        return _summarize_single_news(self._call_gateway, system_msgs, item, model, timeout_s, dry_run, api_key)

    def enrich_events(
        self,
        events: Optional[List[Dict[str, Any]]],
        micro_items: List[Dict[str, Any]],
        snapshot_kpis: Optional[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        return _enrich_or_build_events(events, micro_items, snapshot_kpis)


def _summarize_single_news(
    call_gateway: CallGateway,
    system_msgs: List[Dict[str, str]],
    item: Dict[str, Any],
    model: str,
    timeout_s: float,
    dry_run: bool,
    api_key: Optional[str],
) -> Tuple[Dict[str, Any], Optional[str], int]:
    """Summarize one news item to 1–2 sentence note, return (micro, request_id, latency_ms)."""
    title_i = item.get("title", "")
    ctx = f"{title_i[:200]} | {item.get('source','')} | {item.get('time','')} | {item.get('url','')}"
    prompt = (
        "請僅輸出JSON，包含：title、url、summary(1-2句)、"
        "sentiment(正向|中性|負向)、market_note(對股價/估值/籌碼的簡短說明)、type(事件|指引|風險)、confidence(1-5)。\n"
        "避免投資建議與保證語句。\n\n新聞：" + ctx
    )
    try:
        resp = call_gateway(
            None,  # gateway is included in call_gateway closure
            system_msgs + [{"role": "user", "content": prompt}],
            model,
            timeout_s,
            dry_run,
            category="news_item",
            llm_log_path=None,
            api_key=api_key,
        )
        rid = resp.get("request_id")
        latency = int(resp.get("latency_ms") or 0)
        parsed = _parse_json(resp.get("text"))
        if isinstance(parsed, dict):
            llm_conf = parsed.get("confidence")
            micro = {
                "title": parsed.get("title") or title_i,
                "url": parsed.get("url") or item.get("url"),
                "summary": (parsed.get("summary") or title_i).strip(),
                "sentiment": parsed.get("sentiment") or "中性",
                "market_note": parsed.get("market_note") or "",
                "type": parsed.get("type") or "事件",
                "confidence": combine_confidence(llm_conf, item),
            }
        else:
            micro = {
                "title": title_i,
                "url": item.get("url"),
                "summary": title_i,
                "sentiment": "中性",
                "market_note": "",
                "type": "事件",
                "confidence": combine_confidence(None, item),
            }
        return micro, rid, latency
    except Exception:
        micro = {
            "title": title_i,
            "url": item.get("url"),
            "summary": title_i,
            "sentiment": "中性",
            "market_note": "",
            "type": "事件",
            "confidence": combine_confidence(None, item),
        }
        return micro, None, 0


def _parse_json(text: Optional[str]) -> Optional[Any]:
    if not text:
        return None
    s = text.strip()
    if s.startswith("```"):
        s = s.strip("`")
    try:
        import json
        i = s.find("{")
        j = s.rfind("}")
        if i != -1 and j != -1 and j > i:
            return json.loads(s[i : j + 1])
    except Exception:
        return None
    return None


def _enrich_or_build_events(
    events: Optional[List[Dict[str, Any]]],
    micro_items: List[Dict[str, Any]],
    snapshot_kpis: Dict[str, Any] | None,
) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    snapshot_kpis = snapshot_kpis or {}

    if not events:
        for it in micro_items:
            out.append(
                {
                    "time": it.get("time") or it.get("date") or it.get("when"),
                    "type": it.get("type") or "事件",
                    "title": it.get("title"),
                    "summary": it.get("summary"),
                    "impact": {"facets": ["營收", "毛利"], "direction": it.get("sentiment") or "中性"},
                    "sentiment": it.get("sentiment") or "中性",
                    "market_note": it.get("market_note") or "",
                    "confidence": it.get("confidence") or 3,
                    "url": it.get("url"),
                    "linked_kpis": [k for k in (snapshot_kpis.keys())][:2],
                }
            )
        return _dedup_events(out)

    # enrich
    def _norm(s: str) -> str:
        import re
        return re.sub(r"\s+", "", re.sub(r"[^\w\u4e00-\u9fa5]", "", (s or "").lower()))

    out = list(events)
    for ev in out:
        et = _norm(ev.get("title") or "")
        if not et:
            continue
        for it in micro_items:
            mt = _norm(it.get("title") or "")
            if not mt:
                continue
            if mt in et or et in mt:
                if it.get("summary") and it.get("summary").strip() != (ev.get("title") or ""):
                    ev["summary"] = it.get("summary").strip()
                if it.get("sentiment"):
                    ev["sentiment"] = it.get("sentiment")
                if it.get("market_note"):
                    ev["market_note"] = it.get("market_note")
                if it.get("confidence"):
                    ev["confidence"] = it.get("confidence")
                if it.get("url"):
                    ev["url"] = it.get("url")
                if it.get("kpi_impact"):
                    ev["kpi_impact"] = it.get("kpi_impact")
                break
    return _dedup_events(out)


def _dedup_events(events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    def _norm_t(s: str) -> str:
        import re
        return re.sub(r"\s+", "", re.sub(r"[^\w\u4e00-\u9fa5]", "", (s or "").lower()))
    uniq: list[dict] = []
    seen: set[str] = set()
    for ev in events:
        t = _norm_t(ev.get("title") or "")
        if not t or t in seen:
            continue
        seen.add(t)
        if ev.get("summary") and str(ev["summary"]).strip() == str(ev.get("title") or ""):
            ev["summary"] = ""
        uniq.append(ev)
    return uniq


# News collection (moved from orchestrator for modularity)
def _collect_news(ticker: str, base_url: Optional[str], logs_dir, dry_run: bool, company_name: Optional[str] = None) -> List[Dict[str, str]]:
    import json
    from pathlib import Path
    news_path = Path(logs_dir) / "news.json"
    if dry_run:
        items = [
            {"title": f"{ticker} beats expectations in Q2", "url": f"https://tw.stock.yahoo.com/quote/{ticker}/news", "time": _now_iso()},
            {"title": f"Analysts raise guidance for {ticker}", "url": f"https://tw.stock.yahoo.com/quote/{ticker}/news", "time": _now_iso()},
        ]
        news_path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
        return items

    def parse_links(html: str) -> List[Dict[str, str]]:
        from urllib.parse import unquote, urlparse
        results: List[Dict[str, str]] = []
        idx = 0
        while len(results) < 5 and idx < len(html):
            start = html.find('href="', idx)
            if start == -1:
                break
            end = html.find('"', start + 6)
            if end == -1:
                break
            href = html[start + 6:end]
            idx = end + 1
            if '/news/' not in href:
                continue
            url = href if href.startswith('http') else ('https://tw.stock.yahoo.com' + href)
            tail = url.split('/')[-1]
            title = unquote(tail).replace('-', ' ').split('?')[0][:160] or url
            host = urlparse(url).netloc
            source = 'Yahoo' if 'yahoo' in host else host
            results.append({"title": title, "url": url, "time": _now_iso(), "source": source})
        return results

    candidates: List[str] = []
    if base_url and "tw.stock.yahoo.com" in base_url:
        root = "https://tw.stock.yahoo.com"
        candidates = [f"{root}/quote/{ticker}/news", f"{root}/quote/{ticker}.TW/news"]
    else:
        candidates = [f"https://tw.stock.yahoo.com/quote/{ticker}/news", f"https://tw.stock.yahoo.com/quote/{ticker}.TW/news"]

    q = f"{company_name or ''} {ticker} 最新 新聞".strip()
    items: List[Dict[str, str]] = _collect_news_google(q, logs_dir) if q else []
    try:
        import httpx

        with httpx.Client(timeout=10.0) as client:
            for url in candidates:
                try:
                    resp = client.get(url)
                    if resp.status_code != 200:
                        continue
                    parsed = parse_links(resp.text)
                    if parsed:
                        existing = {it['url'] for it in items}
                        for it in parsed:
                            if it['url'] not in existing:
                                items.append(it)
                        break
                except Exception:
                    continue
    except Exception:
        pass

    if not items:
        items = [
            {"title": f"{ticker} update", "url": f"https://tw.stock.yahoo.com/quote/{ticker}/news", "time": _now_iso()},
        ]
    news_path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    return items


def _collect_news_google(query: str, logs_dir, lang: str = "zh-TW") -> List[Dict[str, str]]:
    try:
        from urllib.parse import unquote, urlparse, quote_plus
        import httpx
        import re

        url = f"https://www.google.com/search?tbm=nws&hl={lang}&q={quote_plus(query)}"
        with httpx.Client(timeout=10.0, headers={"User-Agent": "Mozilla/5.0"}) as client:
            r = client.get(url)
            if r.status_code != 200:
                return []
            html = r.text
            results: List[Dict[str, str]] = []
            idx = 0
            while len(results) < 6 and idx < len(html):
                i = html.find('<a href="', idx)
                if i == -1:
                    break
                j = html.find('"', i + 9)
                if j == -1:
                    break
                href = html[i + 9:j]
                idx = j + 1
                if href.startswith('/url?q='):
                    href = href[7:]
                    href = href.split('&', 1)[0]
                if not href.startswith('http'):
                    continue
                h3s = html.find('<h3', j)
                title = None
                if h3s != -1:
                    h3e = html.find('</h3>', h3s)
                    if h3e != -1 and (h3e - h3s) < 400:
                        title = re.sub(r'<[^>]+>', ' ', html[h3s:h3e]).strip()
                if not title:
                    tail = href.split('/')[-1]
                    title = unquote(tail).replace('-', ' ').split('?')[0][:160]
                host = urlparse(href).netloc
                source = host.split(':')[0]
                window = html[j:j+400]
                approx_time = _relative_time_to_iso(window)
                category = _classify_source(host)
                if title:
                    results.append({
                        "title": title,
                        "url": href,
                        "time": approx_time or _now_iso(),
                        "source": source,
                        "category": category,
                    })
            uniq: List[Dict[str, str]] = []
            seen: set[str] = set()
            for it in results:
                if it['url'] in seen:
                    continue
                seen.add(it['url'])
                uniq.append(it)
            return uniq[:6]
    except Exception:
        return []


__all__ = ["NewsAgent"]


def _relative_time_to_iso(window: str) -> Optional[str]:
    import re
    from datetime import timedelta, datetime, timezone
    m = re.search(r'(\d+)\s*(小時|小時前|天|天前|週|週前)', window)
    if not m:
        return None
    n = int(m.group(1))
    unit = m.group(2)
    delta = None
    if '小時' in unit:
        delta = timedelta(hours=n)
    elif '天' in unit:
        delta = timedelta(days=n)
    elif '週' in unit:
        delta = timedelta(weeks=n)
    if not delta:
        return None
    return (datetime.now(timezone.utc) - delta).isoformat()


def _classify_source(host: str) -> str:
    host_l = host.lower()
    domestic = [
        'yahoo.com.tw', 'tw.stock.yahoo.com', 'cnyes.com', 'moneydj.com', 'udn.com', 'money.udn.com',
        'technews.tw', 'bnext.com.tw', 'ltn.com.tw', 'storm.mg', 'ctee.com.tw', 'cmmedia.com.tw', 'chinatimes.com'
    ]
    international = ['reuters.com', 'bloomberg.com', 'ft.com', 'wsj.com', 'nytimes.com', 'cnbc.com']
    brokers = ['morganstanley', 'goldmansachs', 'jpmorgan', 'ubs', 'barclays', 'nomura', 'credit-suisse', 'bofa', 'citigroup', 'hsbc']
    if any(d in host_l for d in brokers):
        return 'broker'
    if any(d in host_l for d in domestic):
        return 'domestic'
    if any(d in host_l for d in international):
        return 'international'
    return 'other'


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()

"""
Root Orchestrator (agent.py)

- Required to live at repo root (per assignment) as the standalone CLI/workflow entry.
- Loads modular sub‑agents from `agents/`:
  * agents.news_agent: per‑news micro summaries + event enrichment
  * agents.finance_agent: sentiment, trader insights, overview, watchlist
  * agents.scoring: confidence combiner
- Provides a unified `call_gw` wrapper so sub‑agents call the FastAPI gateway consistently.
"""

from __future__ import annotations

import argparse
import hashlib
import uuid
import json
import os
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx
from dotenv import load_dotenv

load_dotenv()

# Externalized agent modules
try:
    from agents import news_agent, finance_agent
    from agents.scoring import combine_confidence
except Exception:
    news_agent = None  # type: ignore
    finance_agent = None  # type: ignore
    def combine_confidence(llm_conf: Optional[float], news: Dict[str, str]) -> int:  # fallback
        return int(llm_conf or 3)


@dataclass
class AgentArgs:
    ticker: str
    source: str
    gateway: Optional[str]
    model: str
    out_dir: Path
    dry_run: bool
    timeout_s: float
    openai_api_key: Optional[str] = None
    yahoo: bool = False


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_dirs(base: Path) -> Dict[str, Path]:
    outputs = base / "outputs"
    logs = base / "run_logs"
    shots = logs / "screenshots"
    outputs.mkdir(parents=True, exist_ok=True)
    shots.mkdir(parents=True, exist_ok=True)
    return {"outputs": outputs, "logs": logs, "shots": shots}


def _load_sample_html() -> str:
    # Load the built-in sample IR HTML from backend/static/sample_ir.html
    here = Path(__file__).resolve().parent
    sample = here / "backend" / "static" / "sample_ir.html"
    if sample.exists():
        return sample.read_text(encoding="utf-8")
    # Fallback minimal sample
    return "<html><body><h1>Sample IR</h1><table><tr><th>Time</th><th>Event</th><th>Guidance</th><th>Risk</th></tr><tr><td>2026-02-15</td><td>Q2</td><td>FY Rev Up</td><td>FX</td></tr></table></body></html>"


def _write_minimal_pdf(path: Path, title: str, body: str, sections: Optional[List[tuple[str, str]]] = None) -> None:
    # Minimal single-page PDF with basic text using plain bytes
    # This is not fancy, but valid enough for artifact purposes
    # naive text placements, special chars stripped
    safe = lambda s: s.replace("(", "[").replace(")", "]").replace("\n", " ")
    y = 720
    lines = [f"BT /F1 24 Tf 72 {y} Td ({safe(title)}) Tj ET"]
    y -= 36
    if sections:
        for head, text in sections:
            lines.append(f"BT /F1 16 Tf 72 {y} Td ({safe(head)}) Tj ET")
            y -= 24
            lines.append(f"BT /F1 12 Tf 72 {y} Td ({safe(text)[:200]}) Tj ET")
            y -= 24
            if y < 100:
                # keep simple: stop if overflow
                break
    else:
        lines.append(f"BT /F1 12 Tf 72 {y} Td ({safe(body)[:200]}) Tj ET")
    content = " ".join(lines)
    stream = content.encode("latin-1", "ignore")
    pdf_parts = [
        b"%PDF-1.4\n",
        b"1 0 obj <</Type /Catalog /Pages 2 0 R>> endobj\n",
        b"2 0 obj <</Type /Pages /Kids [3 0 R] /Count 1>> endobj\n",
        b"3 0 obj <</Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources <</Font <</F1 5 0 R>>>> /Contents 4 0 R>> endobj\n",
        b"4 0 obj <</Length %d>> stream\n" % (len(stream),),
        stream + b"\nendstream endobj\n",
        b"5 0 obj <</Type /Font /Subtype /Type1 /BaseFont /Helvetica>> endobj\n",
    ]
    xref_positions: List[int] = []
    with path.open("wb") as f:
        pos = 0
        for part in pdf_parts:
            xref_positions.append(pos)
            f.write(part)
            pos += len(part)
        xref_start = pos
        f.write(b"xref\n0 6\n0000000000 65535 f \n")
        # there are 5 objects (1..5) recorded above
        for p in xref_positions:
            f.write(f"{p:010d} 00000 n \n".encode("ascii"))
        f.write(b"trailer <</Size 6/Root 1 0 R>>\nstartxref\n")
        f.write(str(xref_start).encode("ascii") + b"\n%%EOF\n")


def _write_1x1_png(path: Path) -> None:
    # A minimal valid 1x1 transparent PNG
    data = bytes.fromhex(
        "89504E470D0A1A0A0000000D49484452000000010000000108060000001F15C4890000000A49444154789C6360000002000154A6F2660000000049454E44AE426082"
    )
    path.write_bytes(data)


def _sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _extract_evidence(content_html: Optional[str]) -> str:
    if not content_html:
        return ""
    import re
    text = content_html
    # Remove script/style blocks robustly
    text = re.sub(r"(?is)<script[^>]*>.*?</script>", " ", text)
    text = re.sub(r"(?is)<style[^>]*>.*?</style>", " ", text)
    # Normalize line breaks for block closures
    text = (
        text.replace("<br>", "\n")
        .replace("<br/>", "\n")
        .replace("</p>", "\n")
        .replace("</div>", "\n")
    )
    # Strip remaining tags
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    # Remove typical JS noise remnants
    text = re.sub(r"window\.[^\n]+", " ", text)
    text = re.sub(r"YAHOO\.[^\n]+", " ", text)
    text = re.sub(r"\bi13n\.[^\n]+", " ", text)
    text = re.sub(r"\bfunction\b[^\n]*", " ", text)
    text = re.sub(r"\bJsEnabled\b|\bNoJs\b", " ", text)
    # Collapse whitespace
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return ""
    return (text[:300] + ("…" if len(text) > 300 else ""))


def _extract_table(content_html: Optional[str]) -> List[Dict[str, str]]:
    if not content_html:
        return []
    # naive table extraction: look for <table> and first few rows
    import re

    tables = re.findall(r"<table[\s\S]*?</table>", content_html, flags=re.I)
    rows_out: List[Dict[str, str]] = []
    for t in tables:
        # headers
        headers = re.findall(r"<th[^>]*>([\s\S]*?)</th>", t, flags=re.I)
        headers = [re.sub(r"<[^>]+>", " ", h).strip().lower() for h in headers]
        if not headers:
            # try first row as headers
            first_row = re.search(r"<tr[\s\S]*?</tr>", t, flags=re.I)
            if first_row:
                headers = [
                    re.sub(r"<[^>]+>", " ", c).strip().lower()
                    for c in re.findall(r"<t[dh][^>]*>([\s\S]*?)</t[dh]>", first_row.group(0), flags=re.I)
                ]
        # capture up to 5 data rows
        for m in re.finditer(r"<tr[\s\S]*?</tr>", t, flags=re.I):
            cells = [
                re.sub(r"<[^>]+>", " ", c).strip()
                for c in re.findall(r"<t[dh][^>]*>([\s\S]*?)</t[dh]>", m.group(0), flags=re.I)
            ]
            if not cells or cells == headers:
                continue
            row = {}
            for i, v in enumerate(cells):
                key = headers[i] if i < len(headers) else f"col{i+1}"
                row[key] = v
            if row:
                rows_out.append(row)
            if len(rows_out) >= 5:
                break
        if rows_out:
            break
    return rows_out


def _extract_meta_snippet(content_html: Optional[str]) -> Optional[str]:
    if not content_html:
        return None
    import re
    m = re.search(r'<meta[^>]+property=["\']og:description["\'][^>]+content=["\']([^"\']+)["\']', content_html, flags=re.I)
    if m:
        return m.group(1).strip()
    m = re.search(r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']+)["\']', content_html, flags=re.I)
    if m:
        return m.group(1).strip()
    return None


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


def _relative_time_to_iso(label: str) -> Optional[str]:
    import re
    from datetime import timedelta
    m = re.search(r'(\d+)\s*(小時|小時前|天|天前|週|週前)', label)
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
    from datetime import datetime, timezone
    return (datetime.now(timezone.utc) - delta).isoformat()

def _polish_llm_text(text: Optional[str], fallback: str) -> str:
    if not text:
        return fallback
    cleaned = text.strip()
    if not cleaned:
        return fallback
    if cleaned.startswith("[OPENAI SIM]"):
        return fallback
    if "window.performance" in cleaned or cleaned.lower().startswith("(none"):
        return fallback
    return cleaned


def _parse_json_from_text(text: Optional[str]) -> Optional[Any]:
    if not text:
        return None
    s = text.strip()
    # remove fences
    if s.startswith('```'):
        s = s.strip('`')
    # try find first { and last }
    try:
        start = s.find('{')
        end = s.rfind('}')
        if start != -1 and end != -1 and end > start:
            import json as _json
            return _json.loads(s[start:end+1])
    except Exception:
        return None
    return None


def _extract_yahoo_snapshot(html: Optional[str], ticker: str) -> Dict[str, Any]:
    if not html:
        return {}
    try:
        import re
        # Yahoo embeds a JSON blob: root.App.main = {...};
        match = re.search(r"root\\.App\\.main\s*=\s*(\{.*?\});", html, flags=re.S)
        if not match:
            return {}
        data = json.loads(match.group(1))
        stores = data.get("context", {}).get("dispatcher", {}).get("stores", {})
        summary_store = stores.get("QuoteSummaryStore", {})
        price = summary_store.get("price", {})
        summary_detail = summary_store.get("summaryDetail", {})
        financial_data = summary_store.get("financialData", {})
        analysis: List[str] = []
        table_rows: List[Dict[str, str]] = []
        kpis: Dict[str, Any] = {}
        name = price.get("longName") or price.get("shortName") or ticker
        if price.get("regularMarketPrice") is not None:
            change = price.get("regularMarketChange")
            percent = price.get("regularMarketChangePercent")
            if isinstance(change, (int, float)) and isinstance(percent, (int, float)):
                change_str = f"{change:+.2f} ({percent:+.2f}%)"
            else:
                change_str = price.get("regularMarketChangePercent") or ""
            line = f"{name} 最新股價 {price.get('regularMarketPrice')} {price.get('currency') or ''} {change_str}"
            analysis.append(line.strip())
            table_rows.append({"指標": "最新股價", "數值": line.split("最新股價", 1)[-1].strip()})
            kpis["price"] = price.get('regularMarketPrice')
            kpis["currency"] = price.get('currency')
            kpis["change"] = change
            kpis["change_percent"] = percent
        if summary_detail.get("fiftyTwoWeekRange"):
            table_rows.append({"指標": "52週區間", "數值": summary_detail.get("fiftyTwoWeekRange")})
        if summary_detail.get("regularMarketDayRange"):
            table_rows.append({"指標": "日內區間", "數值": summary_detail.get("regularMarketDayRange")})
        if financial_data.get("targetMeanPrice"):
            table_rows.append({"指標": "法人平均目標價", "數值": str(financial_data.get("targetMeanPrice"))})
            kpis["target_mean_price"] = financial_data.get("targetMeanPrice")
        if financial_data.get("recommendationKey"):
            table_rows.append({"指標": "法人建議", "數值": financial_data.get("recommendationKey")})
            kpis["recommendation"] = financial_data.get("recommendationKey")
        if financial_data.get("numberOfAnalystOpinions"):
            table_rows.append({"指標": "分析師覆蓋", "數值": str(financial_data.get("numberOfAnalystOpinions"))})
        if financial_data.get("grossMargins") is not None:
            try:
                gm = float(financial_data['grossMargins']) * 100
                table_rows.append({"指標": "毛利率", "數值": f"{gm:.1f}%"})
                kpis["gross_margin_pct"] = gm
            except Exception:
                pass
        earnings = summary_store.get("earnings", {}).get("financialsChart", {}).get("quarterly", [])
        if earnings:
            last = earnings[-1]
            if last.get("actual") is not None:
                table_rows.append({"指標": "最新季度EPS", "數值": str(last.get("actual"))})
                kpis["latest_eps"] = last.get("actual")
        if not analysis and table_rows:
            analysis.append(" | ".join([f"{row['指標']} {row['數值']}" for row in table_rows[:2]]))
        # Derive missing KPIs from table if needed
        if not kpis and table_rows:
            for row in table_rows:
                key = row.get("指標", "")
                val = row.get("數值", "")
                try:
                    if key == "最新股價":
                        import re as _re
                        m = _re.search(r"([0-9]+(?:\.[0-9]+)?)", val)
                        if m:
                            kpis["price"] = float(m.group(1))
                        pm = _re.search(r"([+-]?[0-9]+(?:\.[0-9]+)?)%", val)
                        if pm:
                            kpis["change_percent"] = float(pm.group(1))
                    elif key == "毛利率":
                        if "%" in val:
                            kpis["gross_margin_pct"] = float(val.replace('%','').strip())
                    elif key == "法人平均目標價":
                        kpis["target_mean_price"] = float(val)
                    elif key == "最新季度EPS":
                        kpis["latest_eps"] = float(val)
                except Exception:
                    continue
        return {"text": "\n".join(analysis), "table": table_rows, "kpis": kpis, "name": name}
    except Exception:
        return {}


def _collect_news_google(query: str, logs_dir: Path, lang: str = "zh-TW") -> List[Dict[str, str]]:
    from urllib.parse import unquote, urlparse, quote_plus
    try:
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
                # Try to grab a nearby <h3> as title
                h3s = html.find('<h3', j)
                title = None
                if h3s != -1:
                    h3e = html.find('</h3>', h3s)
                    if h3e != -1 and (h3e - h3s) < 400:
                        import re
                        title = re.sub(r'<[^>]+>', ' ', html[h3s:h3e]).strip()
                if not title:
                    tail = href.split('/')[-1]
                    title = unquote(tail).replace('-', ' ').split('?')[0][:160]
                host = urlparse(href).netloc
                source = host.split(':')[0]
                # try to find relative time nearby
                window = html[j:j+400]
                approx_time = None
                rt = _relative_time_to_iso(window)
                if rt:
                    approx_time = rt
                category = _classify_source(host)
                if title:
                    results.append({"title": title, "url": href, "time": approx_time or _now_iso(), "source": source, "category": category})
            uniq, seen = [], set()
            for it in results:
                if it['url'] in seen:
                    continue
                seen.add(it['url'])
                uniq.append(it)
            return uniq[:6]
    except Exception:
        return []


def _collect_news(ticker: str, base_url: Optional[str], logs_dir: Path, dry_run: bool, company_name: Optional[str] = None) -> List[Dict[str, str]]:
    news_path = logs_dir / "news.json"
    if dry_run:
        items = [
            {"title": f"{ticker} beats expectations in Q2", "url": f"https://tw.stock.yahoo.com/quote/{ticker}/news", "time": _now_iso()},
            {"title": f"Analysts raise guidance for {ticker}", "url": f"https://tw.stock.yahoo.com/quote/{ticker}/news", "time": _now_iso()},
        ]
        news_path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
        return items

    def parse_links(html: str) -> List[Dict[str, str]]:
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
            # decode readable title from URL tail
            from urllib.parse import unquote, urlparse
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

    # Google News first
    q = f"{company_name or ''} {ticker} 最新 新聞".strip()
    items: List[Dict[str, str]] = _collect_news_google(q, logs_dir) if q else []
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

    if not items:
        items = [
            {"title": f"{ticker} update", "url": f"https://tw.stock.yahoo.com/quote/{ticker}/news", "time": _now_iso()},
        ]
    news_path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    return items


def _fetch_and_capture(source: str, shots_dir: Path, logs_dir: Path, dry_run: bool) -> Dict[str, Any]:
    started = time.perf_counter()
    # Special scheme for embedded sample
    if source.startswith("sample://"):
        p = shots_dir / "1.png"
        _write_1x1_png(p)
        import zipfile

        trace_path = logs_dir / "trace.zip"
        with zipfile.ZipFile(trace_path, "w") as z:
            z.writestr("meta.json", json.dumps({"source": source}))
        console_path = logs_dir / "console.log"
        console_path.write_text("[sample] using embedded IR page\n", encoding="utf-8")
        return {
            "screenshot": str(p),
            "trace": str(trace_path),
            "content_html": _load_sample_html(),
            "console_log": str(console_path),
            "url": "sample://ir",
            "latency_ms": int((time.perf_counter() - started) * 1000),
        }
    if dry_run:
        p = shots_dir / "1.png"
        _write_1x1_png(p)
        # create minimal trace zip
        import zipfile

        trace_path = logs_dir / "trace.zip"
        with zipfile.ZipFile(trace_path, "w") as z:
            z.writestr("trace.txt", "dry-run trace")
        console_path = logs_dir / "console.log"
        console_path.write_text("[dry-run] console log\n", encoding="utf-8")
        return {
            "screenshot": str(p),
            "trace": str(trace_path),
            "content_html": "<html><body><h1>Dry Run</h1><p>Example content for testing.</p></body></html>",
            "console_log": str(console_path),
            "latency_ms": int((time.perf_counter() - started) * 1000),
        }

    # Attempt real Playwright browsing; optional dependency
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            context = browser.new_context()
            # tracing
            try:
                context.tracing.start(screenshots=True, snapshots=True)
            except Exception:
                pass
            console_lines: List[str] = []
            page = context.new_page()
            page.on("console", lambda msg: console_lines.append(msg.text()))
            page.goto(source, timeout=30000)
            page.wait_for_load_state("load")
            content_html = page.content()
            shot_path = shots_dir / "1.png"
            page.screenshot(path=str(shot_path))
            console_path = logs_dir / "console.log"
            console_path.write_text("\n".join(console_lines), encoding="utf-8")
            # export trace
            trace_path = logs_dir / "trace.zip"
            try:
                context.tracing.stop(path=str(trace_path))
            except Exception:
                import zipfile
                with zipfile.ZipFile(trace_path, "w") as z:
                    z.writestr("meta.json", json.dumps({"url": source}))
            browser.close()
        return {
            "screenshot": str(shot_path),
            "trace": str(trace_path),
            "content_html": content_html,
            "console_log": str(console_path),
            "url": source,
            "latency_ms": int((time.perf_counter() - started) * 1000),
        }
    except Exception as e:
        # Fallback: try raw HTTP fetch for HTML to enable extraction, and produce minimal artifacts
        p = shots_dir / "1.png"
        _write_1x1_png(p)
        import zipfile

        trace_path = logs_dir / "trace.zip"
        with zipfile.ZipFile(trace_path, "w") as z:
            z.writestr("trace.txt", f"fallback due to: {e}")
        console_path = logs_dir / "console.log"
        console_lines = [f"[fallback] {e}"]
        content_html: Optional[str] = None
        try:
            with httpx.Client(timeout=10.0) as client:
                r = client.get(source)
                if r.status_code == 200 and "text" in r.headers.get("content-type", "text"):
                    content_html = r.text
                    console_lines.append("[fallback] fetched HTML via HTTP")
        except Exception as e2:
            console_lines.append(f"[fallback-http] {e2}")
        console_path.write_text("\n".join(console_lines) + "\n", encoding="utf-8")
        return {
            "screenshot": str(p),
            "trace": str(trace_path),
            "content_html": content_html,
            "console_log": str(console_path),
            "url": source,
            "latency_ms": int((time.perf_counter() - started) * 1000),
        }


def _fetch_yahoo_tw(ticker: str, shots_dir: Path, logs_dir: Path, dry_run: bool) -> Dict[str, Any]:
    started = time.perf_counter()
    base = "https://tw.stock.yahoo.com"
    target_url = f"{base}/"
    if dry_run:
        # Produce deterministic artifacts with reference to Yahoo page
        p = shots_dir / "1.png"
        _write_1x1_png(p)
        import zipfile
        trace_path = logs_dir / "trace.zip"
        with zipfile.ZipFile(trace_path, "w") as z:
            z.writestr("meta.json", json.dumps({"url": target_url, "ticker": ticker}))
        console_path = logs_dir / "console.log"
        console_path.write_text(f"[yahoo-dry-run] {ticker}\n", encoding="utf-8")
        html = f"<html><body><h1>Yahoo TW {ticker}</h1><table><tr><th>Time</th><th>Event</th><th>Guidance</th><th>Risk</th></tr><tr><td>2026-02-15</td><td>Earnings</td><td>Raised</td><td>FX</td></tr></table></body></html>"
        snapshot = {
            "text": f"{ticker} 模擬股價 600 TWD，請以實際資料為準。",
            "table": [
                {"指標": "模擬股價", "數值": "600 TWD"},
                {"指標": "法人建議", "數值": "buy"},
            ],
        }
        return {
            "screenshot": str(p),
            "trace": str(trace_path),
            "content_html": html,
            "console_log": str(console_path),
            "url": target_url,
            "snapshot_text": snapshot["text"],
            "snapshot_table": snapshot["table"],
            "latency_ms": int((time.perf_counter() - started) * 1000),
        }
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            context = browser.new_context()
            try:
                context.tracing.start(screenshots=True, snapshots=True)
            except Exception:
                pass
            console_lines: List[str] = []
            page = context.new_page()
            page.on("console", lambda msg: console_lines.append(msg.text()))
            page.goto(target_url, timeout=40000)
            # Attempt to locate search input and submit ticker with multiple selectors
            did_search = False
            selectors = [
                'input#yfin-usr-qry',
                'input[aria-label*="搜尋"]',
                'input[placeholder*="搜尋"]',
                'input[aria-label*="Search"]',
                'input[placeholder*="Search"]',
                'input[type="search"]',
                'input[name="query"]',
                'form[role="search"] input',
            ]
            for sel in selectors:
                try:
                    locator = page.locator(sel).first
                    if locator.count() > 0:
                        locator.fill(ticker)
                        page.keyboard.press("Enter")
                        did_search = True
                        break
                except Exception:
                    continue
            # Wait for navigation to a quote page
            try:
                page.wait_for_url("**/quote/**", timeout=10000)
                target_url = page.url
            except Exception:
                # fallback direct navigate
                guess = [f"{base}/quote/{ticker}", f"{base}/quote/{ticker}.TW"]
                for u in guess:
                    try:
                        page.goto(u, timeout=20000)
                        target_url = u
                        break
                    except Exception:
                        continue
            page.wait_for_load_state("load")
            content_html = page.content()
            snapshot = _extract_yahoo_snapshot(content_html, ticker)
            shot_path = shots_dir / "1.png"
            page.screenshot(path=str(shot_path), full_page=True)
            console_path = logs_dir / "console.log"
            console_path.write_text("\n".join(console_lines), encoding="utf-8")
            trace_path = logs_dir / "trace.zip"
            try:
                context.tracing.stop(path=str(trace_path))
            except Exception:
                import zipfile
                with zipfile.ZipFile(trace_path, "w") as z:
                    z.writestr("meta.json", json.dumps({"url": target_url, "ticker": ticker, "did_search": did_search}))
            browser.close()
        return {
            "screenshot": str(shot_path),
            "trace": str(trace_path),
            "content_html": content_html,
            "console_log": str(console_path),
            "url": target_url,
            "snapshot_text": snapshot.get("text"),
            "snapshot_table": snapshot.get("table"),
            "snapshot_kpis": snapshot.get("kpis"),
            "company_name": snapshot.get("name"),
            "latency_ms": int((time.perf_counter() - started) * 1000),
        }
    except Exception as e:
        # HTTP fallback
        import zipfile
        p = shots_dir / "1.png"
        _write_1x1_png(p)
        console_path = logs_dir / "console.log"
        lines = [f"[yahoo-fallback] {e}"]
        content_html: Optional[str] = None
        snapshot = {}
        for u in [f"{base}/quote/{ticker}", f"{base}/quote/{ticker}.TW"]:
            try:
                with httpx.Client(timeout=10.0) as client:
                    r = client.get(u)
                    if r.status_code == 200 and "text" in r.headers.get("content-type", "text"):
                        content_html = r.text
                        target_url = u
                        snapshot = _extract_yahoo_snapshot(content_html, ticker)
                        lines.append(f"fetched: {u}")
                        break
            except Exception as ee:
                lines.append(str(ee))
        console_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        trace_path = logs_dir / "trace.zip"
        with zipfile.ZipFile(trace_path, "w") as z:
            z.writestr("meta.json", json.dumps({"url": target_url, "ticker": ticker}))
        return {
            "screenshot": str(p),
            "trace": str(trace_path),
            "content_html": content_html,
            "console_log": str(console_path),
            "url": target_url,
            "snapshot_text": snapshot.get("text"),
            "snapshot_table": snapshot.get("table"),
            "snapshot_kpis": snapshot.get("kpis"),
            "company_name": snapshot.get("name"),
            "latency_ms": int((time.perf_counter() - started) * 1000),
        }


def _call_gateway(
    gateway: Optional[str], messages: List[Dict[str, str]], model: str, timeout_s: float, dry_run: bool, category: str, llm_log_path: Optional[Path], api_key: Optional[str]
) -> Dict[str, Any]:
    if dry_run or not gateway:
        rid = f"dry-run-{category}-{uuid.uuid4().hex[:8]}"
        resp = {
            "request_id": rid,
            "provider": "mock",
            "model": model,
            "latency_ms": 1,
            "retry_count": 0,
            "text": f"[DRY-RUN] {category} result based on extracted content.",
            "usage": {"prompt_tokens": 10, "completion_tokens": 8, "total_tokens": 18},
        }
        if llm_log_path:
            with llm_log_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps({"category": category, **resp}) + "\n")
        return resp
    url = gateway.rstrip("/") + "/v1/chat/completions"
    payload = {"model": model, "messages": messages, "max_tokens": 256, "temperature": 0.2}
    started = time.perf_counter()
    headers = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    with httpx.Client(timeout=timeout_s, headers=headers) as client:
        r = client.post(url, json=payload)
        r.raise_for_status()
        data = r.json()
        text = data["choices"][0]["message"]["content"]
        resp = {
            "request_id": data.get("request_id"),
            "provider": data.get("provider"),
            "model": data.get("model"),
            "latency_ms": data.get("latency_ms", int((time.perf_counter() - started) * 1000)),
            "retry_count": data.get("retry_count", 0),
            "text": text,
            "usage": data.get("usage", {}),
        }
        if llm_log_path:
            with llm_log_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps({"category": category, **resp}) + "\n")
        return resp


def run(args: AgentArgs) -> Dict[str, Any]:
    dirs = _ensure_dirs(args.out_dir)
    outputs, logs, shots = dirs["outputs"], dirs["logs"], dirs["shots"]

    steps: List[Dict[str, Any]] = []
    t0 = time.perf_counter()

    # Step 1: browse and capture
    s0 = time.perf_counter()
    if args.yahoo:
        nav = _fetch_yahoo_tw(args.ticker, shots, logs, dry_run=args.dry_run)
        steps.append({"name": "yahoo_browse", "latency_ms": int((time.perf_counter() - s0) * 1000)})
    else:
        nav = _fetch_and_capture(args.source, shots, logs, dry_run=args.dry_run)
        steps.append({"name": "browse", "latency_ms": int((time.perf_counter() - s0) * 1000)})

    # Step 2: extract content
    sE = time.perf_counter()
    evidence = _extract_evidence(nav.get("content_html"))
    meta_snip = _extract_meta_snippet(nav.get("content_html"))
    if meta_snip:
        evidence = f"{meta_snip}\n{evidence}" if evidence else meta_snip
    snapshot_text = nav.get("snapshot_text")
    snapshot_table = nav.get("snapshot_table") or []
    snapshot_kpis = nav.get("snapshot_kpis") or {}
    if snapshot_text:
        evidence = f"{snapshot_text}\n{evidence}" if evidence else snapshot_text
    table = snapshot_table + _extract_table(nav.get("content_html"))
    steps.append({"name": "extract", "latency_ms": int((time.perf_counter() - sE) * 1000)})

    # Step 2b: collect news via news_agent
    sN = time.perf_counter()
    if news_agent:
        news_items = news_agent.collect_news(args.ticker, nav.get("url"), logs, dry_run=args.dry_run, company_name=nav.get("company_name"))
    else:
        news_items = _collect_news(args.ticker, nav.get("url"), logs, dry_run=args.dry_run, company_name=nav.get("company_name"))
    steps.append({"name": "news", "latency_ms": int((time.perf_counter() - sN) * 1000), "count": len(news_items)})

    # Step 2c: suggest additional sources (MOPS / IR / others)
    source_suggestions = [
        {"title": "MOPS 公開資訊觀測站", "url": "https://mops.twse.com.tw/mops/web/index"},
        {"title": "MOPS 公司基本資料/重大訊息", "url": "https://mops.twse.com.tw/mops/web/t05st01"},
        {"title": "TWSE 市場公告", "url": "https://www.twse.com.tw/announcement"},
        {"title": "櫃買中心公告", "url": "https://www.tpex.org.tw/web/bulletin/"},
    ]
    if args.ticker:
        source_suggestions.extend([
            {"title": f"Yahoo 個股新聞 {args.ticker}", "url": f"https://tw.stock.yahoo.com/quote/{args.ticker}/news"},
        ])
    if nav.get("company_name"):
        from urllib.parse import quote_plus
        q = quote_plus(f"{nav.get('company_name')} IR")
        source_suggestions.append({"title": "公司 IR（搜尋）", "url": f"https://www.google.com/search?q={q}"})
    # Persist suggestions
    (logs / "sources.json").write_text(json.dumps(source_suggestions, ensure_ascii=False, indent=2), encoding="utf-8")

    # Step 3: LLM calls
    llm_log_path = logs / "llm_calls.jsonl"
    # Provide a unified gateway caller for sub-agents
    def call_gw(_gw, msgs, model, to, dr, category, llm_log_path=None, api_key=None):
        return _call_gateway(args.gateway, msgs, model, to, dr, category, llm_log_path, api_key)
    news_titles = [n.get("title", "") for n in news_items if n.get("title")] 
    news_text = "；".join(news_titles)
    table_highlights = "; ".join([f"{row.get('指標')}: {row.get('數值')}" for row in snapshot_table[:3]])
    context_details = " | ".join(
        filter(
            None,
            [
                snapshot_text,
                table_highlights and f"指標摘要：{table_highlights}",
                news_text and f"新聞：{news_text}",
            ],
        )
    )
    messages = [
        {"role": "system", "content": "你是專業的台灣股市研究分析師，請全程使用繁體中文回答，並針對最新資訊產出可交易但不涉及明確下單指令的研究見解。"},
        {"role": "user", "content": f"股票代號：{args.ticker}。來源內容：{evidence or '無'}"},
        {"role": "user", "content": f"即時指標與新聞：{context_details or '無'}"},
    ]
    # Prepare base system-only messages for news-only tasks to reduce token size
    system_only = [{"role": "system", "content": "你是專業的台灣股市研究分析師，請全程使用繁體中文回答。"}]

    # 3a. Event extraction
    s1 = time.perf_counter()
    try:
        llm_events = _call_gateway(
            args.gateway,
            messages + [{"role": "user", "content": (
                "請輸出JSON，鍵items為陣列；請先整合上述新聞與即時指標，避免重複。每項包含："
                "time(ISO或簡易字串)、type(事件|指引|風險)、title、summary、"
                "sentiment(正向|中性|負向或1-5)、market_note(對股價/估值/籌碼可能之影響)、"
                "impact: {facets: [需求|供給|毛利|營收|EPS|估值], direction: 正向|負向|中性}、"
                "confidence(1-5)、linked_kpis(如: ['gross_margin_pct','price','target_mean_price'])."
                "僅輸出JSON，不要額外說明。"
            )}],
            args.model,
            args.timeout_s,
            args.dry_run,
            category="events",
            llm_log_path=llm_log_path,
            api_key=args.openai_api_key,
        )
    except Exception:
        llm_events = {"request_id": f"fallback-events-{uuid.uuid4().hex[:8]}", "text": "{}", "latency_ms": 0, "retry_count": 0}
    steps.append({"name": "llm_events", "latency_ms": int((time.perf_counter() - s1) * 1000), "request_id": llm_events["request_id"]})

    # 3b. Sentiment / surprise
    s2a = time.perf_counter()
    try:
        if finance_agent:
            llm_sent = finance_agent.analyze_sentiment(
                call_gw,
                messages, args.model, args.timeout_s, args.dry_run, args.openai_api_key,
            )
        else:
            llm_sent = _call_gateway(
                args.gateway,
                messages + [{"role": "user", "content": "判斷市場情緒（正向/中性/負向）與驚喜程度（超預期/符合/低於），簡短繁體中文回答。"}],
                args.model,
                args.timeout_s,
                args.dry_run,
                category="sentiment",
                llm_log_path=llm_log_path,
                api_key=args.openai_api_key,
            )
    except Exception:
        llm_sent = {"request_id": f"fallback-sent-{uuid.uuid4().hex[:8]}", "text": "中性；近期消息影響待觀察", "latency_ms": 0, "retry_count": 0}
    steps.append({"name": "llm_sentiment", "latency_ms": int((time.perf_counter() - s2a) * 1000), "request_id": llm_sent["request_id"]})

    # 3c. Trading-oriented research bullets (no execution advice)
    s2b = time.perf_counter()
    try:
        pass
    except Exception:
        pass
    if finance_agent:
        llm_bullets = finance_agent.overview_bullets(
            call_gw,
            messages, args.model, args.timeout_s, args.dry_run, args.openai_api_key,
        )
    else:
        llm_bullets = _call_gateway(
            args.gateway,
            messages + [{"role": "user", "content": "請撰寫一份最新的股票研究摘要（繁體中文），包含：1) 可交易但不涉及執行指令的重點要點、2) 事件時間線、3) 核心結論與需要留意的風險。"}],
            args.model,
            args.timeout_s,
            args.dry_run,
            category="bullets",
            llm_log_path=llm_log_path,
            api_key=args.openai_api_key,
        )
    # bullets 如要包try/except，可在 finance_agent 中包；這裡保持直通
    # 3c-1. Trader insights (explicit)
    s2b_tr = time.perf_counter()
    if finance_agent:
        llm_trader = finance_agent.trader_insights(
            call_gw,
            messages, args.model, args.timeout_s, args.dry_run, args.openai_api_key,
        )
    else:
        llm_trader = _call_gateway(
            args.gateway,
            messages + [{"role": "user", "content": (
                "以交易員視角（繁體中文）列出3-5點可交易洞見與因果理由，包含可能觸發與風險；"
                "不得出現明確下單指令或保證語句。以條列重點輸出。"
            )}],
            args.model,
            args.timeout_s,
            args.dry_run,
            category="trader",
            llm_log_path=llm_log_path,
            api_key=args.openai_api_key,
        )
    # 3d. Watchlist suggestions
    s2c = time.perf_counter()
    if finance_agent:
        llm_watch = finance_agent.watchlist(
            call_gw,
            messages, args.model, args.timeout_s, args.dry_run, args.openai_api_key,
        )
    else:
        llm_watch = _call_gateway(
            args.gateway,
            messages + [{"role": "user", "content": (
                "請輸出JSON，鍵watch為陣列，每項包含：metric(觀測指標)、rationale(理由)、suggested_check(建議檢核方式或閾值)、priority(1-3)。"
                "僅輸出JSON，不要額外說明。"
            )}],
            args.model,
            args.timeout_s,
            args.dry_run,
            category="watch",
            llm_log_path=llm_log_path,
            api_key=args.openai_api_key,
        )
    steps.append({"name": "llm_watch", "latency_ms": int((time.perf_counter() - s2c) * 1000), "request_id": llm_watch["request_id"]})
    steps.append({"name": "llm_bullets", "latency_ms": int((time.perf_counter() - s2b) * 1000), "request_id": llm_bullets["request_id"]})

    # 3e. News reports: summarize latest 10 news + trader insights
    s2d = time.perf_counter()
    news_context = "\n".join(
        [
            f"- {i+1}. {n.get('title','')[:160]} | {n.get('source','')} | {n.get('time','')} | {n.get('url','')}"
            for i, n in enumerate(news_items[:10])
        ]
    ) or "(無)"
    news_prompt = (
        "根據以下最新新聞（至多10則，已依時間排序）先做整體摘要，然後提供交易員視角的洞見要點。\n"
        "請僅輸出JSON，格式：{\"summary\": \"整體摘要\", \"insights\": [\"重點1\", \"重點2\", ...]}。\n"
        "避免投資建議或保證語句。\n\n" + news_context
    )
    try:
        llm_news = _call_gateway(
            args.gateway,
            system_only + [{"role": "user", "content": news_prompt}],
            args.model,
            args.timeout_s,
            args.dry_run,
            category="news_reports",
            llm_log_path=llm_log_path,
            api_key=args.openai_api_key,
        )
    except Exception:
        llm_news = {"request_id": f"fallback-news-{uuid.uuid4().hex[:8]}", "text": "{\"summary\":\"近期新聞聚焦公司與產業供需\",\"insights\":[\"觀察需求與價格動能\"]}", "latency_ms": 0, "retry_count": 0}
    steps.append({"name": "llm_news_reports", "latency_ms": int((time.perf_counter() - s2d) * 1000), "request_id": llm_news["request_id"]})

    # 3f. Per-news micro summaries to map into events (1-2 sentences each)
    micro_items: list[dict] = []
    micro_ids: list[str] = []
    total_micro_ms = 0
    for i, n in enumerate(news_items[:10]):
        if news_agent:
            micro, rid, lat = news_agent.summarize_single_news(
                call_gw,
                system_only, n, args.model, args.timeout_s, args.dry_run, args.openai_api_key,
            )
            micro_items.append(micro)
            if rid:
                micro_ids.append(rid)
            total_micro_ms += int(lat or 0)
        else:
            # fallback trivial
            micro_items.append({
                "title": n.get('title'),
                "url": n.get('url'),
                "summary": n.get('title'),
                "sentiment": '中性',
                "market_note": '',
                "type": '事件',
                "confidence": 3,
            })
    steps.append({"name": "llm_news_items", "latency_ms": total_micro_ms, "count": len(micro_items)})

    # Step 4: generate artifacts
    s3 = time.perf_counter()
    news_lines = [f"- [{n['title']}]({n['url']}) — {n.get('time', '')}" for n in news_items] or ["(無)"]
    table_lines = ["- " + ", ".join([f"{k}: {v}" for k, v in row.items()]) for row in table] or ["(無)"]
    nav_url = nav.get('url') or args.source
    fallback_events_lines = []
    if snapshot_text:
        fallback_events_lines.append(f"- 即時指標：{snapshot_text}")
    # no snippet section; trader insights will cover actionable bullets
    if news_titles:
        fallback_events_lines.append(f"- 新聞焦點：{'；'.join(news_titles[:2])}")
    fallback_events = "\n".join(fallback_events_lines)
    fallback_sentiment = "市場情緒暫視為中性，惟需持續監控產業供需、法人指引與新聞更新。"
    fallback_summary = "可交易重點：評估新聞與即時指標對營收、毛利與資本支出之影響，設定進出策略與風險控管。"
    polished_events = _polish_llm_text(llm_events.get("text"), fallback_events)
    polished_sent = _polish_llm_text(llm_sent.get("text"), fallback_sentiment)
    polished_summary = _polish_llm_text(llm_bullets.get("text"), fallback_summary)
    polished_trader = _polish_llm_text(llm_trader.get("text"), "- 近期驅動：留意新聞與法說摘要對營收/毛利的邊際變化\n- 風險控管：關鍵KPI走弱與外在總經沖擊")

    # Parse news JSON
    news_summary = None
    news_insights = None
    parsed_news = _parse_json_from_text(llm_news.get("text"))
    if isinstance(parsed_news, dict):
        if isinstance(parsed_news.get('summary'), str):
            news_summary = parsed_news.get('summary')
        if isinstance(parsed_news.get('insights'), list):
            try:
                news_insights = [str(x) for x in parsed_news.get('insights')][:8]
            except Exception:
                news_insights = None
    if not news_summary:
        news_summary = "近期新聞聚焦公司基本面與產業供需變化，需留意法人指引與總體環境。"
    if not news_insights:
        news_insights = [
            "觀察新聞提及之需求變化與價格動能",
            "追蹤法人對目標價/評等之調整",
            "留意政策、地緣風險與匯率影響",
        ]

    # Parse structured JSON for events and watchlist
    events_struct = None
    parsed = _parse_json_from_text(llm_events.get("text"))
    if isinstance(parsed, dict) and isinstance(parsed.get('items'), list):
        events_struct = parsed['items']
    # micro_items already prepared per news above
    watch_items = None
    parsed_w = _parse_json_from_text(llm_watch.get("text"))
    if isinstance(parsed_w, dict) and isinstance(parsed_w.get('watch'), list):
        watch_items = parsed_w['watch']
    # Per-news KPI impact inference (revenue/gross_margin/eps)
    try:
        if finance_agent:
            total_kpi_ms = 0
            for i, m in enumerate(micro_items[:10]):
                resp = finance_agent.analyze_kpi_impact(
                    call_gw, m, snapshot_kpis, messages, args.model, args.timeout_s, args.dry_run, args.openai_api_key
                )
                rid = resp.get("request_id")
                if rid:
                    micro_ids.append(rid)
                total_kpi_ms += int(resp.get("latency_ms") or 0)
                parsed_k = _parse_json_from_text(resp.get("text"))
                if isinstance(parsed_k, dict):
                    m["kpi_impact"] = parsed_k
            steps.append({"name": "llm_kpi_impact", "latency_ms": total_kpi_ms, "count": len(micro_items[:10])})
    except Exception:
        pass
    # Enrich events with per-news micro summaries; or build from micro if none
    def _norm(s: str) -> str:
        import re
        return re.sub(r"[^\w\u4e00-\u9fa5]", "", s.lower())

    if news_agent:
        events_struct = news_agent.enrich_or_build_events(events_struct, micro_items, snapshot_kpis)

    # minimal fallback if still missing -> derive from top news
    if not events_struct:
        events_struct = []
        for i, n in enumerate(news_items[:3] or [{}]):
            titleN = n.get("title") if isinstance(n, dict) else None
            when = n.get("time") if isinstance(n, dict) else None
            events_struct.append({
                "time": when or _now_iso(),
                "type": "事件",
                "title": titleN or (news_titles[0] if news_titles else "最新焦點"),
                "summary": (titleN or "") or (evidence[:140] + ("…" if evidence and len(evidence) > 140 else "")),
                "impact": {"facets": ["營收", "毛利"], "direction": "中性"},
                "sentiment": "中性",
                "market_note": "可能影響估值與籌碼，需留意法人評等與KPI變化",
                "confidence": 3,
                "linked_kpis": [k for k in (snapshot_kpis.keys() if isinstance(snapshot_kpis, dict) else [])][:2],
            })

    # Deduplicate events by normalized title
    if events_struct:
        def _norm_t(s: str) -> str:
            import re
            return re.sub(r"\s+", "", re.sub(r"[^\w\u4e00-\u9fa5]", "", s.lower()))
        uniq: list[dict] = []
        seen: set[str] = set()
        for ev in events_struct:
            t = _norm_t(str(ev.get('title') or ''))
            if not t or t in seen:
                continue
            seen.add(t)
            # Ensure summary not duplicating title
            if ev.get('summary') and str(ev['summary']).strip() == str(ev.get('title') or ''):
                ev['summary'] = ''
            uniq.append(ev)
        events_struct = uniq
    if not watch_items:
        watch_items = [
            {"metric": "毛利率", "rationale": "反映產品組合與成本變動", "suggested_check": "季增/年增 > 50bps", "priority": 2},
            {"metric": "營收YoY", "rationale": "需求回溫與市佔變化", "suggested_check": ">= 10%", "priority": 2},
        ]
    # 3g. Finance/quant analysis based on news + KPIs
    fin_json: Dict[str, Any] | None = None
    try:
        if finance_agent:
            fin_resp = finance_agent.analyze_financials(
                call_gw, micro_items, snapshot_kpis, messages, args.model, args.timeout_s, args.dry_run, args.openai_api_key
            )
            fin_parsed = _parse_json_from_text(fin_resp.get("text"))
            if isinstance(fin_parsed, dict):
                fin_json = fin_parsed
    except Exception:
        fin_json = None

    report_lines = [
        f"# 股票研究報告｜{args.ticker}",
        "",
        f"來源：{nav_url}",
        "",
        "## 財務分析（量化視角）",
        (fin_json.get('thesis') if fin_json else '近期新聞與KPI顯示需關注需求、毛利與法人預期變化。'),
        *( ([""] + ["- 驅動：" + d for d in (fin_json.get('drivers') or [])]) if fin_json and isinstance(fin_json.get('drivers'), list) else []),
        *( ([""] + ["- 風險：" + r for r in (fin_json.get('risks') or [])]) if fin_json and isinstance(fin_json.get('risks'), list) else []),
        *( ([""] + ["- 建議部位/策略：" + p for p in (fin_json.get('positioning') or [])]) if fin_json and isinstance(fin_json.get('positioning'), list) else []),
        *( ([""] + ["- 觀測指標：" + m for m in (fin_json.get('metrics_to_watch') or [])]) if fin_json and isinstance(fin_json.get('metrics_to_watch'), list) else []),
        (f"- 期間：{fin_json.get('timeframe')}｜預期波動：{fin_json.get('expected_move_pct')}%｜信心：{fin_json.get('confidence')}/5" if fin_json else ''),
        "",
        "## 交易員 Insights",
        polished_trader,
        "",
        "## 新聞總結",
        news_summary,
        *( ([""] + ["- " + x for x in news_insights]) if news_insights else [] ),
        "",
        "## 快速摘要",
        polished_summary,
        "",
        "## 事件 / 指引 / 風險",
        polished_events,
        "",
        "## 市場情緒與驚喜判讀",
        polished_sent,
        "",
        "## 自動擷取表格",
        *table_lines,
        "",
        "## 最新新聞",
        *news_lines,
        "",
        "## 產出資訊",
        f"- 模型：{args.model}",
        f"- 生成時間：{_now_iso()}",
    ]
    report_md = outputs / "report.md"
    report_md.write_text("\n".join(report_lines), encoding="utf-8")
    slides_pdf = outputs / "slides.pdf"
    _write_minimal_pdf(
        slides_pdf,
        f"{args.ticker} 最新研究摘要",
        polished_summary,
        sections=[
            ("事件 / 指引 / 風險", polished_events[:200]),
            ("情緒 / 驚喜", polished_sent[:180]),
            ("交易員 Insights", polished_trader[:180]),
            ("新聞重點", (news_text or "無")[:180]),
        ],
    )
    checksums = outputs / "checksums.txt"
    checksums.write_text(
        "\n".join(
            [
                f"{_sha256(report_md)}  report.md",
                f"{_sha256(slides_pdf)}  slides.pdf",
            ]
        )
    )
    steps.append({"name": "artifacts", "latency_ms": int((time.perf_counter() - s3) * 1000)})

    # Step 5: write run.json
    report_sections = {
        "summary": polished_summary,
        "events": polished_events,
        "events_struct": events_struct,
        "sentiment": polished_sent,
        "trader_insights": polished_trader,
        "news_reports": {"summary": news_summary, "insights": news_insights},
        "news_micro": micro_items,
        "fin_analysis": fin_json,
        "table": table,
        "news": news_items,
        "source": nav_url,
        "generated_at": _now_iso(),
        "kpis": snapshot_kpis,
        "watch_items": watch_items,
    }

    run_json = {
        "ticker": args.ticker,
        "source": args.source,
        "model": args.model,
        "steps": steps,
        "timings": {"total_ms": int((time.perf_counter() - t0) * 1000)},
        "artifacts": {
            "report_md": str(report_md),
            "slides_pdf": str(slides_pdf),
            "checksums": str(checksums),
            "screenshot": nav.get("screenshot"),
            "trace": nav.get("trace"),
            "console_log": nav.get("console_log"),
            "llm_calls": str(llm_log_path),
            "news_json": str((logs / "news.json")),
        },
        "request_ids": [
            llm_events.get("request_id"),
            llm_sent.get("request_id"),
            llm_bullets.get("request_id"),
            llm_trader.get("request_id"),
            llm_news.get("request_id"),
            *micro_ids,
        ],
        "latency_summary": {
            "navigation_ms": nav.get("latency_ms"),
            "llm_ms": sum(
                int(x or 0)
                for x in [
                    llm_events.get("latency_ms"),
                    llm_sent.get("latency_ms"),
                    llm_bullets.get("latency_ms"),
                ]
            ),
        },
        "timestamp": _now_iso(),
        "report_sections": report_sections,
    }
    (logs / "run.json").write_text(json.dumps(run_json, indent=2), encoding="utf-8")
    return run_json


def parse_args(argv: Optional[List[str]] = None) -> AgentArgs:
    p = argparse.ArgumentParser(description="Playwright research agent")
    p.add_argument("--ticker", required=True)
    p.add_argument("--source", required=True)
    p.add_argument("--gateway", required=False, default=None)
    p.add_argument("--model", required=False, default=os.getenv("AGENT_MODEL", "mock-01"))
    p.add_argument("--out-dir", required=False, default=".")
    p.add_argument("--dry-run", action="store_true", help="Deterministic mode without external calls")
    p.add_argument("--yahoo", action="store_true", help="Use Yahoo Finance TW automation (ignores source) ")
    p.add_argument("--timeout", type=float, default=float(os.getenv("AGENT_TIMEOUT_S", "15")))
    p.add_argument("--openai-api-key", required=False, default=os.getenv("OPENAI_API_KEY"))
    ns = p.parse_args(argv)
    return AgentArgs(
        ticker=ns.ticker,
        source=ns.source,
        gateway=ns.gateway,
        model=ns.model,
        out_dir=Path(ns.out_dir).resolve(),
        dry_run=bool(ns.dry_run),
        timeout_s=float(ns.timeout),
        openai_api_key=ns.openai_api_key,
        yahoo=bool(ns.yahoo),
    )


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    run(args)
    print(json.dumps({"status": "ok", "out_dir": str(args.out_dir)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())

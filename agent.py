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
        return "No content extracted (dry-run or fetch skipped)."
    # naive text extract
    # strip tags naively
    text = content_html
    for tag in ["script", "style"]:
        # remove simple blocks
        text = text.replace(f"<{tag}", "<removed").replace(f"</{tag}>", "")
    text = (
        text.replace("<br>", "\n")
        .replace("<br/>", "\n")
        .replace("</p>", "\n")
        .replace("</div>", "\n")
    )
    # remove remaining tags
    import re

    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
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
    nav = _fetch_and_capture(args.source, shots, logs, dry_run=args.dry_run)
    steps.append({"name": "browse", "latency_ms": int((time.perf_counter() - s0) * 1000)})

    # Step 2: extract content
    sE = time.perf_counter()
    evidence = _extract_evidence(nav.get("content_html"))
    table = _extract_table(nav.get("content_html"))
    steps.append({"name": "extract", "latency_ms": int((time.perf_counter() - sE) * 1000)})

    # Step 3: LLM calls
    llm_log_path = logs / "llm_calls.jsonl"
    messages = [
        {"role": "system", "content": "You are a research assistant."},
        {"role": "user", "content": f"Ticker: {args.ticker}. Summarize events from source."},
        {"role": "user", "content": evidence or "No evidence."},
    ]
    # 3a. Event extraction
    s1 = time.perf_counter()
    llm_events = _call_gateway(
        args.gateway,
        messages + [{"role": "user", "content": "Extract key events, guidance, and risks. Respond in markdown with sections: Events, Guidance, Risks."}],
        args.model,
        args.timeout_s,
        args.dry_run,
        category="events",
        llm_log_path=llm_log_path,
        api_key=args.openai_api_key,
    )
    steps.append({"name": "llm_events", "latency_ms": int((time.perf_counter() - s1) * 1000), "request_id": llm_events["request_id"]})

    # 3b. Sentiment / surprise
    s2a = time.perf_counter()
    llm_sent = _call_gateway(
        args.gateway,
        messages + [{"role": "user", "content": "Assess sentiment (positive/negative/neutral) and surprise (above/inline/below expectations). Respond briefly."}],
        args.model,
        args.timeout_s,
        args.dry_run,
        category="sentiment",
        llm_log_path=llm_log_path,
        api_key=args.openai_api_key,
    )
    steps.append({"name": "llm_sentiment", "latency_ms": int((time.perf_counter() - s2a) * 1000), "request_id": llm_sent["request_id"]})

    # 3c. Trading-oriented research bullets (no execution advice)
    s2b = time.perf_counter()
    llm_bullets = _call_gateway(
        args.gateway,
        messages + [{"role": "user", "content": "Summarize into actionable research points (no trade instructions). Include timeline and risks."}],
        args.model,
        args.timeout_s,
        args.dry_run,
        category="bullets",
        llm_log_path=llm_log_path,
        api_key=args.openai_api_key,
    )
    steps.append({"name": "llm_bullets", "latency_ms": int((time.perf_counter() - s2b) * 1000), "request_id": llm_bullets["request_id"]})

    # Step 4: generate artifacts
    s3 = time.perf_counter()
    report_md = outputs / "report.md"
    report_md.write_text(
        "\n".join(
            [
                f"# Research Report: {args.ticker}",
                "",
                f"Source: {args.source}",
                "",
                "## Evidence",
                evidence,
                "",
                "## Extracted Table (sample)",
                ("\n".join(["- " + ", ".join([f"{k}: {v}" for k, v in row.items()]) for row in table]) or "(none)"),
                "",
                "## Event Extraction",
                llm_events["text"],
                "",
                "## Sentiment / Surprise",
                llm_sent["text"],
                "",
                "## Summary",
                llm_bullets["text"],
                "",
                f"Timestamp: {_now_iso()}",
            ]
        ),
        encoding="utf-8",
    )
    slides_pdf = outputs / "slides.pdf"
    _write_minimal_pdf(
        slides_pdf,
        f"{args.ticker} Research Summary",
        llm_bullets["text"],
        sections=[
            ("Events", llm_events["text"][:180]),
            ("Sentiment/Surprise", llm_sent["text"][:180]),
            ("Risks", "See report for details."),
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
        },
        "request_ids": [llm_events.get("request_id"), llm_sent.get("request_id"), llm_bullets.get("request_id")],
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
    )


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    run(args)
    print(json.dumps({"status": "ok", "out_dir": str(args.out_dir)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())

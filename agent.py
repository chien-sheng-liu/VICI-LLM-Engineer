from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx


@dataclass
class AgentArgs:
    ticker: str
    source: str
    gateway: Optional[str]
    model: str
    out_dir: Path
    dry_run: bool
    timeout_s: float


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_dirs(base: Path) -> Dict[str, Path]:
    outputs = base / "outputs"
    logs = base / "run_logs"
    shots = logs / "screenshots"
    outputs.mkdir(parents=True, exist_ok=True)
    shots.mkdir(parents=True, exist_ok=True)
    return {"outputs": outputs, "logs": logs, "shots": shots}


def _write_minimal_pdf(path: Path, title: str, body: str) -> None:
    # Minimal single-page PDF with basic text using plain bytes
    # This is not fancy, but valid enough for artifact purposes
    content = f"BT /F1 24 Tf 72 720 Td ({title}) Tj ET BT /F1 12 Tf 72 680 Td ({body[:200]}) Tj ET"
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
    text = content_html.replace("\n", " ").strip()
    return (text[:300] + ("…" if len(text) > 300 else ""))


def _fetch_and_capture(source: str, shots_dir: Path, logs_dir: Path, dry_run: bool) -> Dict[str, Any]:
    started = time.perf_counter()
    if dry_run:
        p = shots_dir / "1.png"
        _write_1x1_png(p)
        # create minimal trace zip
        import zipfile

        trace_path = logs_dir / "trace.zip"
        with zipfile.ZipFile(trace_path, "w") as z:
            z.writestr("trace.txt", "dry-run trace")
        return {
            "screenshot": str(p),
            "trace": str(trace_path),
            "content_html": "<html><body><h1>Dry Run</h1><p>Example content for testing.</p></body></html>",
            "latency_ms": int((time.perf_counter() - started) * 1000),
        }

    # Attempt real Playwright browsing; optional dependency
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            context = browser.new_context()
            page = context.new_page()
            page.goto(source, timeout=30000)
            page.wait_for_load_state("load")
            content_html = page.content()
            shot_path = shots_dir / "1.png"
            page.screenshot(path=str(shot_path))
            # Trace capture minimal
            # (Using context.tracing would require start/stop; skipped for simplicity)
            import zipfile

            trace_path = logs_dir / "trace.zip"
            with zipfile.ZipFile(trace_path, "w") as z:
                z.writestr("meta.json", json.dumps({"url": source}))
            browser.close()
        return {
            "screenshot": str(shot_path),
            "trace": str(trace_path),
            "content_html": content_html,
            "latency_ms": int((time.perf_counter() - started) * 1000),
        }
    except Exception as e:
        # Fallback to dry-run artifacts
        p = shots_dir / "1.png"
        _write_1x1_png(p)
        import zipfile

        trace_path = logs_dir / "trace.zip"
        with zipfile.ZipFile(trace_path, "w") as z:
            z.writestr("trace.txt", f"fallback due to: {e}")
        return {
            "screenshot": str(p),
            "trace": str(trace_path),
            "content_html": None,
            "latency_ms": int((time.perf_counter() - started) * 1000),
        }


def _call_gateway(
    gateway: Optional[str], messages: List[Dict[str, str]], model: str, timeout_s: float, dry_run: bool
) -> Dict[str, Any]:
    if dry_run or not gateway:
        return {
            "request_id": "dry-run-req-0001",
            "provider": "mock",
            "model": model,
            "latency_ms": 1,
            "retry_count": 0,
            "text": "[DRY-RUN] Summary based on extracted content.",
            "usage": {"prompt_tokens": 10, "completion_tokens": 8, "total_tokens": 18},
        }
    url = gateway.rstrip("/") + "/v1/chat/completions"
    payload = {"model": model, "messages": messages, "max_tokens": 256, "temperature": 0.2}
    started = time.perf_counter()
    with httpx.Client(timeout=timeout_s) as client:
        r = client.post(url, json=payload)
        r.raise_for_status()
        data = r.json()
        text = data["choices"][0]["message"]["content"]
        return {
            "request_id": data.get("request_id"),
            "provider": data.get("provider"),
            "model": data.get("model"),
            "latency_ms": data.get("latency_ms", int((time.perf_counter() - started) * 1000)),
            "retry_count": data.get("retry_count", 0),
            "text": text,
            "usage": data.get("usage", {}),
        }


def run(args: AgentArgs) -> Dict[str, Any]:
    dirs = _ensure_dirs(args.out_dir)
    outputs, logs, shots = dirs["outputs"], dirs["logs"], dirs["shots"]

    steps: List[Dict[str, Any]] = []
    t0 = time.perf_counter()

    # Step 1: browse and capture
    s0 = time.perf_counter()
    nav = _fetch_and_capture(args.source, shots, logs, dry_run=args.dry_run)
    steps.append({"name": "browse", "latency_ms": int((time.perf_counter() - s0) * 1000)})

    # Step 2: call gateway
    evidence = _extract_evidence(nav.get("content_html"))
    messages = [
        {"role": "system", "content": "You are a research assistant."},
        {"role": "user", "content": f"Ticker: {args.ticker}. Summarize events from source."},
        {"role": "user", "content": evidence or "No evidence."},
    ]
    s1 = time.perf_counter()
    llm = _call_gateway(args.gateway, messages, args.model, args.timeout_s, args.dry_run)
    steps.append({"name": "llm", "latency_ms": int((time.perf_counter() - s1) * 1000), "request_id": llm["request_id"]})

    # Step 3: generate artifacts
    s2 = time.perf_counter()
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
                "## Summary",
                llm["text"],
                "",
                f"Timestamp: {_now_iso()}",
            ]
        ),
        encoding="utf-8",
    )
    slides_pdf = outputs / "slides.pdf"
    _write_minimal_pdf(slides_pdf, f"{args.ticker} Summary", llm["text"])  # minimal valid PDF
    checksums = outputs / "checksums.txt"
    checksums.write_text(
        "\n".join(
            [
                f"{_sha256(report_md)}  report.md",
                f"{_sha256(slides_pdf)}  slides.pdf",
            ]
        )
    )
    steps.append({"name": "artifacts", "latency_ms": int((time.perf_counter() - s2) * 1000)})

    # Step 4: write run.json
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
        },
        "request_ids": [llm.get("request_id")],
        "latency_summary": {"navigation_ms": nav.get("latency_ms"), "llm_ms": llm.get("latency_ms")},
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
    ns = p.parse_args(argv)
    return AgentArgs(
        ticker=ns.ticker,
        source=ns.source,
        gateway=ns.gateway,
        model=ns.model,
        out_dir=Path(ns.out_dir).resolve(),
        dry_run=bool(ns.dry_run),
        timeout_s=float(ns.timeout),
    )


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    run(args)
    print(json.dumps({"status": "ok", "out_dir": str(args.out_dir)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())


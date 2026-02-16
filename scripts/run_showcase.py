from __future__ import annotations

import argparse
import json
import sys
import time
from typing import Optional

import httpx


def main(argv: Optional[list[str]] = None) -> int:
    p = argparse.ArgumentParser(description="Run showcase via backend Agent Runner")
    p.add_argument("--gateway", default="http://localhost:8000")
    p.add_argument("--ticker", default="2330")
    p.add_argument("--source", default="https://tw.stock.yahoo.com/")
    p.add_argument("--model", default="gpt-3.5-turbo")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--yahoo", action="store_true", default=True)
    args = p.parse_args(argv)

    base = args.gateway.rstrip("/")
    start_url = f"{base}/agent/run"
    status_url = f"{base}/agent/status"

    payload = {
        "ticker": args.ticker,
        "source": args.source,
        "model": args.model,
        "dry_run": bool(args.dry_run),
        "gateway": base,
        "yahoo": bool(args.yahoo),
    }

    with httpx.Client(timeout=30.0) as client:
        r = client.post(start_url, json=payload)
        r.raise_for_status()
        run_id = r.json()["run_id"]
        print(f"Run started: {run_id}")

        # poll
        for _ in range(120):
            time.sleep(0.5)
            s = client.get(f"{status_url}/{run_id}")
            s.raise_for_status()
            data = s.json()
            if data["status"] in ("completed", "error"):
                print(json.dumps(data, indent=2))
                # friendly summary
                artifacts = data.get("artifacts", {})
                print("Artifacts:")
                print(f"  Report:  {artifacts.get('report_url')}")
                print(f"  Slides:  {artifacts.get('slides_url')}")
                if data.get("screenshots"):
                    print(f"  Shot:    {data['screenshots'][0]}")
                return 0 if data["status"] == "completed" else 2
        print("Timeout waiting for run to complete")
        return 1


if __name__ == "__main__":
    sys.exit(main())

"""
Call the face service after the graph is loaded.

Usage (face service must already be running on FACE_SERVICE_URL):
  python run_pipeline.py
  python run_pipeline.py --skip-generate --skip-load
  python run_pipeline.py --threshold 0.65
"""

from __future__ import annotations

import argparse
import json
import os
import urllib.error
import urllib.request
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")


def request(method: str, path: str, payload: dict | None = None, timeout: int = 3600) -> dict:
    base = os.getenv("FACE_SERVICE_URL", "http://localhost:8000").rstrip("/")
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{base}{path}",
        data=data,
        headers={"Content-Type": "application/json"},
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"{method} {path} failed ({exc.code}): {detail}") from exc
    except urllib.error.URLError as exc:
        raise SystemExit(
            f"Cannot reach the face service at {base}. Start it with:\n"
            "  cd face-service\n"
            "  .\\.venv\\Scripts\\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000"
        ) from exc


def main() -> None:
    parser = argparse.ArgumentParser(description="Embed, cluster and score the loaded Mini-ASTR graph")
    parser.add_argument("--skip-generate", action="store_true")
    parser.add_argument("--skip-load", action="store_true")
    parser.add_argument("--threshold", type=float, default=None)
    args = parser.parse_args()

    if not args.skip_generate:
        from generate_data import build

        build()
    if not args.skip_load:
        from load_neo4j import main as load

        load()

    print("Embedding faces (first run downloads Facenet512 and can take several minutes)...")
    ingest = request("POST", "/ingest")
    print(json.dumps({k: ingest[k] for k in ("faces", "updated", "failed_count") if k in ingest}, indent=2))
    if ingest.get("failed_count"):
        print("Embedding failures:", json.dumps(ingest.get("failed"), indent=2))

    print("Clustering...")
    body = {"k": 10}
    if args.threshold is not None:
        body["threshold"] = args.threshold
    clustered = request("POST", "/cluster", body)
    print(json.dumps(clustered, indent=2))

    print("Scoring KYC differences...")
    scored = request("POST", "/fuzzy-check")
    print(json.dumps({"clusters": scored["clusters"], "flagged": scored["flagged"]}, indent=2))

    print("Evaluating against ground_truth.json...")
    metrics = request("GET", "/evaluate")
    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()

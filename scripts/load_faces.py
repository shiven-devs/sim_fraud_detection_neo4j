"""Embed the existing Aura Face nodes, cluster them, and score the identities.

This runs the project's pipeline locally, so the Render face service is not used.
Run from the repository root or from scripts/ with the local face requirements
installed in scripts/.venv.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FACE_SERVICE = ROOT / "face-service"
# DeepFace emits emoji in its model-download logs. Windows PowerShell may use
# cp1252, which would turn those log messages into UnicodeEncodeError failures.
for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(FACE_SERVICE))

from app.pipeline import cluster_faces, evaluate, fuzzy_check, ingest_faces  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--threshold", type=float, default=None)
    parser.add_argument("--k", type=int, default=10)
    args = parser.parse_args()

    print("Embedding the existing Face nodes stored in Aura...")
    ingested = ingest_faces()
    print(json.dumps(ingested, indent=2))
    if ingested["faces"] == 0:
        raise SystemExit("No Face nodes found in the Aura database selected by the root .env.")
    if ingested["updated"] == 0:
        raise SystemExit("No faces were embedded. Check the failure details above.")

    print("Clustering face embeddings...")
    clustered = cluster_faces(threshold=args.threshold, k=args.k)
    print(json.dumps(clustered, indent=2))

    print("Scoring clusters against subscriber KYC data...")
    scored = fuzzy_check()
    print(json.dumps(scored, indent=2))

    print("Evaluating planted cases...")
    print(json.dumps(evaluate(), indent=2))


if __name__ == "__main__":
    main()

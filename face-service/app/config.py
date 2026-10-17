"""Shared settings. Phase 2 can import this module instead of reading os.environ ad hoc."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# face-service/app/config.py -> repository root is parents[2]
ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "mini-astr-demo")
FACE_SERVICE_URL = os.getenv("FACE_SERVICE_URL", "http://localhost:8000")

FACES_DIR = Path(os.getenv("FACES_DIR", str(ROOT / "faces")))
GROUND_TRUTH_PATH = Path(os.getenv("GROUND_TRUTH_PATH", str(ROOT / "data" / "ground_truth.json")))

# Configurable on purpose: the demo shows scores, and a reviewer can retune the cut-off.
SIMILARITY_THRESHOLD = float(os.getenv("SIMILARITY_THRESHOLD", "0.8"))
FUZZY_NAME_THRESHOLD = float(os.getenv("FUZZY_NAME_THRESHOLD", "85"))
VECTOR_INDEX = "face_idx"
EMBEDDING_DIM = 512


def cors_origins() -> list[str]:
    origins = ["http://localhost:3000"]
    for item in os.getenv("CORS_ORIGINS", "").split(","):
        cleaned = item.strip().rstrip("/")
        if cleaned and cleaned not in origins:
            origins.append(cleaned)
    return origins

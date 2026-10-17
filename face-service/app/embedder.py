"""Facenet512 embeddings. The model is loaded on the first request and then reused."""

from __future__ import annotations

import logging

import numpy as np

from .config import EMBEDDING_DIM

log = logging.getLogger("mini-astr")
_ready = False


def _represent(path: str):
    # Imported lazily so /health can answer before TensorFlow finishes loading.
    from deepface import DeepFace

    try:
        # LFW crops are already faces. Skipping the detector avoids false "no face" errors.
        return DeepFace.represent(
            img_path=path,
            model_name="Facenet512",
            enforce_detection=False,
            detector_backend="skip",
        )
    except Exception:
        log.warning("detector_backend=skip failed; retrying with the default detector disabled")
        return DeepFace.represent(
            img_path=path,
            model_name="Facenet512",
            enforce_detection=False,
        )


def embed_path(path: str) -> list[float]:
    global _ready
    if not _ready:
        log.info("Loading Facenet512. The first call also downloads the model weights.")
    reps = _represent(path)
    _ready = True
    if not reps:
        raise ValueError(f"No embedding returned for {path}")
    vector = np.asarray(reps[0]["embedding"], dtype=np.float64)
    if vector.shape != (EMBEDDING_DIM,):
        raise ValueError(f"Expected {EMBEDDING_DIM} dimensions, got {vector.shape}")
    norm = np.linalg.norm(vector)
    if norm == 0:
        raise ValueError(f"Zero embedding for {path}")
    # Unit length makes the Neo4j cosine index comparable with the published threshold.
    return [float(x) for x in (vector / norm)]

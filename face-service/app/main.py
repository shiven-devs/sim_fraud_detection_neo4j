"""
Mini-ASTR face service.

POST /embed, /ingest, /cluster, /fuzzy-check, /search and GET /evaluate.
The Next.js app is the only UI. This process does not confirm fraud.
"""

from __future__ import annotations

import logging
import os
import tempfile
from contextlib import asynccontextmanager

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .config import FUZZY_NAME_THRESHOLD, SIMILARITY_THRESHOLD, cors_origins
from .embedder import embed_path
from .neo4j_client import close_driver, session
from .pipeline import cluster_faces, evaluate, fuzzy_check, ingest_faces

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("mini-astr")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    yield
    close_driver()


app = FastAPI(title="Mini-ASTR Face Service", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins(),
    allow_methods=["*"],
    allow_headers=["*"],
)


class ClusterBody(BaseModel):
    threshold: float | None = None
    k: int = Field(default=10, ge=1, le=50)


def _write_upload(file: UploadFile) -> str:
    suffix = os.path.splitext(file.filename or "upload.jpg")[1] or ".jpg"
    if suffix.lower() not in {".jpg", ".jpeg", ".png", ".webp", ".bmp"}:
        suffix = ".jpg"
    handle = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    handle.write(file.file.read())
    handle.close()
    return handle.name


@app.get("/health")
def health():
    return {"status": "ok", "similarity_threshold": SIMILARITY_THRESHOLD, "fuzzy_name_threshold": FUZZY_NAME_THRESHOLD}


@app.post("/embed")
def embed(file: UploadFile = File(...)):
    path = _write_upload(file)
    try:
        embedding = embed_path(path)
    except Exception as exc:
        log.exception("embed failed")
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        os.remove(path)
    return {"dim": len(embedding), "embedding": embedding}


@app.post("/ingest")
def ingest():
    try:
        return ingest_faces()
    except Exception as exc:
        log.exception("ingest failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/cluster")
def cluster(body: ClusterBody | None = None):
    payload = body or ClusterBody()
    try:
        return cluster_faces(threshold=payload.threshold, k=payload.k)
    except Exception as exc:
        log.exception("cluster failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/fuzzy-check")
def fuzzy():
    try:
        return fuzzy_check()
    except Exception as exc:
        log.exception("fuzzy-check failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/search")
def search(file: UploadFile = File(...)):
    path = _write_upload(file)
    try:
        embedding = embed_path(path)
        with session() as db:
            rows = db.run(
                """
                CALL db.index.vector.queryNodes('face_idx', 5, $embedding)
                YIELD node, score
                MATCH (s:Subscriber)-[:HAS_FACE]->(node)
                OPTIONAL MATCH (s)-[:OWNS]->(m:SIM)
                RETURN node.id AS faceId,
                       score,
                       s.id AS subscriberId,
                       s.name AS name,
                       s.dob AS dob,
                       s.address AS address,
                       s.kyc_id AS kycId,
                       s.bank_account AS bankAccount,
                       collect(DISTINCT m.number) AS sims
                ORDER BY score DESC
                """,
                embedding=embedding,
            ).data()
    except Exception as exc:
        log.exception("search failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        os.remove(path)

    matches = []
    for row in rows:
        score = float(row["score"])
        matches.append(
            {
                "faceId": row["faceId"],
                "score": score,
                "aboveThreshold": score > SIMILARITY_THRESHOLD,
                "subscriberId": row["subscriberId"],
                "name": row["name"],
                "dob": row["dob"],
                "address": row["address"],
                "kycId": row["kycId"],
                "bankAccount": row["bankAccount"],
                "sims": [sim for sim in row["sims"] if sim],
            }
        )
    return {"threshold": SIMILARITY_THRESHOLD, "matches": matches}


@app.get("/evaluate")
def evaluate_route():
    try:
        return evaluate()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        log.exception("evaluate failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc

"""Clustering, fuzzy KYC checks, and evaluation against planted ground truth."""

from __future__ import annotations

import json
import os
import tempfile
import time
from collections import defaultdict

import networkx as nx
from rapidfuzz import fuzz

from .config import (
    EMBEDDING_DIM,
    FUZZY_NAME_THRESHOLD,
    GROUND_TRUTH_PATH,
    SIMILARITY_THRESHOLD,
    VECTOR_INDEX,
)
from .embedder import embed_path
from .neo4j_client import session

INDEX_CYPHER = f"""
CREATE VECTOR INDEX {VECTOR_INDEX} IF NOT EXISTS
FOR (f:Face) ON (f.embedding)
OPTIONS {{
  indexConfig: {{
    `vector.dimensions`: {EMBEDDING_DIM},
    `vector.similarity_function`: 'cosine'
  }}
}}
"""


def ensure_vector_index() -> None:
    with session() as db:
        db.run(INDEX_CYPHER)
        db.run("CALL db.awaitIndexes(300)")
        for _ in range(60):
            record = db.run(
                "SHOW INDEXES YIELD name, state WHERE name = $name RETURN state",
                name=VECTOR_INDEX,
            ).single()
            if record and record["state"] == "ONLINE":
                return
            time.sleep(1)
    raise RuntimeError("face_idx did not come online. Neo4j 5.11 or newer is required.")


def _photo_path(face: dict) -> tuple[str, bool]:
    """Return a JPEG path and whether the caller must delete it.

    Hosted ingest uses the bytes stored on the Face node. A local file is the fallback.
    """
    image = face.get("image")
    if image:
        handle = tempfile.NamedTemporaryFile(delete=False, suffix=".jpg")
        handle.write(bytes(image))
        handle.close()
        return handle.name, True

    from .config import ROOT

    relative = face.get("path") or ""
    absolute = ROOT / relative
    if relative and absolute.is_file():
        return str(absolute), False
    raise FileNotFoundError(f"No photo bytes or file for {face.get('id')}")


def ingest_faces() -> dict:
    with session() as db:
        faces = db.run(
            "MATCH (f:Face) RETURN f.id AS id, f.image_path AS path, f.image AS image"
        ).data()
    updated = 0
    failed = []

    for face in faces:
        photo = None
        temporary = False
        try:
            photo, temporary = _photo_path(face)
            embedding = embed_path(photo)
        except Exception as exc:
            failed.append({"id": face["id"], "error": str(exc)})
            continue
        finally:
            if temporary and photo:
                os.remove(photo)
        with session() as db:
            db.run(
                "MATCH (f:Face {id: $id}) SET f.embedding = $embedding",
                id=face["id"],
                embedding=embedding,
            )
        updated += 1
        if updated % 10 == 0:
            print(f"embedded {updated}/{len(faces)}", flush=True)
    ensure_vector_index()
    return {"faces": len(faces), "updated": updated, "failed": failed[:20], "failed_count": len(failed)}


def cluster_faces(threshold: float | None = None, k: int = 10) -> dict:
    cutoff = SIMILARITY_THRESHOLD if threshold is None else threshold
    ensure_vector_index()
    with session() as db:
        faces = db.run(
            "MATCH (f:Face) WHERE f.embedding IS NOT NULL RETURN f.id AS id, f.embedding AS embedding"
        ).data()
    if not faces:
        raise RuntimeError("No face embeddings found. Run POST /ingest first.")

    # Drop the previous clustering so a threshold change is reproducible.
    with session() as db:
        db.run("MATCH (i:Identity)-[:REVIEWED_AS]->(r:Review) DETACH DELETE r")
        db.run("MATCH (i:Identity) DETACH DELETE i")
        db.run("MATCH ()-[r:SIMILAR_TO]->() DELETE r")

    edges = []
    top_scores = []
    seen_pairs: set[tuple[str, str]] = set()
    with session() as db:
        for face in faces:
            neighbors = db.run(
                """
                CALL db.index.vector.queryNodes($index, toInteger($k), $embedding)
                YIELD node, score
                RETURN node.id AS id, score
                """,
                index=VECTOR_INDEX,
                k=k,
                embedding=face["embedding"],
            ).data()
            others = [row for row in neighbors if row["id"] != face["id"]]
            if others:
                top_scores.append(float(others[0]["score"]))
            for row in others:
                if float(row["score"]) <= cutoff:
                    continue
                pair = tuple(sorted((face["id"], row["id"])))
                if pair in seen_pairs:
                    continue
                seen_pairs.add(pair)
                edges.append({"a": pair[0], "b": pair[1], "score": float(row["score"])})

    graph = nx.Graph()
    graph.add_nodes_from(face["id"] for face in faces)
    for edge in edges:
        graph.add_edge(edge["a"], edge["b"], score=edge["score"])

    components = list(nx.connected_components(graph))
    identity_rows = []
    for index, component in enumerate(components, start=1):
        identity_rows.append({"id": f"ID-{index:04d}", "faces": sorted(component)})

    with session() as db:
        if edges:
            db.run(
                """
                UNWIND $edges AS edge
                MATCH (a:Face {id: edge.a})
                MATCH (b:Face {id: edge.b})
                CREATE (a)-[:SIMILAR_TO {score: edge.score}]->(b)
                """,
                edges=edges,
            )
        for row in identity_rows:
            db.run(
                """
                CREATE (i:Identity {id: $id, created_at: datetime()})
                WITH i
                UNWIND $faces AS face_id
                MATCH (f:Face {id: face_id})
                CREATE (f)-[:BELONGS_TO]->(i)
                """,
                id=row["id"],
                faces=row["faces"],
            )

    summary = {
        "threshold": cutoff,
        "k": k,
        "faces": len(faces),
        "similar_edges": len(edges),
        "identities": len(identity_rows),
        "multi_face_identities": sum(1 for row in identity_rows if len(row["faces"]) > 1),
    }
    if top_scores:
        ordered = sorted(top_scores)
        summary["nearest_neighbor_scores"] = {
            "min": round(ordered[0], 4),
            "median": round(ordered[len(ordered) // 2], 4),
            "max": round(ordered[-1], 4),
        }
    return summary


def _score_cluster(people: list[dict], top_similarity: float | None, cutoff: float) -> dict:
    # One subscriber can theoretically be linked twice; keep the first copy.
    unique = []
    seen = set()
    for person in people:
        if person["id"] in seen:
            continue
        seen.add(person["id"])
        unique.append(person)
    people = unique

    reasons: list[str] = []
    score = 0
    names = list(dict.fromkeys(person["name"] for person in people))
    dobs = {person["dob"] for person in people}
    addresses = {person["address"] for person in people}
    banks = {person["bank"] for person in people}
    sim_counts = [int(person["sims"]) for person in people]
    max_sims = max(sim_counts) if sim_counts else 0
    total_sims = sum(sim_counts)

    if len(people) > 1:
        score += 40
        reasons.append(f"Same face is linked to {len(people)} subscriber records.")

    if len(names) > 1:
        ratios = [
            fuzz.token_sort_ratio(names[i], names[j])
            for i in range(len(names))
            for j in range(i + 1, len(names))
        ]
        best = max(ratios) if ratios else 0
        if best > FUZZY_NAME_THRESHOLD:
            score += 20
            reasons.append(
                f"Names look like variants of each other (best token sort ratio {best:.0f}, threshold {FUZZY_NAME_THRESHOLD:.0f})."
            )
        else:
            score += 25
            reasons.append(f"Same face is registered under dissimilar names (best token sort ratio {best:.0f}).")

    if len(dobs) > 1:
        score += 15
        reasons.append(f"{len(dobs)} different dates of birth appear on this face.")
    if len(addresses) > 1:
        score += 10
        reasons.append(f"{len(addresses)} different addresses appear on this face.")
    if len(banks) > 1:
        score += 15
        reasons.append(f"{len(banks)} different bank accounts appear on this face.")

    names_by_bank: dict[str, set[str]] = defaultdict(set)
    for person in people:
        names_by_bank[person["bank"]].add(person["name"])
    if any(len(group) > 1 for group in names_by_bank.values()):
        score += 20
        reasons.append("A bank account is shared by subscriber records with different names.")

    if max_sims > 8:
        score += 30
        reasons.append(f"A subscriber in this cluster holds {max_sims} SIMs (rule: more than 8).")

    if top_similarity is not None and len(people) > 1:
        reasons.append(
            f"Highest face similarity inside the cluster is {top_similarity:.2f} "
            f"(link threshold {cutoff:.2f}). This is a similarity score, not a yes/no decision."
        )

    score = min(100, score)
    return {
        "risk_score": score,
        "reasons": reasons,
        "subscriber_count": len(people),
        "sim_count": total_sims,
        "flagged": score >= 30,
    }


def fuzzy_check() -> dict:
    with session() as db:
        rows = db.run(
            """
            MATCH (i:Identity)<-[:BELONGS_TO]-(:Face)<-[:HAS_FACE]-(s:Subscriber)
            OPTIONAL MATCH (s)-[:OWNS]->(m:SIM)
            RETURN i.id AS identity_id,
                   s.id AS id,
                   s.name AS name,
                   s.dob AS dob,
                   s.address AS address,
                   s.bank_account AS bank,
                   count(m) AS sims
            """
        ).data()
        similarities = {
            record["id"]: record["top"]
            for record in db.run(
                """
                MATCH (i:Identity)<-[:BELONGS_TO]-(f:Face)-[r:SIMILAR_TO]-(g:Face)-[:BELONGS_TO]->(i)
                RETURN i.id AS id, max(r.score) AS top
                """
            ).data()
        }

    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        grouped[row["identity_id"]].append(row)

    # Identities with no subscriber still get an explicit zero so the dashboard can ignore them.
    with session() as db:
        all_ids = [record["id"] for record in db.run("MATCH (i:Identity) RETURN i.id AS id").data()]

    updates = []
    flagged = 0
    for identity_id in all_ids:
        scored = _score_cluster(grouped.get(identity_id, []), similarities.get(identity_id), SIMILARITY_THRESHOLD)
        scored["id"] = identity_id
        updates.append(scored)
        if scored["flagged"]:
            flagged += 1

    with session() as db:
        db.run(
            """
            UNWIND $rows AS row
            MATCH (i:Identity {id: row.id})
            SET i.risk_score = row.risk_score,
                i.reasons = row.reasons,
                i.subscriber_count = row.subscriber_count,
                i.sim_count = row.sim_count,
                i.flagged = row.flagged
            """,
            rows=updates,
        )
    return {
        "clusters": len(updates),
        "flagged": flagged,
        "fuzzy_name_threshold": FUZZY_NAME_THRESHOLD,
        "top_flagged": sorted(
            (
                {"id": row["id"], "risk_score": row["risk_score"], "reasons": row["reasons"]}
                for row in updates
                if row["flagged"]
            ),
            key=lambda row: row["risk_score"],
            reverse=True,
        )[:10],
    }


def _load_ground_truth() -> dict:
    with session() as db:
        record = db.run(
            "MATCH (d:Dataset {id: 'mini-astr'}) RETURN d.ground_truth AS ground_truth"
        ).single()
    if record and record["ground_truth"]:
        return json.loads(record["ground_truth"])
    if GROUND_TRUTH_PATH.exists():
        return json.loads(GROUND_TRUTH_PATH.read_text(encoding="utf-8"))
    raise FileNotFoundError(
        "Ground truth is not on the Dataset node and "
        f"{GROUND_TRUTH_PATH} is missing. Reload with scripts/load_neo4j.py."
    )


def evaluate() -> dict:
    ground_truth = _load_ground_truth()

    with session() as db:
        flagged = db.run(
            """
            MATCH (i:Identity)
            WHERE coalesce(i.flagged, false) = true
            OPTIONAL MATCH (i)<-[:BELONGS_TO]-(:Face)<-[:HAS_FACE]-(s:Subscriber)
            WITH i, collect(DISTINCT s.id) AS ids
            RETURN i.id AS id, ids
            """
        ).data()
        excess_rows = db.run(
            """
            MATCH (s:Subscriber)-[:OWNS]->(m:SIM)
            WITH s, count(m) AS sims
            WHERE sims > 8
            RETURN s.id AS id, sims
            """
        ).data()
        bank_rows = db.run(
            """
            MATCH (a:Subscriber)-[:HAS_FACE]->(:Face)-[:BELONGS_TO]->(i:Identity)<-[:BELONGS_TO]-(:Face)<-[:HAS_FACE]-(b:Subscriber)
            WHERE a.id < b.id AND a.bank_account = b.bank_account AND a.name <> b.name
            RETURN a.id AS a, b.id AS b, a.bank_account AS bank
            """
        ).data()

    truth_clusters = ground_truth.get("same_face_clusters", [])
    detected = [set(row["ids"]) for row in flagged if len([item for item in row["ids"] if item]) > 1]

    recalled = 0
    for cluster in truth_clusters:
        expected = set(cluster["subscriber_ids"])
        if any(len(expected & found) >= 2 for found in detected):
            recalled += 1

    true_positives = 0
    false_positives = 0
    for found in detected:
        if any(len(found & set(cluster["subscriber_ids"])) >= 2 for cluster in truth_clusters):
            true_positives += 1
        else:
            false_positives += 1
    false_negatives = len(truth_clusters) - recalled
    precision = true_positives / (true_positives + false_positives) if (true_positives + false_positives) else 0.0
    recall = recalled / len(truth_clusters) if truth_clusters else 0.0

    excess_found = {row["id"] for row in excess_rows}
    excess_expected = {row["subscriber_id"] for row in ground_truth.get("excess_sims", [])}
    shared_expected = ground_truth.get("shared_bank", [])
    shared_hits = 0
    for case in shared_expected:
        expected = set(case["subscriber_ids"])
        if any(expected <= {row["a"], row["b"]} for row in bank_rows):
            shared_hits += 1

    return {
        "face_clusters": {
            "precision": precision,
            "recall": recall,
            "true_positives": true_positives,
            "false_positives": false_positives,
            "false_negatives": false_negatives,
            "ground_truth_clusters": len(truth_clusters),
            "detected_multi_person_clusters": len(detected),
        },
        "excess_sims": {
            "expected": sorted(excess_expected),
            "detected": sorted(excess_found),
            "caught": excess_expected <= excess_found and len(excess_expected) > 0,
        },
        "shared_bank": {
            "expected": len(shared_expected),
            "detected_pairs": len(bank_rows),
            "caught": shared_hits == len(shared_expected) and len(shared_expected) > 0,
        },
        "similarity_threshold": SIMILARITY_THRESHOLD,
        "fuzzy_name_threshold": FUZZY_NAME_THRESHOLD,
    }

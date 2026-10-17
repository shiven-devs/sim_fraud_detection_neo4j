"""
Load data/subscribers.json into Neo4j.

Creates Subscriber, Face, SIM and TSP nodes and the Phase 1 relationships.
Embeddings, Identity clusters and Review nodes are filled in later by the face service
and the reviewer UI. Re-running this script deletes previous Mini-ASTR labels first.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

from dotenv import load_dotenv
from neo4j import GraphDatabase

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")


def connect():
    uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    user = os.getenv("NEO4J_USER", "neo4j")
    password = os.getenv("NEO4J_PASSWORD", "mini-astr-demo")
    driver = GraphDatabase.driver(uri, auth=(user, password))
    last_error: Exception | None = None
    for attempt in range(30):
        try:
            driver.verify_connectivity()
            print(f"Connected to {uri}")
            return driver
        except Exception as exc:  # connection refused while the container boots
            last_error = exc
            print(f"Waiting for Neo4j ({attempt + 1}/30)...")
            time.sleep(2)
    raise SystemExit(f"Neo4j is not reachable at {uri}: {last_error}")


def main() -> None:
    dataset_path = ROOT / "data" / "subscribers.json"
    truth_path = ROOT / "data" / "ground_truth.json"
    if not dataset_path.exists():
        raise SystemExit("Missing data/subscribers.json. Run scripts/generate_data.py first.")
    if not truth_path.exists():
        raise SystemExit("Missing data/ground_truth.json. Run scripts/generate_data.py first.")
    dataset = json.loads(dataset_path.read_text(encoding="utf-8"))
    subscribers = dataset["subscribers"]
    ground_truth = truth_path.read_text(encoding="utf-8")

    driver = connect()
    with driver.session() as session:
        print("Removing previous Mini-ASTR nodes (including stored photos and ground truth)...")
        session.run(
            """
            MATCH (n)
            WHERE n:Subscriber OR n:Face OR n:SIM OR n:TSP OR n:Identity
               OR n:Review OR n:AuditLog OR n:Dataset
            DETACH DELETE n
            """
        )

        # Uniqueness keeps a re-load and the later cluster step from creating duplicates.
        for statement in (
            "CREATE CONSTRAINT subscriber_id IF NOT EXISTS FOR (s:Subscriber) REQUIRE s.id IS UNIQUE",
            "CREATE CONSTRAINT face_id IF NOT EXISTS FOR (f:Face) REQUIRE f.id IS UNIQUE",
            "CREATE CONSTRAINT sim_number IF NOT EXISTS FOR (m:SIM) REQUIRE m.number IS UNIQUE",
            "CREATE CONSTRAINT tsp_name IF NOT EXISTS FOR (t:TSP) REQUIRE t.name IS UNIQUE",
            "CREATE CONSTRAINT identity_id IF NOT EXISTS FOR (i:Identity) REQUIRE i.id IS UNIQUE",
            "CREATE CONSTRAINT review_id IF NOT EXISTS FOR (r:Review) REQUIRE r.id IS UNIQUE",
            "CREATE CONSTRAINT audit_id IF NOT EXISTS FOR (a:AuditLog) REQUIRE a.id IS UNIQUE",
            "CREATE CONSTRAINT dataset_id IF NOT EXISTS FOR (d:Dataset) REQUIRE d.id IS UNIQUE",
        ):
            session.run(statement)

        session.run(
            "UNWIND $names AS name MERGE (:TSP {name: name})",
            names=dataset.get("tsps", ["Jio", "Airtel", "Vi"]),
        )

        rows = []
        sim_rows = []
        for person in subscribers:
            image_file = ROOT / person["image_path"]
            if not image_file.is_file():
                raise SystemExit(f"Missing photo {image_file}. Run scripts/generate_data.py first.")
            # Bytes travel with the node so Render and Vercel do not need the faces folder.
            rows.append(
                {
                    "id": person["id"],
                    "name": person["name"],
                    "dob": person["dob"],
                    "address": person["address"],
                    "kyc_id": person["kyc_id"],
                    "bank_account": person["bank_account"],
                    "face_id": person["face_id"],
                    "image_path": person["image_path"],
                    "image": bytearray(image_file.read_bytes()),
                }
            )
            for sim in person["sims"]:
                sim_rows.append(
                    {
                        "subscriber_id": person["id"],
                        "number": sim["number"],
                        "activated_on": sim["activated_on"],
                        "tsp": sim["tsp"],
                    }
                )

        session.run(
            """
            UNWIND $rows AS row
            CREATE (s:Subscriber {
              id: row.id,
              name: row.name,
              dob: row.dob,
              address: row.address,
              kyc_id: row.kyc_id,
              bank_account: row.bank_account
            })
            CREATE (f:Face {id: row.face_id, image_path: row.image_path, image: row.image})
            CREATE (s)-[:HAS_FACE]->(f)
            """,
            rows=rows,
        )
        # SIM nodes are created before the relationships so MATCH can find them.
        session.run(
            """
            UNWIND $rows AS row
            CREATE (:SIM {number: row.number, activated_on: row.activated_on})
            """,
            rows=sim_rows,
        )
        session.run(
            """
            UNWIND $rows AS row
            MATCH (m:SIM {number: row.number})
            MATCH (t:TSP {name: row.tsp})
            MATCH (s:Subscriber {id: row.subscriber_id})
            CREATE (s)-[:OWNS]->(m)
            CREATE (m)-[:ISSUED_BY]->(t)
            """,
            rows=sim_rows,
        )
        session.run(
            "CREATE (:Dataset {id: 'mini-astr', ground_truth: $ground_truth})",
            ground_truth=ground_truth,
        )

        counts = session.run(
            """
            RETURN
              count { (:Subscriber) } AS subscribers,
              count { (:Face) } AS faces,
              count { (:SIM) } AS sims,
              count { (:TSP) } AS tsps
            """
        ).single()
        print(
            "Loaded "
            f"{counts['subscribers']} subscribers, "
            f"{counts['faces']} faces with photo bytes, "
            f"{counts['sims']} SIMs, "
            f"{counts['tsps']} TSPs, "
            "and the ground-truth Dataset node."
        )
        print("Face embeddings are still empty. Start the face service, then run scripts/run_pipeline.py")
        print("or POST /ingest, /cluster and /fuzzy-check.")
    driver.close()


if __name__ == "__main__":
    main()

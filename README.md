# Mini-ASTR
hosted on https://sim-fraud-detection-neo4j.vercel.app/
A hackathon demo that flags synthetic SIM connections when one face is registered under more than one identity. It follows the shape of India's DoT ASTR system: face embeddings, fuzzy KYC comparison, a SIM-count rule, and a human review before anything is confirmed.

Photos come from the public [Labeled Faces in the Wild](http://vis-www.cs.umass.edu/lfw/) benchmark through scikit-learn. Names, dates of birth, addresses, KYC ids and bank accounts are generated with Faker. Do not load real subscriber data.

Phase 2 (a graph chat assistant) is not in this repo.

## Layout

```
web/             Next.js 14 dashboard, review, search and rules
face-service/    FastAPI + DeepFace Facenet512
scripts/         synthetic data generator, Neo4j loader, pipeline caller
docker-compose.yml
.env.example
```

Graph written in Phase 1:

- `(:Subscriber)-[:HAS_FACE]->(:Face)`
- `(:Subscriber)-[:OWNS]->(:SIM)-[:ISSUED_BY]->(:TSP)`
- `(:Face)-[:SIMILAR_TO {score}]->(:Face)`
- `(:Face)-[:BELONGS_TO]->(:Identity)-[:REVIEWED_AS]->(:Review)`
- `(:Face)` also stores the JPEG in `image`, so a hosted site can show thumbnails without the `faces/` folder
- `(:Dataset {ground_truth})` holds the planted cases used for precision and recall
- `(:AuditLog)` for each search and review

`web/lib/neo4j.ts` is the only Next.js Neo4j driver. `web/lib/llm.ts` is an empty seam for a later phase and is not called.

## 0. Requirements

- Docker Desktop
- Node.js 18+
- Python 3.10, 3.11 or 3.12 (TensorFlow often has no Windows wheel for 3.13)

From the repository root:

```powershell
copy .env.example .env
docker compose up -d
```

Neo4j Browser: http://localhost:7474 (user `neo4j`, password `mini-astr-demo`).

The loader deletes nodes labelled Subscriber, Face, SIM, TSP, Identity, Review and AuditLog. Point `.env` at an empty demo database.

## 1. Generate synthetic data

```powershell
cd scripts
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe generate_data.py
```

The first run downloads LFW and can take several minutes. It writes:

- `faces/<person>/<n>.jpg` — different files for each planted duplicate, never the same photo reused
- `data/subscribers.json` — about 100 subscribers, 3 TSPs (Jio, Airtel, Vi)
- `data/ground_truth.json` — the planted cases

Planted cases:

- 6 people, each with 2 or 3 subscriber records, altered names, different dates of birth and different SIMs
- 1 subscriber with 10 SIMs
- 1 face on two dissimilar names that share a bank account

Check the printed counts, then open `data/ground_truth.json` before a demo so you know which cases were planted. The detector does not read that file except in `GET /evaluate`.

## 2. Load Neo4j

```powershell
cd scripts
.\.venv\Scripts\python.exe load_neo4j.py
```

Expect about 100 subscribers, 100 faces, 3 TSPs, and more SIMs than subscribers. Each face stores its JPEG. Embeddings are still empty.

In Neo4j Browser:

```cypher
MATCH (s:Subscriber)-[:HAS_FACE]->(f:Face), (s)-[:OWNS]->(m:SIM)-[:ISSUED_BY]->(t:TSP)
RETURN s.name, f.image_path, m.number, t.name
LIMIT 10
```

## 3. Face service

Use a second terminal. The first `pip install` downloads TensorFlow and is large.

```powershell
cd face-service
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Check:

```powershell
curl http://127.0.0.1:8000/health
```

Embed, cluster and score. The first embedding run also downloads Facenet512 weights.

```powershell
cd scripts
.\.venv\Scripts\python.exe run_pipeline.py --skip-generate --skip-load
```

`run_pipeline.py` without those flags regenerates data and reloads the graph first.

The JSON from `/cluster` includes nearest-neighbour scores. If `multi_face_identities` is 0, same-person LFW photos scored under 0.8. Set `SIMILARITY_THRESHOLD=0.65` in `.env`, restart the face service, and run:

```powershell
.\.venv\Scripts\python.exe run_pipeline.py --skip-generate --skip-load --threshold 0.65
```

Clustering rebuilds `Identity` and `SIMILAR_TO` and deletes old `Review` nodes. `AuditLog` rows stay.

`GET /evaluate` prints precision and recall against `ground_truth.json`. A ground-truth face cluster counts as recalled when one detected multi-person identity contains at least two of its subscriber ids.

## 4. Dashboard

```powershell
cd web
npm install
npm run dev
```

Open http://localhost:3000.

- Metric cards: subscribers, SIMs, suspicious clusters, SIMs affected, precision, recall
- Queue sorted by risk score
- Cluster page: photos, KYC, reasons, force-directed graph, Confirm Fraud / Reject (false match)
- Face search: top 5 scores, audited with the reviewer name
- Rules: the two Cypher checks, plus the vector-search query used by the face service

A cluster stays "Pending review" until Confirm or Reject writes a `Review` node.

Audit log:

```cypher
MATCH (a:AuditLog) RETURN a.action, a.actor, a.timestamp, a.target, a.detail ORDER BY a.timestamp DESC
```

## Two-minute demo

1. Open the dashboard. Read the disclaimer. Point at precision, recall, and the risk-sorted queue.
2. Open the highest multi-name cluster. Show two or three different photos, similar names, different dates of birth, and the similarity score in the reasons. The score is not a yes/no.
3. Enter your name and choose Confirm Fraud or Reject. Show that the status changes and that the decision is listed with a timestamp.
4. Open Rules. Show the subscriber with more than 8 SIMs, and the identities that hold more than one name.
5. Open Face search, upload one photo from `faces/`, and read the scores against the threshold.

## Tuning

| Variable | Default | Role |
| --- | --- | --- |
| `SIMILARITY_THRESHOLD` | `0.8` | Cosine score required to link two faces |
| `FUZZY_NAME_THRESHOLD` | `85` | `token_sort_ratio` above which names count as variants |
| `FACE_SERVICE_URL` | `http://localhost:8000` | Next.js proxy target |
| `NEO4J_URI` | `bolt://localhost:7687` | `neo4j+s://` for Aura, `bolt://` for Docker |
| `CORS_ORIGINS` | empty | Extra browser origins for the face service, comma-separated |

## Deploy on Render and Vercel

The public site is Vercel. Render runs the face service. Neo4j Aura holds the graph, the JPEG bytes, and the ground-truth `Dataset` node. Do not commit `.env`.

Use a Render instance with 2 GB of RAM. The free and starter plans have 512 MB, and Facenet512 is killed there. [render.yaml](render.yaml) requests the standard plan and Python 3.11.

1. Push this repo to GitHub.
2. In [Neo4j Aura](https://console.neo4j.io), create an instance on Neo4j 5.11 or newer. Copy the `neo4j+s://` URI and password.
3. In Render, create a Blueprint from this repo, or a Python web service with root directory `face-service`. Set `NEO4J_URI`, `NEO4J_USER`, and `NEO4J_PASSWORD`. Optionally set `CORS_ORIGINS` to the Vercel URL. Open `https://<your-service>.onrender.com/health` and confirm `"status": "ok"`.
4. In Vercel, import the same repo. Set the root directory to `web`. Set the same Aura variables and `FACE_SERVICE_URL` to the Render URL, with no trailing slash.
5. From the laptop, point `.env` at Aura and Render, then load the demo once:

```powershell
cd scripts
.\.venv\Scripts\python.exe generate_data.py
.\.venv\Scripts\python.exe load_neo4j.py
.\.venv\Scripts\python.exe run_pipeline.py --skip-generate --skip-load
```

`load_neo4j.py` deletes Mini-ASTR nodes in that Aura database, then stores each photo on its `Face` node. The pipeline calls Render to embed, cluster, and score. The first embedding also downloads Facenet512 onto Render, so it can take several minutes.

Reload the Vercel URL. Metrics, photos, rules, and review actions come from Aura. Face search calls Render. A search right after Render wakes up can exceed Vercel's hobby limit of about 10 seconds; run one search after the model is warm, or retry.

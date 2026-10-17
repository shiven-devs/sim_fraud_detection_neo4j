import { NextResponse } from "next/server";
import { dbErrorMessage, run, text } from "@/lib/neo4j";

export const dynamic = "force-dynamic";

type SimRow = { number?: string | null; activatedOn?: string | null; tsp?: string | null };

export async function GET(_request: Request, { params }: { params: { id: string } }) {
  try {
    const identity = await run(
      `
      MATCH (i:Identity {id: $id})
      RETURN i.id AS id,
             i.risk_score AS riskScore,
             i.reasons AS reasons,
             coalesce(i.flagged, false) AS flagged,
             coalesce(i.subscriber_count, 0) AS subscriberCount
      `,
      { id: params.id }
    );
    if (identity.records.length === 0) {
      return NextResponse.json({ error: "Cluster not found." }, { status: 404 });
    }

    const reviews = await run(
      `
      MATCH (:Identity {id: $id})-[:REVIEWED_AS]->(r:Review)
      RETURN r.decision AS decision, r.reviewer AS reviewer, r.timestamp AS timestamp, r.note AS note
      ORDER BY r.timestamp DESC
      `,
      { id: params.id }
    );

    const peopleResult = await run(
      `
      MATCH (:Identity {id: $id})<-[:BELONGS_TO]-(f:Face)<-[:HAS_FACE]-(s:Subscriber)
      OPTIONAL MATCH (s)-[:OWNS]->(m:SIM)-[:ISSUED_BY]->(t:TSP)
      RETURN f.id AS faceId,
             s.id AS subscriberId,
             s.name AS name,
             s.dob AS dob,
             s.address AS address,
             s.kyc_id AS kycId,
             s.bank_account AS bankAccount,
             collect(DISTINCT {number: m.number, activatedOn: m.activated_on, tsp: t.name}) AS sims
      ORDER BY s.name
      `,
      { id: params.id }
    );

    const links = await run(
      `
      MATCH (:Identity {id: $id})<-[:BELONGS_TO]-(f:Face)-[rel:SIMILAR_TO]-(g:Face)-[:BELONGS_TO]->(:Identity {id: $id})
      WHERE f.id < g.id
      RETURN f.id AS source, g.id AS target, rel.score AS score
      `,
      { id: params.id }
    );

    const info = identity.records[0];
    const people = peopleResult.records.map((record) => {
      const sims = ((record.get("sims") as SimRow[] | null) ?? []).filter((sim) => sim?.number);
      return {
        faceId: text(record.get("faceId")),
        subscriberId: text(record.get("subscriberId")),
        name: text(record.get("name")),
        dob: text(record.get("dob")),
        address: text(record.get("address")),
        kycId: text(record.get("kycId")),
        bankAccount: text(record.get("bankAccount")),
        sims: sims.map((sim) => ({
          number: text(sim.number),
          activatedOn: text(sim.activatedOn),
          tsp: text(sim.tsp),
        })),
      };
    });

    const nodes: { id: string; label: string; type: string }[] = [
      { id: `identity:${params.id}`, label: params.id, type: "Identity" },
    ];
    const graphLinks: { source: string; target: string; label: string }[] = [];
    const seen = new Set(nodes.map((node) => node.id));

    function addNode(id: string, label: string, type: string) {
      if (seen.has(id)) return;
      seen.add(id);
      nodes.push({ id, label, type });
    }

    for (const person of people) {
      addNode(`face:${person.faceId}`, "Face", "Face");
      addNode(`sub:${person.subscriberId}`, person.name, "Subscriber");
      graphLinks.push({ source: `sub:${person.subscriberId}`, target: `face:${person.faceId}`, label: "HAS_FACE" });
      graphLinks.push({ source: `face:${person.faceId}`, target: `identity:${params.id}`, label: "BELONGS_TO" });
      for (const sim of person.sims) {
        addNode(`sim:${sim.number}`, sim.number, "SIM");
        addNode(`tsp:${sim.tsp}`, sim.tsp, "TSP");
        graphLinks.push({ source: `sub:${person.subscriberId}`, target: `sim:${sim.number}`, label: "OWNS" });
        graphLinks.push({ source: `sim:${sim.number}`, target: `tsp:${sim.tsp}`, label: "ISSUED_BY" });
      }
    }

    for (const record of links.records) {
      const score = Number(record.get("score"));
      graphLinks.push({
        source: `face:${text(record.get("source"))}`,
        target: `face:${text(record.get("target"))}`,
        label: `SIMILAR_TO ${score.toFixed(2)}`,
      });
    }

    const reviewRows = reviews.records.map((record) => ({
      decision: text(record.get("decision")),
      reviewer: text(record.get("reviewer")),
      timestamp: text(record.get("timestamp")),
      note: text(record.get("note")),
    }));

    return NextResponse.json({
      id: text(info.get("id")),
      riskScore: Number(info.get("riskScore") ?? 0),
      reasons: (info.get("reasons") as string[] | null) ?? [],
      flagged: Boolean(info.get("flagged")),
      subscriberCount: Number(info.get("subscriberCount") ?? people.length),
      decision: reviewRows[0]?.decision ?? null,
      reviews: reviewRows,
      people,
      graph: { nodes, links: graphLinks },
    });
  } catch (error) {
    return NextResponse.json({ error: dbErrorMessage(error) }, { status: 500 });
  }
}

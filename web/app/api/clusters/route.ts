import { NextResponse } from "next/server";
import { dbErrorMessage, run, text } from "@/lib/neo4j";

export const dynamic = "force-dynamic";

export async function GET() {
  try {
    const result = await run(`
      MATCH (i:Identity)
      WHERE coalesce(i.flagged, false) = true
      OPTIONAL MATCH (i)<-[:BELONGS_TO]-(:Face)<-[:HAS_FACE]-(s:Subscriber)
      WITH i, collect(DISTINCT s.name) AS names, count(DISTINCT s) AS subscribers
      OPTIONAL MATCH (i)-[:REVIEWED_AS]->(r:Review)
      WITH i, names, subscribers, r
      ORDER BY r.timestamp DESC
      WITH i, names, subscribers, collect(r)[0] AS latest
      RETURN i.id AS id,
             i.risk_score AS riskScore,
             i.reasons AS reasons,
             coalesce(i.sim_count, 0) AS sims,
             names,
             subscribers,
             latest.decision AS decision
      ORDER BY riskScore DESC
    `);

    const clusters = result.records.map((record) => ({
      id: text(record.get("id")),
      riskScore: Number(record.get("riskScore") ?? 0),
      reasons: (record.get("reasons") as string[] | null) ?? [],
      sims: Number(record.get("sims") ?? 0),
      names: (record.get("names") as string[] | null)?.filter(Boolean) ?? [],
      subscribers: Number(record.get("subscribers") ?? 0),
      decision: record.get("decision") ? text(record.get("decision")) : null,
    }));

    return NextResponse.json({ clusters });
  } catch (error) {
    return NextResponse.json({ error: dbErrorMessage(error) }, { status: 500 });
  }
}

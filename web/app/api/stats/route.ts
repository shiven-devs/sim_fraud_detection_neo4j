import { NextResponse } from "next/server";
import { faceServiceUrl } from "@/lib/face";
import { optionalEnv } from "@/lib/env";
import { dbErrorMessage, run } from "@/lib/neo4j";

export const dynamic = "force-dynamic";

export async function GET() {
  try {
    const totals = await run(`
      RETURN
        count { (:Subscriber) } AS subscribers,
        count { (:SIM) } AS sims,
        count { (:Identity) } AS identities,
        count { (i:Identity) WHERE coalesce(i.flagged, false) = true } AS suspicious
    `);
    const affected = await run(`
      MATCH (i:Identity)
      WHERE coalesce(i.flagged, false) = true
      MATCH (i)<-[:BELONGS_TO]-(:Face)<-[:HAS_FACE]-(:Subscriber)-[:OWNS]->(m:SIM)
      RETURN count(DISTINCT m) AS simsAffected
    `);

    const row = totals.records[0];
    let evaluation = null;
    let evaluationError: string | null = null;
    try {
      const response = await fetch(`${faceServiceUrl()}/evaluate`, { cache: "no-store" });
      if (!response.ok) {
        evaluationError = await response.text();
      } else {
        evaluation = await response.json();
      }
    } catch {
      evaluationError = "Face service is not running, so precision and recall are unavailable.";
    }

    return NextResponse.json({
      subscribers: row.get("subscribers") ?? 0,
      sims: row.get("sims") ?? 0,
      identities: row.get("identities") ?? 0,
      suspiciousClusters: row.get("suspicious") ?? 0,
      simsAffected: affected.records[0]?.get("simsAffected") ?? 0,
      precision: evaluation?.face_clusters?.precision ?? null,
      recall: evaluation?.face_clusters?.recall ?? null,
      evaluation,
      evaluationError,
      similarityThreshold: Number(optionalEnv("SIMILARITY_THRESHOLD", "0.8")),
      fuzzyNameThreshold: Number(optionalEnv("FUZZY_NAME_THRESHOLD", "85")),
    });
  } catch (error) {
    return NextResponse.json({ error: dbErrorMessage(error) }, { status: 500 });
  }
}

import { randomUUID } from "crypto";
import { NextResponse } from "next/server";
import { dbErrorMessage, run } from "@/lib/neo4j";

export const dynamic = "force-dynamic";

const DECISIONS = new Set(["confirmed_fraud", "rejected"]);

export async function POST(request: Request) {
  try {
    const body = await request.json();
    const identityId = String(body.identityId ?? "").trim();
    const decision = String(body.decision ?? "");
    const reviewer = String(body.reviewer ?? "").trim();
    const note = String(body.note ?? "").trim();

    if (!identityId) return NextResponse.json({ error: "Missing cluster id." }, { status: 400 });
    if (!DECISIONS.has(decision)) {
      return NextResponse.json({ error: "Decision must be confirmed_fraud or rejected." }, { status: 400 });
    }
    if (!reviewer) return NextResponse.json({ error: "Enter your name so the review is audited." }, { status: 400 });

    const found = await run("MATCH (i:Identity {id: $id}) RETURN i.id AS id", { id: identityId });
    if (found.records.length === 0) {
      return NextResponse.json({ error: "Cluster not found." }, { status: 404 });
    }

    await run(
      `
      MATCH (i:Identity {id: $identityId})
      CREATE (r:Review {
        id: $reviewId,
        decision: $decision,
        reviewer: $reviewer,
        timestamp: datetime(),
        note: $note
      })
      CREATE (i)-[:REVIEWED_AS]->(r)
      CREATE (:AuditLog {
        id: $auditId,
        action: "review",
        actor: $reviewer,
        timestamp: datetime(),
        target: $identityId,
        detail: $decision
      })
      `,
      {
        identityId,
        decision,
        reviewer,
        note,
        reviewId: `REV-${randomUUID()}`,
        auditId: `AUD-${randomUUID()}`,
      },
      "WRITE"
    );

    return NextResponse.json({ ok: true, decision });
  } catch (error) {
    return NextResponse.json({ error: dbErrorMessage(error) }, { status: 500 });
  }
}

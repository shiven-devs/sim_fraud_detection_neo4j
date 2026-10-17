import { randomUUID } from "crypto";
import { NextResponse } from "next/server";
import { faceServiceUrl } from "@/lib/face";
import { dbErrorMessage, run } from "@/lib/neo4j";

export const dynamic = "force-dynamic";
// Hobby still stops the function near 10 seconds. A warm face service usually fits; a cold model load may not.
export const maxDuration = 60;

export async function POST(request: Request) {
  try {
    const incoming = await request.formData();
    const file = incoming.get("file");
    const actor = String(incoming.get("actor") ?? "").trim();
    if (!(file instanceof File)) return NextResponse.json({ error: "Choose a photo to search." }, { status: 400 });
    if (!actor) return NextResponse.json({ error: "Enter your name so the search is audited." }, { status: 400 });
    if (file.size > 5_000_000) return NextResponse.json({ error: "Photo must be under 5 MB." }, { status: 400 });

    const outbound = new FormData();
    outbound.append("file", file, file.name || "upload.jpg");

    let response: Response;
    try {
      response = await fetch(`${faceServiceUrl()}/search`, {
        method: "POST",
        body: outbound,
        signal: AbortSignal.timeout(180000),
      });
    } catch {
      return NextResponse.json(
        { error: "Cannot reach the face service. Start it on FACE_SERVICE_URL (default http://localhost:8000)." },
        { status: 502 }
      );
    }

    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      const detail = typeof payload.detail === "string" ? payload.detail : "Face search failed.";
      return NextResponse.json({ error: detail }, { status: response.status });
    }

    const matches = Array.isArray(payload.matches) ? payload.matches : [];
    const top = matches[0];
    try {
      await run(
        `
        CREATE (:AuditLog {
          id: $id,
          action: "face_search",
          actor: $actor,
          timestamp: datetime(),
          target: $target,
          detail: $detail
        })
        `,
        {
          id: `AUD-${randomUUID()}`,
          actor,
          target: top?.faceId ?? "",
          detail: top ? `top score ${Number(top.score).toFixed(3)} across ${matches.length} matches` : "no matches",
        },
        "WRITE"
      );
    } catch (error) {
      return NextResponse.json({ error: dbErrorMessage(error), matches, threshold: payload.threshold ?? null }, { status: 500 });
    }

    return NextResponse.json({ threshold: payload.threshold ?? null, matches });
  } catch (error) {
    return NextResponse.json({ error: error instanceof Error ? error.message : "Search failed." }, { status: 500 });
  }
}

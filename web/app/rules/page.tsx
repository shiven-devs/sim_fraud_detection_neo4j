import { dbErrorMessage, run, text } from "@/lib/neo4j";

export const dynamic = "force-dynamic";

const SAME_FACE = `MATCH (i:Identity)<-[:BELONGS_TO]-(:Face)<-[:HAS_FACE]-(s:Subscriber)
WITH i, collect(DISTINCT s.name) AS names, count(DISTINCT s) AS n
WHERE n > 1
RETURN i, names, n`;

const TOO_MANY_SIMS = `MATCH (s:Subscriber)-[:OWNS]->(m:SIM)
WITH s, count(m) AS sims
WHERE sims > 8
RETURN s, sims`;

const VECTOR_SEARCH = `CALL db.index.vector.queryNodes('face_idx', 5, $embedding)
YIELD node, score`;

export default async function RulesPage() {
  try {
    const sameFace = await run(SAME_FACE);
    const tooMany = await run(TOO_MANY_SIMS);

    const faceRows = sameFace.records
      .map((record) => ({
        id: text(record.get("i").properties.id),
        names: (record.get("names") as string[]) ?? [],
        n: Number(record.get("n")),
      }))
      .sort((a, b) => b.n - a.n);

    const simRows = tooMany.records
      .map((record) => ({
        id: text(record.get("s").properties.id),
        name: text(record.get("s").properties.name),
        sims: Number(record.get("sims")),
      }))
      .sort((a, b) => b.sims - a.sims);

    return (
      <div className="space-y-8">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Rules</h1>
          <p className="mt-1 max-w-3xl text-sm text-stone-600">
            Two checks run as Cypher, independent of the risk-score write-up. Face search uses the vector index
            query and shows the score instead of hiding it behind a yes or no.
          </p>
        </div>

        <Rule title="Same face, multiple identities" query={SAME_FACE}>
          {faceRows.length === 0 ? (
            <p className="py-3 text-sm text-stone-500">No identity is linked to more than one subscriber yet.</p>
          ) : (
            <table className="min-w-full text-left text-sm">
              <thead className="text-xs uppercase tracking-wide text-stone-500">
                <tr>
                  <th className="py-2">Identity</th>
                  <th className="py-2">Names</th>
                  <th className="py-2">Subscribers</th>
                </tr>
              </thead>
              <tbody>
                {faceRows.map((row) => (
                  <tr key={row.id} className="border-t border-line">
                    <td className="py-2 font-mono text-xs">{row.id}</td>
                    <td className="py-2">{row.names.join(", ")}</td>
                    <td className="py-2 tabular-nums">{row.n}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Rule>

        <Rule title="More than 8 SIMs in one name" query={TOO_MANY_SIMS}>
          {simRows.length === 0 ? (
            <p className="py-3 text-sm text-stone-500">No subscriber holds more than 8 SIMs.</p>
          ) : (
            <table className="min-w-full text-left text-sm">
              <thead className="text-xs uppercase tracking-wide text-stone-500">
                <tr>
                  <th className="py-2">Subscriber</th>
                  <th className="py-2">Name</th>
                  <th className="py-2">SIMs</th>
                </tr>
              </thead>
              <tbody>
                {simRows.map((row) => (
                  <tr key={row.id} className="border-t border-line">
                    <td className="py-2 font-mono text-xs">{row.id}</td>
                    <td className="py-2">{row.name}</td>
                    <td className="py-2 tabular-nums">{row.sims}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Rule>

        <section className="space-y-2">
          <h2 className="text-lg font-semibold">Vector search</h2>
          <pre className="overflow-x-auto rounded-2xl bg-ink p-4 text-sm text-paper">{VECTOR_SEARCH}</pre>
          <p className="text-sm text-stone-600">
            Face search and clustering both call this index. The index is 512-dimensional cosine on Face.embedding.
            Clustering keeps a SIMILAR_TO edge only when the score is above SIMILARITY_THRESHOLD.
          </p>
        </section>
      </div>
    );
  } catch (error) {
    return <p className="rounded-xl border border-clay/30 bg-white px-4 py-3 text-sm text-clay">{dbErrorMessage(error)}</p>;
  }
}

function Rule({ title, query, children }: { title: string; query: string; children: React.ReactNode }) {
  return (
    <section className="space-y-2">
      <h2 className="text-lg font-semibold">{title}</h2>
      <pre className="overflow-x-auto rounded-2xl bg-ink p-4 text-sm text-paper">{query}</pre>
      <div className="overflow-x-auto rounded-2xl border border-line bg-white px-4 py-2 shadow-sm">{children}</div>
    </section>
  );
}

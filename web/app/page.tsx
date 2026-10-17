"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { percent, statusLabel } from "@/lib/format";

type Stats = {
  subscribers: number;
  sims: number;
  identities: number;
  suspiciousClusters: number;
  simsAffected: number;
  precision: number | null;
  recall: number | null;
  evaluationError: string | null;
  similarityThreshold: number;
  fuzzyNameThreshold: number;
  evaluation?: {
    excess_sims?: { caught?: boolean };
    shared_bank?: { caught?: boolean };
  };
};

type Cluster = {
  id: string;
  riskScore: number;
  reasons: string[];
  sims: number;
  names: string[];
  subscribers: number;
  decision: string | null;
};

function Pill({ decision }: { decision: string | null }) {
  const label = statusLabel(decision);
  const tone =
    decision === "confirmed_fraud"
      ? "bg-clay text-white"
      : decision === "rejected"
        ? "bg-stone-200 text-ink"
        : "bg-amber-100 text-amber-950";
  return <span className={`rounded-full px-2 py-0.5 text-xs ${tone}`}>{label}</span>;
}

export default function DashboardPage() {
  const [stats, setStats] = useState<Stats | null>(null);
  const [clusters, setClusters] = useState<Cluster[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    Promise.all([fetch("/api/stats").then((res) => res.json()), fetch("/api/clusters").then((res) => res.json())])
      .then(([statsBody, clusterBody]) => {
        if (statsBody.error) setError(statsBody.error);
        else setStats(statsBody);
        if (clusterBody.error) setError(clusterBody.error);
        else setClusters(clusterBody.clusters ?? []);
      })
      .catch(() => setError("Could not load the dashboard."));
  }, []);

  const cards = [
    ["Subscribers", stats ? String(stats.subscribers) : "…"],
    ["SIMs", stats ? String(stats.sims) : "…"],
    ["Suspicious clusters", stats ? String(stats.suspiciousClusters) : "…"],
    ["SIMs affected", stats ? String(stats.simsAffected) : "…"],
    ["Precision", percent(stats?.precision)],
    ["Recall", percent(stats?.recall)],
  ];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Review queue</h1>
        <p className="mt-1 max-w-3xl text-sm text-stone-600">
          Clusters are groups of faces the model considers one person. A high score means the same face sits on
          more than one identity, or one person holds more than eight SIMs. Nothing here is confirmed until a
          reviewer says so.
        </p>
      </div>

      {error && <p className="rounded-xl border border-clay/30 bg-white px-4 py-3 text-sm text-clay">{error}</p>}

      <section className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {cards.map(([label, value]) => (
          <article key={label} className="rounded-2xl border border-line bg-white px-4 py-3 shadow-sm">
            <p className="text-xs uppercase tracking-wide text-stone-500">{label}</p>
            <p className="mt-1 text-3xl font-semibold tabular-nums">{value}</p>
          </article>
        ))}
      </section>

      {stats && (
        <p className="text-sm text-stone-600">
          Face links use cosine similarity above {stats.similarityThreshold}. Name variants use token sort ratio
          above {stats.fuzzyNameThreshold}. Scores stay visible so a reviewer can disagree with the cut-off.
          {stats.evaluation?.excess_sims && (
            <> Excess-SIM rule: {stats.evaluation.excess_sims.caught ? "caught the planted case" : "has not caught the planted case yet"}.</>
          )}
          {stats.evaluation?.shared_bank && (
            <> Shared bank rule: {stats.evaluation.shared_bank.caught ? "caught the planted case" : "has not caught the planted case yet"}.</>
          )}
        </p>
      )}
      {stats?.evaluationError && <p className="text-sm text-stone-500">{stats.evaluationError}</p>}

      {stats && stats.subscribers === 0 && (
        <ol className="list-decimal space-y-1 rounded-2xl border border-line bg-white px-8 py-4 text-sm">
          <li>Copy .env.example to .env and start Neo4j with docker compose up -d.</li>
          <li>Run scripts/generate_data.py, then scripts/load_neo4j.py.</li>
          <li>Start the face service and run scripts/run_pipeline.py --skip-generate --skip-load.</li>
        </ol>
      )}
      {stats && stats.subscribers > 0 && stats.identities === 0 && (
        <p className="rounded-2xl border border-line bg-white px-4 py-3 text-sm">
          Subscribers are loaded, but faces are not clustered yet. Start the face service and run
          scripts/run_pipeline.py --skip-generate --skip-load.
        </p>
      )}

      <div className="overflow-x-auto rounded-2xl border border-line bg-white shadow-sm">
        <table className="min-w-full text-left text-sm">
          <thead className="border-b border-line text-xs uppercase tracking-wide text-stone-500">
            <tr>
              <th className="px-4 py-3">Cluster</th>
              <th className="px-4 py-3">Risk</th>
              <th className="px-4 py-3">Names</th>
              <th className="px-4 py-3">People</th>
              <th className="px-4 py-3">SIMs</th>
              <th className="px-4 py-3">Status</th>
            </tr>
          </thead>
          <tbody>
            {clusters.length === 0 && (
              <tr>
                <td colSpan={6} className="px-4 py-6 text-stone-500">
                  No flagged clusters yet.
                </td>
              </tr>
            )}
            {clusters.map((cluster) => (
              <tr key={cluster.id} className="border-t border-line">
                <td className="px-4 py-3 font-mono text-xs">
                  <Link href={`/clusters/${cluster.id}`} className="underline decoration-line underline-offset-2">
                    {cluster.id}
                  </Link>
                </td>
                <td className="px-4 py-3 tabular-nums">{cluster.riskScore}</td>
                <td className="px-4 py-3">{cluster.names.join(", ")}</td>
                <td className="px-4 py-3 tabular-nums">{cluster.subscribers}</td>
                <td className="px-4 py-3 tabular-nums">{cluster.sims}</td>
                <td className="px-4 py-3">
                  <Pill decision={cluster.decision} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

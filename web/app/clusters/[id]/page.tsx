"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import ClusterGraph, { type GraphData } from "@/components/ClusterGraph";
import { useReviewer } from "@/components/useReviewer";
import { statusLabel } from "@/lib/format";

type Sim = { number: string; activatedOn: string; tsp: string };
type Person = {
  faceId: string;
  subscriberId: string;
  name: string;
  dob: string;
  address: string;
  kycId: string;
  bankAccount: string;
  sims: Sim[];
};
type Review = { decision: string; reviewer: string; timestamp: string; note: string };
type Cluster = {
  id: string;
  riskScore: number;
  reasons: string[];
  decision: string | null;
  reviews: Review[];
  people: Person[];
  graph: GraphData;
};

export default function ClusterPage({ params }: { params: { id: string } }) {
  const { name, update } = useReviewer();
  const [cluster, setCluster] = useState<Cluster | null>(null);
  const [error, setError] = useState("");
  const [note, setNote] = useState("");
  const [saving, setSaving] = useState(false);

  function load() {
    fetch(`/api/clusters/${params.id}`)
      .then((res) => res.json())
      .then((body) => {
        if (body.error) setError(body.error);
        else {
          setError("");
          setCluster(body);
        }
      })
      .catch(() => setError("Could not load this cluster."));
  }

  useEffect(() => {
    load();
    // params.id is the only input that should reload the case.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [params.id]);

  async function decide(decision: "confirmed_fraud" | "rejected") {
    setSaving(true);
    setError("");
    const response = await fetch("/api/review", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ identityId: params.id, decision, reviewer: name, note }),
    });
    const body = await response.json();
    setSaving(false);
    if (!response.ok) {
      setError(body.error || "Could not save the review.");
      return;
    }
    setNote("");
    load();
  }

  if (!cluster && !error) return <p className="text-sm text-stone-500">Loading cluster…</p>;

  return (
    <div className="space-y-6">
      <Link href="/" className="text-sm text-stone-500 underline">
        Back to the queue
      </Link>
      {error && <p className="rounded-xl border border-clay/30 bg-white px-4 py-3 text-sm text-clay">{error}</p>}
      {cluster && (
        <>
          <div className="flex flex-wrap items-end justify-between gap-3">
            <div>
              <p className="font-mono text-xs text-stone-500">{cluster.id}</p>
              <h1 className="text-2xl font-semibold">Risk {cluster.riskScore}</h1>
              <p className="text-sm text-stone-600">{statusLabel(cluster.decision)}. Confirmation requires a reviewer.</p>
            </div>
          </div>

          <section className="rounded-2xl border border-line bg-white p-4 shadow-sm">
            <h2 className="text-sm font-semibold uppercase tracking-wide text-stone-500">Why this was flagged</h2>
            {cluster.reasons.length === 0 ? (
              <p className="mt-2 text-sm">No risk reasons stored. Run fuzzy-check if this cluster is new.</p>
            ) : (
              <ul className="mt-2 list-disc space-y-1 pl-5 text-sm">
                {cluster.reasons.map((reason) => (
                  <li key={reason}>{reason}</li>
                ))}
              </ul>
            )}
          </section>

          <section className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            {cluster.people.map((person) => (
              <article key={person.subscriberId} className="rounded-2xl border border-line bg-white p-4 shadow-sm">
                <img
                  src={`/api/faces?id=${encodeURIComponent(person.faceId)}`}
                  alt=""
                  className="h-44 w-full rounded-xl bg-stone-200 object-cover"
                />
                <h2 className="mt-3 text-lg font-semibold">{person.name}</h2>
                <dl className="mt-2 space-y-1 text-sm">
                  <div className="flex justify-between gap-3">
                    <dt className="text-stone-500">Date of birth</dt>
                    <dd>{person.dob}</dd>
                  </div>
                  <div className="flex justify-between gap-3">
                    <dt className="text-stone-500">KYC id</dt>
                    <dd className="font-mono text-xs">{person.kycId}</dd>
                  </div>
                  <div>
                    <dt className="text-stone-500">Address</dt>
                    <dd>{person.address}</dd>
                  </div>
                  <div>
                    <dt className="text-stone-500">Bank account</dt>
                    <dd className="font-mono text-xs">{person.bankAccount}</dd>
                  </div>
                </dl>
                <ul className="mt-3 space-y-1 text-sm">
                  {person.sims.map((sim) => (
                    <li key={sim.number} className="rounded-lg bg-paper px-2 py-1">
                      <span className="font-mono">{sim.number}</span>
                      <span className="text-stone-500"> · {sim.tsp} · {sim.activatedOn}</span>
                    </li>
                  ))}
                </ul>
              </article>
            ))}
          </section>

          <section className="space-y-3">
            <h2 className="text-sm font-semibold uppercase tracking-wide text-stone-500">Connections</h2>
            <ClusterGraph data={cluster.graph} />
          </section>

          <section className="rounded-2xl border border-line bg-white p-4 shadow-sm">
            <h2 className="text-sm font-semibold uppercase tracking-wide text-stone-500">Reviewer decision</h2>
            <p className="mt-1 text-sm text-stone-600">
              Confirm fraud only if you accept the face match. Reject when the photos are different people.
            </p>
            <label className="mt-3 block text-sm">
              Your name
              <input
                value={name}
                onChange={(event) => update(event.target.value)}
                className="mt-1 w-full max-w-sm rounded-lg border border-line bg-paper px-3 py-2"
                placeholder="Reviewer name"
              />
            </label>
            <label className="mt-3 block text-sm">
              Note
              <textarea
                value={note}
                onChange={(event) => setNote(event.target.value)}
                className="mt-1 w-full rounded-lg border border-line bg-paper px-3 py-2"
                rows={3}
              />
            </label>
            <div className="mt-3 flex flex-wrap gap-2">
              <button
                type="button"
                disabled={saving}
                onClick={() => decide("confirmed_fraud")}
                className="rounded-full bg-clay px-4 py-2 text-sm text-white disabled:opacity-50"
              >
                Confirm Fraud
              </button>
              <button
                type="button"
                disabled={saving}
                onClick={() => decide("rejected")}
                className="rounded-full border border-ink px-4 py-2 text-sm disabled:opacity-50"
              >
                Reject (false match)
              </button>
            </div>
            {cluster.reviews.length > 0 && (
              <ol className="mt-4 space-y-2 text-sm">
                {cluster.reviews.map((review) => (
                  <li key={`${review.timestamp}-${review.reviewer}`} className="border-t border-line pt-2">
                    <span className="font-medium">{statusLabel(review.decision)}</span> by {review.reviewer}
                    <span className="text-stone-500"> · {review.timestamp}</span>
                    {review.note && <p className="text-stone-600">{review.note}</p>}
                  </li>
                ))}
              </ol>
            )}
          </section>
        </>
      )}
    </div>
  );
}

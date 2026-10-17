"use client";

import { FormEvent, useState } from "react";
import { useReviewer } from "@/components/useReviewer";

type Match = {
  faceId: string;
  score: number;
  aboveThreshold: boolean;
  subscriberId: string;
  name: string;
  dob: string;
  address: string;
  kycId: string;
  bankAccount: string;
  sims: string[];
};

export default function SearchPage() {
  const { name, update } = useReviewer();
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState("");
  const [matches, setMatches] = useState<Match[]>([]);
  const [threshold, setThreshold] = useState<number | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (!file) {
      setError("Choose a photo first.");
      return;
    }
    setBusy(true);
    setError("");
    const body = new FormData();
    body.append("file", file);
    body.append("actor", name);
    const response = await fetch("/api/search", { method: "POST", body });
    const payload = await response.json();
    setBusy(false);
    if (!response.ok) {
      setMatches([]);
      setError(payload.error || "Search failed.");
      return;
    }
    setThreshold(payload.threshold ?? null);
    setMatches(payload.matches ?? []);
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Face search</h1>
        <p className="mt-1 max-w-3xl text-sm text-stone-600">
          Upload a photo to see the five nearest stored faces and their similarity scores. The search does not
          confirm a match. Your name is written to the audit log with the time of the search.
        </p>
      </div>

      <form onSubmit={onSubmit} className="space-y-3 rounded-2xl border border-line bg-white p-4 shadow-sm">
        <label className="block text-sm">
          Your name
          <input
            value={name}
            onChange={(event) => update(event.target.value)}
            className="mt-1 w-full max-w-sm rounded-lg border border-line bg-paper px-3 py-2"
            placeholder="Reviewer name"
          />
        </label>
        <label className="block text-sm">
          Photo
          <input
            type="file"
            accept="image/*"
            className="mt-1 block text-sm"
            onChange={(event) => {
              const next = event.target.files?.[0] ?? null;
              setFile(next);
              setPreview(next ? URL.createObjectURL(next) : "");
            }}
          />
        </label>
        {preview && <img src={preview} alt="" className="h-32 w-32 rounded-xl object-cover" />}
        <button type="submit" disabled={busy} className="rounded-full bg-ink px-4 py-2 text-sm text-white disabled:opacity-50">
          {busy ? "Searching… the first request loads the face model" : "Search"}
        </button>
        {error && <p className="text-sm text-clay">{error}</p>}
      </form>

      {threshold != null && (
        <p className="text-sm text-stone-600">
          Clustering threshold is {threshold}. A score under that line can still be a true match, and a score over
          it can still be a different person.
        </p>
      )}

      <div className="grid gap-3 md:grid-cols-2">
        {matches.map((match) => (
          <article key={match.faceId} className="rounded-2xl border border-line bg-white p-4 shadow-sm">
            <div className="flex gap-3">
              <img
                src={`/api/faces?id=${encodeURIComponent(match.faceId)}`}
                alt=""
                className="h-28 w-28 rounded-xl bg-stone-200 object-cover"
              />
              <div>
                <p className="text-2xl font-semibold tabular-nums">{match.score.toFixed(3)}</p>
                <p className="text-xs uppercase tracking-wide text-stone-500">
                  {match.aboveThreshold ? "Above the link threshold" : "Below the link threshold"}
                </p>
                <h2 className="mt-2 font-semibold">{match.name}</h2>
                <p className="text-sm text-stone-600">{match.dob}</p>
              </div>
            </div>
            <p className="mt-3 text-sm">{match.address}</p>
            <p className="mt-1 font-mono text-xs text-stone-600">{match.kycId}</p>
            <p className="font-mono text-xs text-stone-600">{match.bankAccount}</p>
            <p className="mt-2 text-sm">SIMs: {match.sims.join(", ") || "none"}</p>
          </article>
        ))}
      </div>
    </div>
  );
}

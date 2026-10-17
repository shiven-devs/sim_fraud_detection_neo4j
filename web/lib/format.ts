export function percent(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return "—";
  return `${Math.round(value * 100)}%`;
}

export function statusLabel(decision: string | null | undefined): string {
  if (decision === "confirmed_fraud") return "Confirmed fraud";
  if (decision === "rejected") return "Rejected";
  return "Pending review";
}

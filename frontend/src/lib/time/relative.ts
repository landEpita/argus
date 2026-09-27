/**
 * "4 min ago", "in 2 h", "3 d ago". Coarse on purpose: a live console needs the
 * order of magnitude at a glance, and precise times live in tooltips.
 */
export function formatRelative(iso: string, now: number = Date.now()): string {
  const then = Date.parse(iso);
  if (Number.isNaN(then)) return "—";
  const seconds = Math.round((then - now) / 1000);
  const abs = Math.abs(seconds);
  const future = seconds > 0;
  let value: string;
  if (abs < 45) return future ? "in a moment" : "just now";
  if (abs < 3600) value = `${Math.round(abs / 60)} min`;
  else if (abs < 86400) value = `${Math.round(abs / 3600)} h`;
  else value = `${Math.round(abs / 86400)} d`;
  return future ? `in ${value}` : `${value} ago`;
}

/** Exact UTC time for tooltips: "2026-09-27 15:04 UTC". */
export function formatUtc(iso: string): string {
  const date = new Date(iso);
  return Number.isNaN(date.getTime())
    ? "—"
    : `${date.toISOString().slice(0, 16).replace("T", " ")} UTC`;
}

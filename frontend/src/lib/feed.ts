/** Feed sorting and day filters (pure, so they're easy to test). */
export type FeedSort = "match" | "soonest";
export type DayFilter = "any" | "today" | "tomorrow" | "weekend";

export const SORTS: { value: FeedSort; label: string }[] = [
  { value: "match", label: "Best match" },
  { value: "soonest", label: "Soonest" },
];
export const DAYS: { value: DayFilter; label: string }[] = [
  { value: "any", label: "Any day" },
  { value: "today", label: "Today" },
  { value: "tomorrow", label: "Tomorrow" },
  { value: "weekend", label: "This weekend" },
];

const iso = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
const plus = (d: Date, n: number) => new Date(d.getFullYear(), d.getMonth(), d.getDate() + n);

/** Whether a group's local day (YYYY-MM-DD) falls in the filter, counted from `now` (the viewer's today). */
export function matchesDay(day: string, filter: DayFilter, now = new Date()): boolean {
  if (filter === "any") return true;
  if (filter === "today") return day === iso(now);
  if (filter === "tomorrow") return day === iso(plus(now, 1));
  // This weekend: the coming Saturday and Sunday (just today, if it's already Sunday).
  const dow = now.getDay(); // 0 = Sunday
  const sat = dow === 0 ? plus(now, -1) : plus(now, 6 - dow);
  return [iso(sat), iso(plus(sat, 1))].includes(day) && day >= iso(now);
}

/** Remembered per browser; any storage failure just means the default. */
export function remembered<T extends string>(key: string, allowed: readonly T[], fallback: T): T {
  try {
    const v = localStorage.getItem(key);
    return v && (allowed as readonly string[]).includes(v) ? (v as T) : fallback;
  } catch { return fallback; }
}

export function remember(key: string, value: string): void {
  try { localStorage.setItem(key, value); } catch { /* storage unavailable: fine */ }
}

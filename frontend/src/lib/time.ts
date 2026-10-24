// Timezone helpers. Availability is entered as wall-clock time in the plan's IANA timezone
// and sent to the API as UTC ISO strings; everything is rendered back in that timezone.

function partsIn(utcMs: number, timeZone: string) {
  const fmt = new Intl.DateTimeFormat("en-US", {
    timeZone, hourCycle: "h23", year: "numeric", month: "2-digit", day: "2-digit",
    hour: "2-digit", minute: "2-digit", second: "2-digit",
  });
  const p: Record<string, number> = {};
  for (const { type, value } of fmt.formatToParts(new Date(utcMs))) if (type !== "literal") p[type] = Number(value);
  return p;
}

/** Offset (ms) of `timeZone` from UTC at the given instant. */
function offsetAt(utcMs: number, timeZone: string): number {
  const p = partsIn(utcMs, timeZone);
  const asUtc = Date.UTC(p.year, p.month - 1, p.day, p.hour % 24, p.minute, p.second);
  return asUtc - Math.floor(utcMs / 1000) * 1000;
}

/** "2027-01-17" + "17:00" in "America/New_York" -> "2027-01-17T22:00:00Z". */
export function localToUtcIso(date: string, time: string, timeZone: string): string {
  const [y, m, d] = date.split("-").map(Number);
  const [hh, mm] = time.split(":").map(Number);
  const wall = Date.UTC(y, m - 1, d, hh, mm);
  let utc = wall - offsetAt(wall, timeZone);
  utc = wall - offsetAt(utc, timeZone); // second pass settles DST boundaries
  return new Date(utc).toISOString().replace(".000Z", "Z");
}

/** UTC ISO -> { date: "YYYY-MM-DD", time: "HH:mm" } as wall-clock in `timeZone`. */
export function utcToLocal(iso: string, timeZone: string): { date: string; time: string } {
  const p = partsIn(Date.parse(iso), timeZone);
  const pad = (n: number) => String(n).padStart(2, "0");
  return { date: `${p.year}-${pad(p.month)}-${pad(p.day)}`, time: `${pad(p.hour % 24)}:${pad(p.minute)}` };
}

export function formatDateTime(iso: string | null, timeZone: string, withZone = true): string {
  if (!iso) return "Time to be decided";
  if (/^\d{4}-\d{2}-\d{2}$/.test(iso)) return formatDay(iso);
  return new Intl.DateTimeFormat("en-US", {
    timeZone, weekday: "short", month: "short", day: "numeric", hour: "numeric", minute: "2-digit",
    timeZoneName: withZone ? "short" : undefined,
  }).format(new Date(iso));
}

export function formatTime(iso: string, timeZone: string): string {
  return new Intl.DateTimeFormat("en-US", { timeZone, hour: "numeric", minute: "2-digit" }).format(new Date(iso));
}

export function formatDay(iso: string, timeZone?: string): string {
  // Plain "YYYY-MM-DD" dates are calendar days, not instants: format them in UTC so they don't shift.
  const plain = /^\d{4}-\d{2}-\d{2}$/.test(iso);
  return new Intl.DateTimeFormat("en-US", {
    timeZone: plain ? "UTC" : timeZone, weekday: "short", month: "short", day: "numeric",
  }).format(new Date(plain ? `${iso}T00:00:00Z` : iso));
}

export function formatDateRange(start: string, end: string): string {
  const f = (s: string, o: Intl.DateTimeFormatOptions) =>
    new Intl.DateTimeFormat("en-US", { timeZone: "UTC", ...o }).format(new Date(`${s}T00:00:00Z`));
  if (start === end) return f(start, { month: "short", day: "numeric", year: "numeric" });
  const sameMonth = start.slice(0, 7) === end.slice(0, 7);
  return `${f(start, { month: "short", day: "numeric" })}–${f(end, sameMonth ? { day: "numeric" } : { month: "short", day: "numeric" })}, ${end.slice(0, 4)}`;
}

/** "2 min ago" style relative time for timelines and chat. */
export function relativeTime(iso: string, now = Date.now()): string {
  const s = Math.round((now - Date.parse(iso)) / 1000);
  if (s < 10) return "just now";
  if (s < 60) return `${s}s ago`;
  const m = Math.round(s / 60);
  if (m < 60) return `${m} min ago`;
  const h = Math.round(m / 60);
  if (h < 24) return `${h} h ago`;
  return formatDay(iso);
}

export const TIMEZONES = [
  "America/New_York", "America/Chicago", "America/Denver", "America/Phoenix", "America/Los_Angeles",
  "America/Anchorage", "Pacific/Honolulu", "America/Toronto", "America/Mexico_City", "Europe/London",
  "Europe/Paris", "Europe/Berlin", "Asia/Kolkata", "Asia/Singapore", "Asia/Tokyo", "Australia/Sydney",
];

export function browserTimeZone(): string {
  try { return Intl.DateTimeFormat().resolvedOptions().timeZone || "America/Chicago"; } catch { return "America/Chicago"; }
}

export interface LocalWindow { date: string; from: string; to: string }

function nextDay(date: string): string {
  const d = new Date(`${date}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + 1);
  return d.toISOString().slice(0, 10);
}

/** Wall-clock windows in the plan's timezone -> contract windows. An end at/before the start runs past midnight. */
export function windowsToUtc(windows: LocalWindow[], timeZone: string) {
  return windows.map((w) => ({
    starts_at: localToUtcIso(w.date, w.from, timeZone),
    ends_at: localToUtcIso(w.to <= w.from ? nextDay(w.date) : w.date, w.to, timeZone),
  }));
}

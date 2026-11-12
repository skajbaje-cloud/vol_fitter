// Time-zone helpers on the browser's built-in Intl API (no library).
// Backend timestamps are naive UTC strings; local schedule times are "HH:MM" wall-clock in a name's IANA zone.

export const utcDate = (naiveUtc: string) => new Date(naiveUtc.endsWith("Z") ? naiveUtc : `${naiveUtc}Z`);

function parts(date: Date, tz: string): Record<string, number> {
  const fmt = new Intl.DateTimeFormat("en-US", {
    timeZone: tz, hourCycle: "h23", year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit",
  });
  const out: Record<string, number> = {};
  for (const p of fmt.formatToParts(date)) if (p.type !== "literal") out[p.type] = Number(p.value);
  return out;
}

/** Minutes the zone is ahead of UTC at that instant (New York in winter: -300). */
export function offsetMinutes(tz: string, date = new Date()): number {
  const p = parts(date, tz);
  return Math.round((Date.UTC(p.year, p.month - 1, p.day, p.hour, p.minute) - Math.floor(date.getTime() / 60000) * 60000) / 60000);
}

export function offsetLabel(tz: string, date = new Date()): string {
  const m = offsetMinutes(tz, date);
  const sign = m < 0 ? "−" : "+";
  const h = Math.floor(Math.abs(m) / 60), mm = Math.abs(m) % 60;
  return `UTC${sign}${h}${mm ? `:${String(mm).padStart(2, "0")}` : ""}`;
}

/** Short zone name such as EST or CET, falling back to the UTC offset. */
export function tzAbbr(tz: string, date = new Date()): string {
  for (const locale of ["en-US", "en-GB"]) {
    const name = new Intl.DateTimeFormat(locale, { timeZone: tz, timeZoneName: "short" })
      .formatToParts(date).find((p) => p.type === "timeZoneName")?.value;
    if (name && !/^(GMT|UTC)[+−-]/.test(name)) return name;
  }
  return offsetLabel(tz, date);
}

export function hhmmIn(date: Date, tz?: string): string {
  return new Intl.DateTimeFormat("en-GB", { timeZone: tz, hour: "2-digit", minute: "2-digit", hourCycle: "h23" }).format(date);
}

export function todayIn(tz: string, date = new Date()): { y: number; m: number; d: number } {
  const p = parts(date, tz);
  return { y: p.year, m: p.month, d: p.day };
}

/** The instant when the wall clock in tz reads hhmm on local date ymd. */
export function wallToInstant(tz: string, ymd: { y: number; m: number; d: number }, hhmm: string): Date {
  const [h, mi] = hhmm.split(":").map(Number);
  const guess = Date.UTC(ymd.y, ymd.m - 1, ymd.d, h, mi);
  let t = guess - offsetMinutes(tz, new Date(guess)) * 60000;
  const second = offsetMinutes(tz, new Date(t));
  if (guess - second * 60000 !== t) t = guess - second * 60000;      // crossed a daylight-saving change
  return new Date(t);
}

export const userZone = () => Intl.DateTimeFormat().resolvedOptions().timeZone;

let zones: string[] | null = null;
export function allZones(): string[] {
  if (!zones) {
    const intl = Intl as unknown as { supportedValuesOf?: (k: string) => string[] };
    zones = intl.supportedValuesOf?.("timeZone") ?? ["America/New_York", "Europe/London", "Europe/Berlin", "Asia/Tokyo"];
  }
  return zones;
}

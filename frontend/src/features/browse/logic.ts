// The browse screens' logic (P-BRW-04, P-BRW-06, P-BRW-07, S7.19, S7.21). Pure functions: the clock arrives as an
// argument and nothing here reads one, so the tests pin it.
//
// TIME. The server sends every instant in the cinema's own offset (+05:30) and the client performs no zone
// arithmetic (P-BRW-06): a time is read off the string it was given, and "today" is the injected instant shifted
// by the offset those same strings carry - the cinema's today, never the device's.
// MONEY. Formatting is passed in (features/admin/money.ts's formatPaise), so the minor-unit ratio stays defined once.

const WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const DAY_MS = 86_400_000;

/** The day-button form, e.g. `Sat 15 Aug` (S7.19). Never `Today` or `Tomorrow`. */
export const DAY_LABEL = /^(Mon|Tue|Wed|Thu|Fri|Sat|Sun) [0-9]{1,2} [A-Z][a-z]{2}$/;

function offsetMs(iso: string): number {
  const m = /([+-])(\d{2}):(\d{2})$/.exec(iso);
  if (!m) return 0;
  return (m[1] === "-" ? -1 : 1) * (Number(m[2]) * 60 + Number(m[3])) * 60_000;
}

function localDate(instantMs: number, offset: number): string {
  return new Date(instantMs + offset).toISOString().slice(0, 10);
}

function daysFrom(first: string, last: string): string[] {
  const out: string[] = [];
  for (let t = Date.parse(`${first}T00:00:00Z`); t <= Date.parse(`${last}T00:00:00Z`); t += DAY_MS) {
    out.push(new Date(t).toISOString().slice(0, 10));
  }
  return out;
}

/** SCR-BRW-01's strip: today through the day before max(display_until) over the films this response returned.
 *  Empty when the array is: no bound, no strip, never a single dead day (P-BRW-04). */
export function listingStrip(nowMs: number, displayUntils: string[]): string[] {
  if (displayUntils.length === 0) return [];
  const offset = offsetMs(displayUntils[0]);
  const latest = Math.max(...displayUntils.map((d) => Date.parse(d)));
  return daysFrom(localDate(nowMs, offset), localDate(latest - 1, offset));
}

/** SCR-BRW-02's strip: today through the last day of this film's window (P-BRW-06). */
export function movieStrip(nowMs: number, displayUntil: string): string[] {
  return listingStrip(nowMs, [displayUntil]);
}

/** A selected day the strip no longer offers drops back to `Any date`, and the change is announced (P-BRW-04). */
export function keepDay(day: string | null, days: string[]): { day: string | null; cleared: boolean } {
  if (day === null || days.includes(day)) return { day, cleared: false };
  return { day: null, cleared: true };
}

export const DATE_CLEARED = "The date filter was cleared. Nothing in this list is showing on that day.";

/** What a listing response does to the filters: a selected day the new strip no longer offers drops back to
 *  `Any date`, and the change is announced (P-BRW-04). The caller re-requests with the returned filters.
 *  An EMPTY response has no strip to fall outside: the day stays, and the filtered empty state renders (S-BRW-06). */
export function settleListing<F extends { date: string | null }>(filters: F, displayUntils: string[], nowMs: number): { filters: F; announce: string | null } {
  if (displayUntils.length === 0 || !keepDay(filters.date, listingStrip(nowMs, displayUntils)).cleared) return { filters, announce: null };
  return { filters: { ...filters, date: null }, announce: DATE_CLEARED };
}

export function dayLabel(isoDate: string): string {
  const t = new Date(`${isoDate}T00:00:00Z`);
  return `${WEEKDAYS[t.getUTCDay()]} ${t.getUTCDate()} ${MONTHS[t.getUTCMonth()]}`;
}

/** `7:30 pm`, read off the instant's own offset (S7.19). */
export function timeLabel(iso: string): string {
  const hour = Number(iso.slice(11, 13));
  return `${hour % 12 || 12}:${iso.slice(14, 16)} ${hour < 12 ? "am" : "pm"}`;
}

export function showtimeName(st: { starts_at: string; screen: { name: string }; base_price_paise: number; sales_closed: boolean },
                             money: (paise: number) => string): string {
  const when = `${timeLabel(st.starts_at)}, ${st.screen.name}`;
  return st.sales_closed ? `${when}, sales closed` : `${when}, from ${money(st.base_price_paise)}`;
}

export interface Reference {
  cinemas: { id: number; name: string }[];
  languages: { id: number; name: string }[];
  formats: { id: number; name: string }[];
  certifications: { id: number; name: string }[];
}

/** Which reference-backed controls render: each only at two or more values (FR-ADR-046). A failed reference
 *  read renders none of them AND the one line that tells an outage from a correct day one (P-BRW-04 exc. 5). */
export function controlsFor(ref: Reference | null): { language: boolean; format: boolean; cinema: boolean; unavailable: boolean } {
  if (ref === null) return { language: false, format: false, cinema: false, unavailable: true };
  return { language: ref.languages.length >= 2, format: ref.formats.length >= 2, cinema: ref.cinemas.length >= 2, unavailable: false };
}

/** `1 film showing.` / `12 films showing.` - an interpolated count owes a singular (S7.21). */
export function countLine(n: number, noun: string, tail: string): string {
  return `${n} ${n === 1 ? noun : `${noun}s`} ${tail}.`;
}

export function runtimeName(minutes: number): string {
  return minutes === 1 ? "1 minute" : `${minutes} minutes`;
}

// CR-008 T9-T13: the discovery features' pure logic - search status, the landing rows, the carousel, ratings, recently
// viewed, share and "Add to calendar". No clock and no storage of its own: callers pass them in, so the tests pin them.
import type { Film } from "../browse/api";

// ---- T12: ratings -------------------------------------------------------------------------------------------------

export type Rating = { average_tenths: number | null; count: number };

/** `7.4` from 74 tenths; null while unrated. Integers on the wire, one decimal on screen. */
export function ratingText(r: Rating): string | null {
  return r.average_tenths === null || r.count === 0 ? null : `${Math.floor(r.average_tenths / 10)}.${r.average_tenths % 10}`;
}

/** The card badge's accessible name: "Rated 7.4 out of 10 by 3 people" / "New, not yet rated". */
export function ratingName(r: Rating): string {
  const t = ratingText(r);
  return t === null ? "New, not yet rated" : `Rated ${t} out of 10 by ${r.count} ${r.count === 1 ? "person" : "people"}`;
}

// ---- T10: the landing rows ----------------------------------------------------------------------------------------

export const ROW_SIZE = 6;

/** Top rated: rated films, best average first, more votes breaking a tie, then the listing's own order. */
export function topRated(films: Film[]): Film[] {
  return films.filter((f) => !f.coming_soon && f.rating.count > 0)
    .map((f, i) => ({ f, i }))
    .sort((a, b) => (b.f.rating.average_tenths! - a.f.rating.average_tenths!) || (b.f.rating.count - a.f.rating.count) || a.i - b.i)
    .map((x) => x.f);
}

export function rows(films: Film[]): { top: Film[]; now: Film[]; soon: Film[] } {
  const soon = films.filter((f) => f.coming_soon).sort((a, b) => (a.release_date ?? "").localeCompare(b.release_date ?? ""));
  return { top: topRated(films), now: films.filter((f) => !f.coming_soon), soon };
}

/** The hero carousel's films: the top rated first, topped up from what is showing, at most 5. */
export function featured(films: Film[]): Film[] {
  const top = topRated(films);
  const rest = films.filter((f) => !f.coming_soon && !top.includes(f));
  return [...top, ...rest].slice(0, 5);
}

// ---- T13a: the carousel's one status -------------------------------------------------------------------------------
// `stopped`: the viewer pressed Pause, or prefers reduced motion - nothing turns until they press Play.
// `holds`: why an otherwise playing carousel waits right now (pointer over it, focus inside, tab hidden, off-screen).

export type Hold = "hover" | "focus" | "hidden" | "offscreen";
export type Carousel = { index: number; count: number; stopped: boolean; holds: Hold[] };
export type CarouselEvent =
  | { type: "next" } | { type: "prev" } | { type: "go"; index: number } | { type: "tick" }
  | { type: "hold"; why: Hold } | { type: "release"; why: Hold } | { type: "stop" } | { type: "play" } | { type: "count"; count: number };

export function carousel(s: Carousel, e: CarouselEvent): Carousel {
  const at = (i: number) => (s.count ? (i + s.count) % s.count : 0);
  switch (e.type) {
    case "next": return { ...s, index: at(s.index + 1) };
    case "prev": return { ...s, index: at(s.index - 1) };
    case "go": return { ...s, index: at(e.index) };
    case "tick": return turning(s) ? { ...s, index: at(s.index + 1) } : s;
    case "hold": return s.holds.includes(e.why) ? s : { ...s, holds: [...s.holds, e.why] };
    case "release": return { ...s, holds: s.holds.filter((h) => h !== e.why) };
    case "stop": return { ...s, stopped: true };
    case "play": return { ...s, stopped: false };
    case "count": return { ...s, count: e.count, index: e.count ? Math.min(s.index, e.count - 1) : 0 };
  }
}

/** Whether the next tick may turn the slide. */
export function turning(s: Carousel): boolean {
  return !s.stopped && s.holds.length === 0 && s.count > 1;
}

// ---- T9: search's one status ---------------------------------------------------------------------------------------

export type Hit = { id: number; title: string; genres: { id: number; name: string }[]; poster_url: string; matched: "title" | "genre" };
export type Search =
  | { kind: "idle" } | { kind: "loading"; q: string } | { kind: "results"; q: string; items: Hit[] }
  | { kind: "error"; q: string };

export const SEARCH_MIN = 2;
export const SEARCH_WAIT_MS = 250;

/** What a typed value asks for: nothing under two characters, else a request. */
export function wants(q: string): string | null {
  const words = q.trim().replace(/\s+/g, " ");
  return words.length >= SEARCH_MIN ? words : null;
}

/** An answer counts only for the query it was asked for; anything older is dropped (with the abort, belt and braces). */
export function answered(s: Search, q: string, r: { ok: true; items: Hit[] } | { ok: false }): Search {
  if (s.kind !== "loading" || s.q !== q) return s;
  return r.ok ? { kind: "results", q, items: r.items } : { kind: "error", q };
}

/** Arrow keys over the options, wrapping; -1 is "nothing active" (focus stays in the box). */
export function moveActive(active: number, count: number, key: "ArrowDown" | "ArrowUp"): number {
  if (count === 0) return -1;
  if (key === "ArrowDown") return active + 1 >= count ? 0 : active + 1;
  return active <= 0 ? count - 1 : active - 1;
}

// ---- T13d: recently viewed (per browser) ---------------------------------------------------------------------------

export const RECENT_KEY = "fr.recent";
export const RECENT_MAX = 12;
type Store = Pick<Storage, "getItem" | "setItem">;

/** The ONE place the frontend touches localStorage (S-XCT-13 / S-XCT-43 allow this file and this key only): a list of
 *  film ids, never a token or anything about the account. A browser that refuses storage gets a store that keeps nothing. */
export function recentStore(): Store {
  try {
    const s = window.localStorage;
    s.getItem(RECENT_KEY);
    return s;
  } catch {
    return { getItem: () => null, setItem: () => undefined };
  }
}

export function readRecent(store: Store): number[] {
  try {
    const v = JSON.parse(store.getItem(RECENT_KEY) ?? "[]");
    return Array.isArray(v) ? v.filter((n) => Number.isInteger(n) && n > 0).slice(0, RECENT_MAX) : [];
  } catch {
    return [];
  }
}

/** The film moves to the front; the list keeps RECENT_MAX. A refusing store (a private window) is ignored. */
export function pushRecent(store: Store, id: number): number[] {
  const next = [id, ...readRecent(store).filter((n) => n !== id)].slice(0, RECENT_MAX);
  try {
    store.setItem(RECENT_KEY, JSON.stringify(next));
  } catch {
    // storage refused: nothing is remembered, the page is unchanged
  }
  return next;
}

/** The listing's films in viewed order, leaving out any that are no longer listed (and the one on screen). */
export function recentFilms(ids: number[], films: Film[], except?: number): Film[] {
  const byId = new Map(films.map((f) => [f.id, f]));
  return ids.filter((id) => id !== except).map((id) => byId.get(id)).filter((f): f is Film => Boolean(f));
}

// ---- T13c: share ----------------------------------------------------------------------------------------------------

export type Shared = { kind: "idle" } | { kind: "sharing" } | { kind: "shared" } | { kind: "copied" } | { kind: "manual"; url: string };

export const SHARE_COPIED = "Link copied. Paste it anywhere to share.";
export const SHARE_MANUAL = "Copy this link to share it:";

type ShareNav = { share?: (d: ShareData) => Promise<void>; clipboard?: { writeText: (t: string) => Promise<void> } };

/** Web Share where the browser has it; else the clipboard; else the link shown for copying by hand. */
export async function shareLink(nav: ShareNav, data: { title: string; text: string; url: string }): Promise<Shared> {
  if (nav.share) {
    try {
      await nav.share(data);
      return { kind: "shared" };
    } catch (e) {
      if ((e as { name?: string })?.name === "AbortError") return { kind: "idle" }; // the viewer closed the sheet
    }
  }
  try {
    if (!nav.clipboard) throw new Error("no clipboard");
    await nav.clipboard.writeText(data.url);
    return { kind: "copied" };
  } catch {
    return { kind: "manual", url: data.url };
  }
}

// ---- T13b: Add to calendar -----------------------------------------------------------------------------------------

/** An ISO instant with an offset (the server's `+05:30` form) as iCalendar UTC: 20261122T143000Z. */
export function icsUtc(iso: string): string {
  return new Date(iso).toISOString().replace(/[-:]/g, "").replace(/\.\d{3}/, "");
}

function icsText(s: string): string {
  return s.replace(/\\/g, "\\\\").replace(/;/g, "\\;").replace(/,/g, "\\,").replace(/\r?\n/g, "\\n");
}

/** One VEVENT for the booking. Times are UTC instants (Z), so every calendar shows them in its own zone correctly. */
export function bookingIcs(b: { reference: string; movie_title: string; hall_name: string; showtime_starts_at: string;
                                showtime_ends_at: string; seats: { seat_label: string }[] }, stampIso: string): string {
  const seats = b.seats.map((s) => s.seat_label).join(", ");
  return [
    "BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//FrontRow//Booking//EN", "CALSCALE:GREGORIAN", "METHOD:PUBLISH",
    "BEGIN:VEVENT",
    `UID:${b.reference}@frontrow`,
    `DTSTAMP:${icsUtc(stampIso)}`,
    `DTSTART:${icsUtc(b.showtime_starts_at)}`,
    `DTEND:${icsUtc(b.showtime_ends_at)}`,
    `SUMMARY:${icsText(`${b.movie_title} at FrontRow`)}`,
    `LOCATION:${icsText(`FrontRow, ${b.hall_name}`)}`,
    `DESCRIPTION:${icsText(`Booking ${b.reference}. Seats ${seats}. Show the reference at the entrance.`)}`,
    "END:VEVENT", "END:VCALENDAR", "",
  ].join("\r\n");
}

// ---- T16: the date grid ---------------------------------------------------------------------------------------------

/** The days in rows of 7, each with the month's short name where the month starts or changes (and on the first day). */
export function weekRows(days: string[]): { day: string; month: string | null }[][] {
  const out: { day: string; month: string | null }[][] = [];
  days.forEach((day, i) => {
    if (i % 7 === 0) out.push([]);
    const month = i === 0 || day.slice(5, 7) !== days[i - 1].slice(5, 7) ? MONTHS[Number(day.slice(5, 7)) - 1] : null;
    out[out.length - 1].push({ day, month });
  });
  return out;
}
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

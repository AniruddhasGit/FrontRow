// SCR-RPT-01's rules, with no DOM. Dates are CALENDAR dates ("2026-08-14") moved by calendar arithmetic only; no
// instant is converted on the client and nothing here reads the device's clock or zone (P-RPT-01).
import { getJson, type Get } from "../api";
import { paiseWords, pctWords } from "../format";

export type Period = "day" | "week" | "month";
export const PERIODS: [Period, string][] = [["day", "Day"], ["week", "Week"], ["month", "Month"]];

export interface Screen { screen_id: number; screen_name: string; is_active: boolean }
export interface Scope { role: string; scope_empty: boolean; all_halls: boolean; screens: Screen[]; today: string }
export interface Film { movie_id: number; title: string; shows: number; seats_sold: number; capacity: number; occupancy_pct: number | null; takings_paise: number }
export interface Dashboard {
  period: Period; scope_empty: boolean; screen_ids: number[]; takings_paise: number; seats_sold: number; capacity: number;
  occupancy_pct: number | null; shows: number; films: Film[]; films_truncated: boolean;
}
export interface ShowRow {
  showtime_id: number; starts_at: string; screen_id: number; screen_name: string; movie_id: number; title: string;
  seats_sold: number; capacity: number; occupancy_pct: number | null; takings_paise: number; has_started: boolean;
}
export interface Shows { total: number; limit: number; offset: number; rows: ShowRow[] }

// ---- calendar dates ----------------------------------------------------------------------------------------------
const DAYS = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];
const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];

interface Ymd { y: number; m: number; d: number }
const parse = (s: string): Ymd => ({ y: Number(s.slice(0, 4)), m: Number(s.slice(5, 7)), d: Number(s.slice(8, 10)) });
const pad = (n: number, w = 2) => String(n).padStart(w, "0");
const text = (c: Ymd) => `${pad(c.y, 4)}-${pad(c.m)}-${pad(c.d)}`;
// Date.UTC is used as a pure calendar calculator (day counts and weekdays); its time zone is never consulted.
const serial = (c: Ymd) => Date.UTC(c.y, c.m - 1, c.d) / 86400000;
const fromSerial = (n: number): Ymd => {
  const t = new Date(n * 86400000);
  return { y: t.getUTCFullYear(), m: t.getUTCMonth() + 1, d: t.getUTCDate() };
};
const weekday = (c: Ymd) => new Date(serial(c) * 86400000).getUTCDay();
const addDays = (c: Ymd, n: number) => fromSerial(serial(c) + n);
const monday = (c: Ymd) => addDays(c, -((weekday(c) + 6) % 7)); // ISO-8601, Monday-first

/** The anchor moved by one whole period; the result is the same kind of anchor (the 1st of a month for month). */
export function shift(anchor: string, period: Period, by: 1 | -1): string {
  const c = parse(anchor);
  if (period === "day") return text(addDays(c, by));
  if (period === "week") return text(addDays(monday(c), 7 * by));
  const month = c.m - 1 + by;
  return text({ y: c.y + Math.floor(month / 12), m: ((month % 12) + 12) % 12 + 1, d: 1 });
}

const dayForm = (c: Ymd, withYear: boolean) => `${DAYS[weekday(c)]} ${c.d} ${MONTHS[c.m - 1]}` + (withYear ? ` ${c.y}` : "");

/** SCR-RPT-01's period line, from the local anchor date only. */
export function periodLine(anchor: string, period: Period): string {
  const c = parse(anchor);
  if (period === "day") return dayForm(c, true);
  if (period === "month") return `${MONTHS[c.m - 1]} ${c.y}`;
  const first = monday(c);
  const last = addDays(first, 6);
  return first.y === last.y ? `${dayForm(first, false)} to ${dayForm(last, true)}` : `${dayForm(first, true)} to ${dayForm(last, true)}`;
}

export function stepperNames(period: Period): [string, string] {
  return [`Previous ${period}`, `Next ${period}`];
}

// ---- scope -------------------------------------------------------------------------------------------------------
export const isManager = (scope: Scope | null) => scope?.role === "manager";

/** "Halls shown: Hall 3, Hall 5." - names from EP-RPT-03, keyed on EP-RPT-01's screen_ids, ascending. */
export function scopeLine(scope: Scope, dash: Dashboard): string {
  const every = scope.screens.map((s) => s.screen_id);
  if (scope.all_halls && every.length === dash.screen_ids.length && every.every((id) => dash.screen_ids.includes(id))) {
    return "Halls shown: every hall.";
  }
  const names = [...dash.screen_ids].sort((a, b) => a - b).map((id) => scope.screens.find((s) => s.screen_id === id)?.screen_name ?? "");
  return `Halls shown: ${names.join(", ")}.`;
}

export function hallOptions(scope: Scope): [string, string][] {
  const first: [string, string] = ["", isManager(scope) ? "All my halls" : "All halls"];
  const rest = [...scope.screens].sort((a, b) => a.screen_id - b.screen_id)
    .map((s): [string, string] => [String(s.screen_id), s.is_active ? s.screen_name : `${s.screen_name} — out of service`]);
  return [first, ...rest];
}

// ---- requests ----------------------------------------------------------------------------------------------------
export interface Query { period: Period; anchor: string | null; screenId: string; offset: number }

/** `date` is omitted until the reader steps away from the server's today (the server owns "today"). */
export function query(q: Query): string {
  return [`period=${q.period}`, q.anchor ? `date=${q.anchor}` : "", q.screenId ? `screen_id=${q.screenId}` : ""].filter(Boolean).join("&");
}

export const dashboardUrl = (q: Query) => `/api/reports/dashboard?${query(q)}`;
export const showsUrl = (q: Query) => `/api/reports/showtimes?${query(q)}&limit=50&offset=${q.offset}`;

export interface Loaded { scope?: Scope; dash?: Dashboard; shows?: Shows; error?: unknown }

/** SCR-RPT-01's opening load: scope and dashboard together, neither waiting for the other; the showtimes listing only
 *  after the dashboard resolves, because it repeats the dashboard's period and scope exactly. */
export function openingLoad(get: Get, q: Query, on: (part: Loaded) => void): Promise<void> {
  const scope = getJson<Scope>(get, "/api/reports/scope").then((s) => on({ scope: s }), (error) => on({ error }));
  const rest = getJson<Dashboard>(get, dashboardUrl(q)).then(async (dash) => {
    on({ dash });
    if (!dash.scope_empty) on({ shows: await getJson<Shows>(get, showsUrl(q)) });
  }).catch((error) => on({ error }));
  return Promise.all([scope, rest]).then(() => undefined);
}

// ---- the per-film table ------------------------------------------------------------------------------------------
export type SortKey = "title" | "shows" | "seats_sold" | "capacity" | "occupancy_pct" | "takings_paise";
export const FILM_COLUMNS: [SortKey, string][] = [["title", "Film"], ["shows", "Shows"], ["seats_sold", "Seats sold"],
  ["capacity", "Capacity"], ["occupancy_pct", "Occupancy"], ["takings_paise", "Takings"]];
export interface Sort { key: SortKey; dir: "asc" | "desc" }
export const DEFAULT_SORT: Sort = { key: "takings_paise", dir: "desc" };

/** The chosen column, then title ascending, then movie_id ascending - the same total order as the server (P-RPT-05). */
export function sortFilms(films: Film[], sort: Sort): Film[] {
  const value = (f: Film) => (f[sort.key] ?? -1) as number | string;
  return [...films].sort((a, b) => {
    const x = value(a), y = value(b);
    const c = x < y ? -1 : x > y ? 1 : 0;
    return (sort.dir === "asc" ? c : -c) || a.title.localeCompare(b.title) || a.movie_id - b.movie_id;
  });
}

export function toggle(sort: Sort, key: SortKey): Sort {
  return sort.key === key ? { key, dir: sort.dir === "desc" ? "asc" : "desc" } : { key, dir: key === "title" ? "asc" : "desc" };
}

export function headerName(label: string, key: SortKey, sort: Sort): string {
  if (sort.key !== key) return `${label}, sort by this column`;
  return sort.dir === "desc" ? `${label}, sorted highest first. Activate to sort lowest first` : `${label}, sorted lowest first. Activate to sort highest first`;
}

// ---- announcements -----------------------------------------------------------------------------------------------
export function figuresSentence(dash: Dashboard): string {
  if (dash.scope_empty) return "";
  // No occupancy sentence when capacity is zero: the copy table publishes none, and the figure itself reads "—".
  const occupancy = dash.occupancy_pct === null ? "" : ` Occupancy ${pctWords(dash.occupancy_pct)}.`;
  return `Takings ${paiseWords(dash.takings_paise)}.${occupancy}`;
}

export function positionLine(shows: Shows): string {
  if (shows.total === 1) return "Showing the only show in this period";
  if (shows.total === 0) return "";
  return `Shows ${shows.offset + 1} to ${shows.offset + shows.rows.length} of ${shows.total}`;
}

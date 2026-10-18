// The seat map's client model (P-BRW-09, P-BRW-16, P-SEA-01..04, COMPONENTS.md §1-§2). Pure functions, no DOM,
// no network, no clock: the screen (SeatMapScreen.tsx) renders what these return.
//
// The server sends three objective states; the fourth, held_by_me, is computed HERE from the caller's own hold
// token and selection (FR-ADR-045). The client performs no money arithmetic beyond adding integers the server
// already rounded (FR-ADR-038): no multiplication, no division, no rounding.

export type WireState = "available" | "held" | "sold";
export type Visual = "available" | "sold" | "held_by_other" | "held_by_me";
export type Glyph = "outline" | "bar" | "hatch" | "check";

export interface Seat {
  id: number;
  row: string;
  num: number;
  gr: number;
  gc: number;
  cat: number;
  price_paise: number;
  state: WireState;
  is_active: boolean;
}
export interface Category {
  id: number;
  name: string;
  price_paise: number;
}
export interface SeatMap {
  showtime: { id: number; starts_at: string; sales_close_at: string; sales_closed: boolean };
  screen: { id: number; name: string; rows: number; cols: number };
  categories: Category[];
  seats: Seat[];
  generated_at: string;
  poll_interval_seconds: number;
}

// [JUDGMENT CALL] The server's MAX_SEATS_PER_BOOKING (S7.9, ruled 10) reaches the client through no endpoint, so the
// cap note needs its own copy of the number. The hold endpoint (Phase 4) is the enforcement point; this only stops
// an eleventh tap. If the server's value changes, this one must change with it - reported as a contract gap.
export const MAX_SEATS_PER_BOOKING = 10;

// sessionStorage keys (P-SEA-03). fr.selection is the live selection, rewritten on every change and deleted when
// it empties. fr.hold is the hold the Phase 4 hold path writes ({ hold_token, seats: [{ seat_id }] }); this screen
// only reads it. fr.pending_selection is the sign-in round trip's (lane E5) and is never written here.
export const SELECTION_KEY = "fr.selection";
export const HOLD_KEY = "fr.hold";

export const GLYPHS: Glyph[] = ["outline", "bar", "hatch", "check"];

// The four renderings, each told apart three ways: fill, mark, and border (COMPONENTS.md §1.4). The accessible
// name's ending is the fourth way, for a reader who sees none of them.
export const TREATMENT: Record<Visual, { fill: string; glyph: Glyph; ending: string }> = {
  available: { fill: "--fr-seat-available", glyph: "outline", ending: "available" },
  sold: { fill: "--fr-seat-sold", glyph: "hatch", ending: "sold" },
  held_by_other: { fill: "--fr-seat-held-other", glyph: "bar", ending: "held by another customer" },
  held_by_me: { fill: "--fr-seat-mine", glyph: "check", ending: "held by you" },
};

// The legend (SCR-BRW-03 copy): four states and the out-of-service swatch, which is not a fifth state.
export const LEGEND: { visual: Visual | "out_of_service"; label: string }[] = [
  { visual: "available", label: "Available" },
  { visual: "sold", label: "Sold" },
  { visual: "held_by_other", label: "Held by someone else" },
  { visual: "held_by_me", label: "Held by you" },
  { visual: "out_of_service", label: "Out of service" },
];

const STATES = new Set<string>(["available", "held", "sold"]);
const isInt = (v: unknown): v is number => typeof v === "number" && Number.isInteger(v);
const isPaise = (v: unknown): v is number => isInt(v) && v >= 0;

/** The payload, or null when anything in it could make a seat lie: a fourth state, a seat with no is_active, a
 *  price that is not a non-negative integer. Rejected, never defaulted (P-BRW-09 server-side validation). */
export function parseSeatMap(raw: unknown): SeatMap | null {
  const m = raw as SeatMap;
  if (!m || typeof m !== "object" || !m.showtime || !m.screen || !Array.isArray(m.seats) || !Array.isArray(m.categories)) return null;
  if (typeof m.showtime.sales_closed !== "boolean" || !isInt(m.poll_interval_seconds) || m.poll_interval_seconds < 1) return null;
  if (!isInt(m.screen.rows) || !isInt(m.screen.cols)) return null;
  for (const c of m.categories) if (!isInt(c.id) || typeof c.name !== "string" || !isPaise(c.price_paise)) return null;
  for (const s of m.seats) {
    if (!isInt(s.id) || !isInt(s.gr) || !isInt(s.gc) || !isInt(s.num) || !isInt(s.cat) || typeof s.row !== "string") return null;
    if (!STATES.has(s.state) || typeof s.is_active !== "boolean" || !isPaise(s.price_paise)) return null;
  }
  return m;
}

/** held_by_me when the seat is in the caller's own hold or selection; otherwise the wire state as drawn. */
export function visualOf(seat: Seat, mine: ReadonlySet<number>): Visual {
  // A chosen seat that has since been taken leaves the selection on the same poll (recheck), before it renders.
  if (seat.state !== "sold" && mine.has(seat.id)) return "held_by_me";
  if (seat.state === "held") return "held_by_other";
  return seat.state;
}

export function seatLabel(seat: Seat): string {
  return `${seat.row}${seat.num}`;
}

/** `Row C seat 12, Premium, available` - identity, category and state (COMPONENTS.md §1.6). */
export function seatName(seat: Seat, categoryName: string, visual: Visual): string {
  const ending = seat.is_active ? TREATMENT[visual].ending : "out of service";
  return `Row ${seat.row} seat ${seat.num}, ${categoryName}, ${ending}`;
}

/** A tap does something only on an in-service seat that is free or the caller's own, while sales are open. */
export function selectable(seat: Seat, visual: Visual, salesClosed: boolean): boolean {
  return seat.is_active && !salesClosed && (visual === "available" || visual === "held_by_me");
}

/** A tap: add or remove, locally, sending nothing. The eleventh seat is refused and nothing changes. */
export function toggle(selection: number[], seat: Seat, visual: Visual, max = MAX_SEATS_PER_BOOKING): { selection: number[]; refused: boolean } {
  if (selection.includes(seat.id)) return { selection: selection.filter((id) => id !== seat.id), refused: false };
  if (!selectable(seat, visual, false)) return { selection, refused: false };
  if (selection.length >= max) return { selection, refused: true };
  return { selection: [...selection, seat.id], refused: false };
}

export function capNote(max: number): string {
  return `Up to ${max} seats.`;
}

/** The running total: the integer sum of the payload's own price_paise, or null when a chosen seat has no known
 *  price - and then no total is rendered at all, never a zero (P-SEA-04). */
export function total(selection: number[], seats: ReadonlyMap<number, Seat>): number | null {
  let sum = 0;
  for (const id of selection) {
    const seat = seats.get(id);
    if (!seat) return null;
    sum += seat.price_paise;
  }
  return sum;
}

/** Re-check a restored or carried selection against a fresh map: what stays chosen, and what has gone. */
export function recheck(selection: number[], map: SeatMap): { kept: number[]; gone: Seat[] } {
  const byId = new Map(map.seats.map((s) => [s.id, s]));
  const kept: number[] = [];
  const gone: Seat[] = [];
  for (const id of selection) {
    const seat = byId.get(id);
    if (seat && seat.is_active && seat.state === "available") kept.push(id);
    else if (seat) gone.push(seat);
  }
  return { kept, gone };
}

/** P-SEA-03's sentence, one per seat that went, in ONE banner. The plural form is unpublished, so the published
 *  singular sentence is repeated rather than inventing a new one (reported as a copy gap). */
export function goneBanner(gone: Seat[]): string | null {
  if (gone.length === 0) return null;
  return gone.map((s) => `${seatLabel(s)} is no longer available. It has been removed from your choices.`).join(" ");
}

/** The one standing-condition banner over the map, or null. Each string is its owner's (P-BRW-07, P-BRW-08, P-BRW-09). */
export function mapBanner(map: SeatMap): string | null {
  if (map.showtime.sales_closed) return "Sales for this showtime have closed.";
  if (map.seats.every((s) => !s.is_active)) return "None of the seats in this hall are available.";
  if (map.seats.every((s) => s.state === "sold")) return "Every seat for this showtime is sold.";
  return null;
}

/** Seats whose wire state or service changed between two polls - they keep the change ring (COMPONENTS.md §1.7). */
export function changedSeats(before: SeatMap | null, after: SeatMap): Set<number> {
  const changed = new Set<number>();
  if (!before) return changed;
  const old = new Map(before.seats.map((s) => [s.id, s]));
  for (const s of after.seats) {
    const was = old.get(s.id);
    if (was && (was.state !== s.state || was.is_active !== s.is_active)) changed.add(s.id);
  }
  return changed;
}

/** P-BRW-16's bands: maximal runs of grid rows that each hold exactly one category. A row with no seat (void) is
 *  inside a band and does not break it; a row with two categories (mixed) belongs to none and ends the run.
 *  Only compares gr values with each other, so it holds whatever base the rows are numbered from. */
export function bands(map: Pick<SeatMap, "seats"> & { screen: { rows: number } }): { cat: number; from: number; to: number }[] {
  const cats = new Map<number, Set<number>>();
  for (const s of map.seats) {
    if (!cats.has(s.gr)) cats.set(s.gr, new Set());
    cats.get(s.gr)!.add(s.cat);
  }
  const rows = [...cats.keys()].sort((a, b) => a - b);
  const out: { cat: number; from: number; to: number }[] = [];
  let open: { cat: number; from: number; to: number } | null = null;
  for (const gr of rows) {
    const here = cats.get(gr)!;
    if (here.size !== 1) {
      if (open) out.push(open);
      open = null;
      continue;
    }
    const cat = [...here][0];
    if (open && open.cat === cat) open.to = gr;
    else {
      if (open) out.push(open);
      open = { cat, from: gr, to: gr };
    }
  }
  if (open) out.push(open);
  return out;
}

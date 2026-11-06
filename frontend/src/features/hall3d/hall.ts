// The 3D hall's geometry, from the seat-map payload alone (FR-ADR-074, CR-001 Part B). Pure: no three.js, no DOM,
// no runtime import, so node --test loads it directly. Nothing here knows the six halls: an aisle is an empty grid
// column, a walkway an empty grid row, a row may be any length, and a seat may span two columns.
import type { Seat } from "../seatmap/model";

export const PITCH_X = 0.62; // metres per grid column
export const PITCH_Z = 1.05; // metres per grid row
export const RISE = 0.22; // the rake: the floor climbs this much per grid row
export const EYE = 1.15; // seated eye height above the tier
export const SCREEN_GAP = 5; // front row to the screen

export interface Placed { seat: Seat; x: number; y: number; z: number; span: number }
export interface Hall {
  placed: Placed[];
  halfWidth: number; // half the width of the seat block
  tiers: { gr: number; y: number; z: number }[]; // every grid row, first to last, walkways included
  aisles: number[]; // the centre x of each run of empty columns inside the block
  walkways: number[]; // grid rows inside the block that hold no seat
  screen: { width: number; height: number; y: number; z: number };
  depth: number; // z of the last row
  top: number; // floor height of the last row
}

/** The columns a seat takes. A row whose seats all sit two columns apart is a row of wide seats (CR-001 A.3, the
 *  recliner row); any row with a one-column step is ordinary, so its two-column gaps stay aisles. */
// ponytail: inferred from spacing because the payload carries no seat width; a row of exactly two seats split by a
// one-column aisle reads as wide. Upgrade path: a `span` field on the seat-map seat.
function spans(seats: Seat[]): Map<number, number> {
  const rows = new Map<number, Seat[]>();
  for (const s of seats) rows.set(s.gr, [...(rows.get(s.gr) ?? []), s]);
  const out = new Map<number, number>();
  for (const row of rows.values()) {
    row.sort((a, b) => a.gc - b.gc);
    let step = Infinity;
    for (let i = 1; i < row.length; i++) step = Math.min(step, row[i].gc - row[i - 1].gc);
    for (const s of row) out.set(s.id, step === 2 ? 2 : 1);
  }
  return out;
}

export function computeHall(seats: Seat[]): Hall {
  if (seats.length === 0) {
    return { placed: [], halfWidth: 4, tiers: [], aisles: [], walkways: [], screen: { width: 8, height: 3.4, y: 2.9, z: -SCREEN_GAP }, depth: 0, top: 0 };
  }
  const span = spans(seats);
  const grMin = Math.min(...seats.map((s) => s.gr));
  const grMax = Math.max(...seats.map((s) => s.gr));
  const gcMin = Math.min(...seats.map((s) => s.gc));
  const gcEnd = Math.max(...seats.map((s) => s.gc + span.get(s.id)!));
  const mid = (gcMin + gcEnd) / 2;
  const used = new Set<number>();
  const rowsUsed = new Set<number>();
  for (const s of seats) {
    rowsUsed.add(s.gr);
    for (let c = s.gc; c < s.gc + span.get(s.id)!; c++) used.add(c);
  }
  const placed = seats.map((s) => {
    const w = span.get(s.id)!;
    return { seat: s, span: w, x: (s.gc + w / 2 - mid) * PITCH_X, y: (s.gr - grMin) * RISE, z: (s.gr - grMin) * PITCH_Z };
  });
  const aisles: number[] = [];
  for (let c = gcMin; c < gcEnd; c++) {
    if (used.has(c)) continue;
    let end = c;
    while (end + 1 < gcEnd && !used.has(end + 1)) end++;
    aisles.push(((c + end + 1) / 2 - mid) * PITCH_X);
    c = end;
  }
  const tiers = [];
  const walkways = [];
  for (let gr = grMin; gr <= grMax; gr++) {
    tiers.push({ gr, y: (gr - grMin) * RISE, z: (gr - grMin) * PITCH_Z });
    if (!rowsUsed.has(gr)) walkways.push(gr);
  }
  const halfWidth = ((gcEnd - gcMin) * PITCH_X) / 2;
  const width = Math.max(6, halfWidth * 1.7);
  const height = width / 2.39; // scope
  return {
    placed, halfWidth, tiers, aisles, walkways, depth: (grMax - grMin) * PITCH_Z, top: (grMax - grMin) * RISE,
    screen: { width, height, y: height / 2 + 1.4, z: -SCREEN_GAP },
  };
}

export type Mode = "overview" | "seat" | "screen";
export interface View { at: [number, number, number]; look: [number, number, number] }

/** The three cameras. `seat` sits at the given seat's real position and eye height and looks at the screen; with no
 *  seat chosen it takes the centre of the middle row. */
export function views(hall: Hall, seatId: number | null): Record<Mode, View> {
  const { screen, depth, top } = hall;
  const chosen = hall.placed.find((p) => p.seat.id === seatId);
  const sit = chosen ?? { x: 0, y: top / 2, z: depth / 2 };
  return {
    overview: { at: [0, top + 6, depth + 7], look: [0, 1.4, depth * 0.3 - 1] },
    seat: { at: [sit.x, sit.y + EYE, sit.z], look: [0, screen.y, screen.z] },
    screen: { at: [0, screen.y - 0.4, screen.z + 1], look: [0, top * 0.6, depth * 0.7] },
  };
}

export type ModelKind = "standard" | "premium" | "recliner";
export const MODEL_URL: Record<ModelKind, string> = {
  standard: "/models/seat_standard.glb",
  premium: "/models/seat_premium.glb",
  recliner: "/models/seat_recliner.glb",
};

/** Category name to seat model. The names are ASSUMED (OPEN-SEAT-01), so an unknown name is a standard seat. */
export function modelKind(categoryName: string): ModelKind {
  const n = categoryName.trim().toLowerCase();
  return n === "premium" || n === "recliner" ? n : "standard";
}

// The 3D hall's geometry, from the seat-map payload alone (FR-ADR-074, CR-001 Part B). Pure: no three.js, no DOM,
// no runtime import, so node --test loads it directly. Nothing here knows the six halls: an aisle is an empty grid
// column, a walkway an empty grid row, a row may be any length, and a seat may span two columns.
import type { Seat, Visual } from "../seatmap/model";

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

export type Mode = "all" | "seat";
export interface View { at: [number, number, number]; look: [number, number, number] }

/** The screen-side camera that frames every seat: it looks at the middle of the seat block from in front of it,
 *  as low as it can while every corner of the block fits the frustum (fov in degrees, aspect = width / height) and
 *  the camera stays in front of the screen. A wide hall therefore sits higher and farther back than a narrow one. */
export function allSeats(hall: Hall, aspect: number, fov = 50): View {
  const { halfWidth, depth, top, screen } = hall;
  const look: [number, number, number] = [0, top / 2 + 0.5, depth / 2];
  const ty = Math.tan((fov * Math.PI) / 360) * 0.9; // 10% breathing room at the frame's edge
  const tx = ty * aspect;
  const corners = [-1, 1].flatMap((sx) => [0, top + 1.3].flatMap((y) => [-0.6, depth + 0.6].map((z) => [sx * (halfWidth + 0.3), y - look[1], z - look[2]])));
  let at: [number, number, number] = [0, 0, 0];
  for (let deg = 20; deg <= 80; deg += 5) {
    const s = Math.sin((deg * Math.PI) / 180);
    const c = Math.cos((deg * Math.PI) / 180);
    // Camera space: right is -x, up (0, c, s), forward (0, -s, c); a corner fits when its offset / its depth <= tan.
    const dist = Math.max(...corners.map(([x, y, z]) => {
      const fwd = -s * y + c * z;
      return Math.max(Math.abs(x) / tx, Math.abs(c * y + s * z) / ty) - fwd;
    }));
    at = [0, look[1] + dist * s, look[2] - dist * c];
    if (at[2] >= screen.z + 0.6) break;
  }
  return { at, look };
}

/** The two cameras. `all` is allSeats(); `seat` sits at the given seat's real position and eye height and looks at
 *  the screen's centre, and with no seat given it takes the centre of the middle row. */
export function views(hall: Hall, seatId: number | null, aspect: number): Record<Mode, View> {
  const { screen, depth, top } = hall;
  const chosen = hall.placed.find((p) => p.seat.id === seatId);
  const sit = chosen ?? { x: 0, y: top / 2, z: depth / 2 };
  return {
    all: allSeats(hall, aspect),
    seat: { at: [sit.x, sit.y + EYE, sit.z], look: [0, screen.y, screen.z] },
  };
}

/** Why a seat cannot be chosen, in the hall's words, or null when it is free. Its state, never a price. */
export function stateWord(seat: Seat, visual: Visual): string | null {
  if (!seat.is_active) return "Not available";
  return visual === "sold" ? "Taken" : visual === "held_by_other" ? "Being held" : visual === "held_by_me" ? "Yours" : null;
}

/** The hover label: `Row F · Seat 7 · Premium · $14.61`, the price replaced by the state when the seat is not free.
 *  `price` comes formatted (formatPaise), so this file stays free of runtime imports. */
export function seatTip(seat: Seat, category: string, visual: Visual, price: string): string {
  return `Row ${seat.row} · Seat ${seat.num} · ${category} · ${stateWord(seat, visual) ?? price}`;
}

/** CR-003: the per-hall file /halls/hallN.json written by the Blender bake (seat positions and cameras in three.js
 *  metres; the room itself is hallN.glb). Seats face +z (the screen is at z ~ 0, the rows at -z). */
export interface BakedMeta {
  hall: number; allseats: { eye: number[]; look: number[] }; screen: { w: number; h: number; zc: number; z: number };
  seats: { id: string; row: string; num: number; cat: string; level: string; pos: number[]; eye: number[] }[];
  /** The arrival route, ENTRY door to the all-seats view (hall_path.py); the live camera flies it, no video. */
  intro?: { eye: number[]; look: number[] }[];
}
/** CR-004: the seat page's arrival. Seated in the middle of the front level, facing the film on the screen; then up and
 *  round by the side wall (so the look point never passes through the eye) onto the all-seats view. */
export function screenFirst(meta: BakedMeta): { eye: number[]; look: number[] }[] {
  const front = meta.seats.filter((s) => s.level === meta.seats[0].level);
  const sit = front[Math.floor(front.length / 2)].eye;
  const { eye: ae, look: al } = meta.allseats;
  const wall = Math.max(...meta.seats.map((s) => Math.abs(s.pos[0]))) + 2;
  const mid = [(sit[0] + ae[0]) / 2, Math.max(sit[1], ae[1]) + 0.3, (sit[2] + ae[2]) / 2];
  return [{ eye: sit, look: [0, meta.screen.zc - 0.35, meta.screen.z] }, { eye: mid, look: [wall, mid[1], mid[2]] }, { eye: ae, look: al }];
}
export interface Baked { placed: Placed[]; meta: BakedMeta; views: (seatId: number | null) => Record<Mode, View> }

const v3 = (a: number[]) => [a[0], a[1], a[2]] as [number, number, number];

/** The API's seats on the baked hall's positions, matched by row and number - or null when the two layouts differ in
 *  any seat (then the procedural hall is drawn: a stale file never misplaces a bookable seat). */
export function bakedHall(seats: Seat[], meta: BakedMeta): Baked | null {
  const at = new Map(meta.seats.map((m) => [`${m.row}${m.num}`, m]));
  if (!seats.length || seats.length !== at.size) return null;
  const placed: Placed[] = [];
  for (const seat of seats) {
    const m = at.get(`${seat.row}${seat.num}`);
    if (!m) return null;
    placed.push({ seat, x: m.pos[0], y: m.pos[1], z: m.pos[2], span: 1 });
  }
  const eye = new Map(seats.map((s) => [s.id, at.get(`${s.row}${s.num}`)!.eye]));
  const screen: [number, number, number] = [0, meta.screen.zc - 0.35, meta.screen.z];
  const all = { at: v3(meta.allseats.eye), look: v3(meta.allseats.look) };
  return {
    placed, meta,
    views: (seatId) => ({ all, seat: { at: v3(eye.get(seatId ?? -1) ?? meta.seats[Math.floor(meta.seats.length / 2)].eye), look: screen } }),
  };
}

/** "SCREEN 4" -> 4: which hall's files to ask for. Anything else has no baked hall. */
export function screenNumber(name: string): number | null {
  const m = /^screen\s+(\d+)$/i.exec(name.trim());
  return m ? Number(m[1]) : null;
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

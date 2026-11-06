// The sign-in screen's rules (SCR-ACC-01, P-ACC-13), with no DOM, no clock and no relative import.
// Run: node --test frontend/src/features/auth/auth.test.mjs

export const PENDING_KEY = "fr.pending_selection";
export const PENDING_MAX_AGE_MS = 30 * 60 * 1000; // P-ACC-13: a stored selection older than 30 minutes is discarded
export const CONTEXT_NOTE = "Your seats are still selected. Sign in to hold them.";
export const SHOWTIME_GONE = "That showtime is no longer available.";
const SELECTION_KEY = "fr.selection"; // E2 P-SEA-03's live selection (seatmap/model.ts); a different key, read here only
const NOTICE_KEY = "fr.notice"; // one sentence handed to the listing, read once; inside the fr. sign-out sweep

interface Store {
  getItem(key: string): string | null;
  removeItem(key: string): void;
}
interface Writable extends Store {
  setItem(key: string, value: string): void;
}

const SEAT_MAP = /^\/showtimes\/(\d+)$/;

/** The sign-in address. From a seat map it carries the map's own path (no seat ids), so a sign-in returns there even
 *  when storage is unavailable. [JUDGMENT CALL] Both routes out of a seat map carry it, with or without a selection. */
export function signInHref(pathname: string): string {
  return SEAT_MAP.test(pathname) ? `/sign-in?next=${encodeURIComponent(pathname)}` : "/sign-in";
}

/** P-ACC-13: leaving a seat map for sign-in, by either route, with a non-empty selection writes fr.pending_selection
 *  once, from fr.selection, stamped with the BROWSER's clock (`nowMs`). fr.selection is left as it is. */
export function leaveForSignIn(pathname: string, store: Writable, nowMs: number): void {
  const m = SEAT_MAP.exec(pathname);
  if (!m) return;
  try {
    const live = JSON.parse(store.getItem(SELECTION_KEY) ?? "null");
    if (live?.showtime_id !== Number(m[1]) || !Array.isArray(live.seat_ids) || live.seat_ids.length === 0) return;
    const stored_at = new Date(nowMs).toISOString().replace(/\.\d{3}Z$/, "Z");
    store.setItem(PENDING_KEY, JSON.stringify({ showtime_id: live.showtime_id, seat_ids: live.seat_ids, stored_at }));
  } catch {
    // storage unavailable: nothing is stored and nothing is said
  }
}

/** P-ACC-13 exceptions 1, 1a and 2: the seats that went while signing in, labels in the order chosen. */
export function takenMessage(gone: string[], kept: number): string | null {
  if (gone.length === 0) return null;
  if (kept === 0) return "The seats you chose were taken while you were signing in. Choose again from the map.";
  const names = gone.length === 1 ? gone[0] : `${gone.slice(0, -1).join(", ")} and ${gone[gone.length - 1]}`;
  return `${names} ${gone.length === 1 ? "was" : "were"} taken while you were signing in. Your other seats are still selected.`;
}

export function leaveNotice(store: Writable, sentence: string): void {
  try {
    store.setItem(NOTICE_KEY, sentence);
  } catch {
    // no storage: the listing opens without the sentence
  }
}

export function takeNotice(store: Store): string | null {
  try {
    const sentence = store.getItem(NOTICE_KEY);
    store.removeItem(NOTICE_KEY);
    return sentence;
  } catch {
    return null;
  }
}

export interface Pending {
  showtime_id: number;
  seat_ids: number[];
  stored_at: string;
}

/** The pending selection if it is fresh by the BROWSER's clock (`nowMs`), else null. A stale one is removed together
 *  with the fr.selection it was taken from, so the map opens with no selection (P-ACC-13 exception 4). */
export function pending(store: Store, nowMs: number): Pending | null {
  let value: Pending | null = null;
  try {
    const raw = store.getItem(PENDING_KEY);
    value = raw ? (JSON.parse(raw) as Pending) : null;
  } catch {
    return null; // storage unavailable: nothing stored, no message, sign-in still works
  }
  if (!value || !Number.isInteger(value.showtime_id) || !Array.isArray(value.seat_ids)) return null;
  const at = Date.parse(value.stored_at);
  if (!Number.isFinite(at) || nowMs - at > PENDING_MAX_AGE_MS) {
    try {
      store.removeItem(PENDING_KEY);
      store.removeItem(SELECTION_KEY);
    } catch {
      // nothing to remove
    }
    return null;
  }
  return value;
}

/** A same-site path carried in ?next= (SCR-XCT-04's interrupted request), or null. Never another origin. */
export function nextPath(search: string): string | null {
  const next = new URLSearchParams(search).get("next");
  return next && next.startsWith("/") && !next.startsWith("//") ? next : null;
}

/** Where a successful sign-in goes: the interrupted path, else the seat map of a pending selection, else the listing. */
export function destination(search: string, store: Store, nowMs: number): string {
  const p = pending(store, nowMs);
  return nextPath(search) ?? (p ? `/showtimes/${p.showtime_id}` : "/");
}

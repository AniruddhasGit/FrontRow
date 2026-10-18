// The sign-in screen's rules (SCR-ACC-01, P-ACC-13), with no DOM, no clock and no relative import.
// Run: node --test frontend/src/features/auth/auth.test.mjs

export const PENDING_KEY = "fr.pending_selection";
export const PENDING_MAX_AGE_MS = 30 * 60 * 1000; // P-ACC-13: a stored selection older than 30 minutes is discarded
export const CONTEXT_NOTE = "Your seats are still selected. Sign in to hold them.";

interface Store {
  getItem(key: string): string | null;
  removeItem(key: string): void;
}

export interface Pending {
  showtime_id: number;
  seat_ids: number[];
  stored_at: string;
}

/** The pending selection if it is fresh by the BROWSER's clock (`nowMs`), else null - and a stale one is removed. */
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

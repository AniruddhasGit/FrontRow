// CR-008 T3-T8: the personal account's rules, with no DOM, no clock and no relative import, so node --test runs them.
// Run: node --test frontend/src/features/account/
//
// Every screen here keeps ONE status per flow (a union), never a pile of booleans, and every wait has an exit: a
// request that fails or never answers lands in "error" with a retry (web-app-pitfalls rules 2 and 3).

/** A read: loading, then exactly one of the three ends. "guest" is the 401 - the page offers sign-in instead. */
export type Load<T> = { kind: "loading" } | { kind: "ready"; data: T } | { kind: "guest" } | { kind: "error"; message: string };

/** A write: idle, sending, then done or failed. A second press while sending is ignored by the caller. */
export type Send = { kind: "idle" } | { kind: "sending" } | { kind: "done"; message?: string } | { kind: "failed"; message: string };

export const UNAVAILABLE = "This cannot be loaded right now. Try again shortly.";

/** A response from browse/api's get() or send() turned into a Load. */
export function loaded<T>(r: { ok: true; body: T } | { ok: false; status: number; message: string }): Load<T> {
  if (r.ok) return { kind: "ready", data: r.body };
  if (r.status === 401) return { kind: "guest" };
  return { kind: "error", message: r.message || UNAVAILABLE };
}

// ---- T5: the sidebar ------------------------------------------------------------------------------------------------

export interface Summary { display_name: string | null; email: string; points_balance: number; unread_notifications: number }

/** "Hi, Asha" - the display name, else the email's local part. */
export function greeting(s: Pick<Summary, "display_name" | "email">): string {
  return `Hi, ${s.display_name?.trim() || s.email.split("@")[0]}`;
}

export function points(n: number): string {
  return `${n.toLocaleString("en-US")} ${n === 1 ? "point" : "points"}`;
}

/** The unread badge's accessible words, and its visible text (capped so the badge never widens the header). */
export function unreadName(n: number): string {
  return n === 0 ? "No unread notifications" : `${n} unread ${n === 1 ? "notification" : "notifications"}`;
}
export function unreadBadge(n: number): string | null {
  return n <= 0 ? null : n > 99 ? "99+" : String(n);
}

// ---- T3: rewards at checkout ----------------------------------------------------------------------------------------

export interface Quote { points: number; discount_paise: number; total_paise: number }

/** What the pay request carries. `expected_total_paise` is the total THIS screen shows, so the server refuses to book
 *  anything else (TOTAL_CHANGED) - the hold may have grown from another tab. */
export function payExtras(subtotal: number, quote: Quote | null, usePoints: boolean): { use_points: boolean; expected_total_paise: number } {
  const use = usePoints && !!quote && quote.points > 0;
  return { use_points: use, expected_total_paise: use && quote ? quote.total_paise : subtotal };
}

// ---- T4: bookmarks --------------------------------------------------------------------------------------------------

export const PENDING_BOOKMARK = "fr.pending_bookmark"; // inside the fr.* sign-out sweep

interface Store { getItem(k: string): string | null; setItem(k: string, v: string): void; removeItem(k: string): void }

/** A guest pressed Save: remember the film, so the bookmark is applied once they have signed in. */
export function rememberBookmark(store: Store, movieId: number): void {
  try {
    store.setItem(PENDING_BOOKMARK, String(movieId));
  } catch {
    // no storage: the guest signs in and presses Save again
  }
}

/** The remembered film, read once (removed as it is read), or null. */
export function takeBookmark(store: Store): number | null {
  try {
    const raw = store.getItem(PENDING_BOOKMARK);
    store.removeItem(PENDING_BOOKMARK);
    const id = Number(raw);
    return raw && Number.isInteger(id) && id > 0 ? id : null;
  } catch {
    return null;
  }
}

/** The saved set for one page. "pending" films are between press and answer; a failed toggle reverts and says so. */
export type Saved = { kind: "loading" } | { kind: "guest" } | { kind: "error" } | { kind: "ready"; ids: number[]; pending: number[]; failed: number | null };
export type SavedEvent =
  | { type: "loaded"; ids: number[] } | { type: "guest" } | { type: "error" }
  | { type: "press"; id: number } | { type: "answered"; id: number; saved: boolean } | { type: "refused"; id: number };

export function savedReducer(s: Saved, e: SavedEvent): Saved {
  switch (e.type) {
    case "loaded": return { kind: "ready", ids: e.ids, pending: [], failed: null };
    case "guest": return { kind: "guest" };
    case "error": return { kind: "error" };
  }
  if (s.kind !== "ready") return s;
  if (e.type === "press") return s.pending.includes(e.id) ? s : { ...s, pending: [...s.pending, e.id], failed: null };
  const pending = s.pending.filter((p) => p !== e.id);
  if (e.type === "refused") return { ...s, pending, failed: e.id };
  const ids = e.saved ? [...new Set([...s.ids, e.id])] : s.ids.filter((i) => i !== e.id);
  return { ...s, ids, pending };
}

// ---- T6: profile ----------------------------------------------------------------------------------------------------

export interface ProfileForm { display_name: string; phone: string; preferred_language_id: string; preferred_format_id: string }
export const PROFILE_ERRORS = {
  display_name: "Enter a name of 1 to 60 characters, or leave it empty.",
  phone: "Enter 7 to 15 digits, optionally starting with +.",
};

/** The same bounds the server checks, shown inline before a request is sent. The server's refusal is shown the same way. */
export function profileErrors(f: ProfileForm): Partial<Record<keyof ProfileForm, string>> {
  const out: Partial<Record<keyof ProfileForm, string>> = {};
  if (f.display_name.trim().length > 60) out.display_name = PROFILE_ERRORS.display_name;
  const phone = f.phone.replace(/[\s-]/g, "");
  if (phone && !/^\+?[0-9]{7,15}$/.test(phone)) out.phone = PROFILE_ERRORS.phone;
  return out;
}

/** The PUT body: every field, empty strings as null. */
export function profileBody(f: ProfileForm) {
  const id = (v: string) => (v ? Number(v) : null);
  return { display_name: f.display_name.trim() || null, phone: f.phone.replace(/[\s-]/g, "") || null,
           preferred_language_id: id(f.preferred_language_id), preferred_format_id: id(f.preferred_format_id) };
}

// The hold on the client (P-HLD-01..09, SCR-SEA-01/02, COMPONENTS.md §7). Pure functions plus one fetch wrapper:
// no DOM and no clock. The countdown takes the current instant as an argument and never reads one itself, so a
// device with a wrong clock shows a wrong number and never causes a wrong outcome - the server decides (P-HLD-03).
//
// The server renders every sentence a failure shows; this file composes none of them (SCR-XCT-01). It branches on
// error.code only, never on the message.
import type { SeatMap } from "./model";

export interface HoldSeat {
  seat_id: number;
  label: string;
  category: string;
  price_paise: number;
}
export interface Hold {
  hold_token: string;
  showtime_id: number;
  expires_at: string;
  seats: HoldSeat[];
  total_paise: number;
}

// The client's own copy (P-HLD-09, P-HLD-06, SCR-SEA-02).
export const TIME_LEFT = "TIME LEFT";
export const WARNING_LINE = "Less than a minute left. At 0:00 your seats are released and you will need to choose them again.";
export const ENDED_LINE = "Your hold has ended and your seats have been released. You have not been charged.";
export const ENDED_PAYING_LINE = "Your hold has ended. We are waiting for the answer to your payment. Do not close this page.";
export const GIVE_UP = "Give up these seats";
const WARNING_MS = 60_000;

export interface Countdown {
  text: string; // m:ss, never negative
  remainingMs: number;
  urgent: boolean; // the last 60 seconds: bar and digits switch to --fr-countdown-urgent, the warning line shows
  ended: boolean;
}

/** `now` is required: the countdown is arithmetic on a server-issued instant and an instant the caller supplies. */
export function countdown(expiresAt: string, now: number): Countdown {
  if (typeof now !== "number" || !Number.isFinite(now)) throw new TypeError("countdown needs the current instant");
  const remainingMs = Math.max(0, Date.parse(expiresAt) - now);
  const seconds = Math.ceil(remainingMs / 1000);
  const text = `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
  return { text, remainingMs, urgent: remainingMs > 0 && remainingMs <= WARNING_MS, ended: remainingMs === 0 };
}

/** The one line under the digits, or null. At zero with a confirm in flight the request is never cancelled and
 *  the customer is told to wait for its answer (P-HLD-09 row 3). */
export function countdownLine(c: Countdown, confirmInFlight: boolean): string | null {
  if (c.ended) return confirmInFlight ? ENDED_PAYING_LINE : ENDED_LINE;
  return c.urgent ? WARNING_LINE : null;
}

/** The primary action's label (SCR-SEA-01): a guest, nothing chosen, a first hold, or more seats for a live one. */
export function primaryLabel(signedIn: boolean, adding: number, holding: boolean): string {
  if (!signedIn) return "Sign in to hold these seats";
  if (adding === 0) return holding ? "Continue to payment" : "Choose seats";
  if (!holding) return "Hold these seats";
  return adding === 1 ? "Hold 1 more seat" : `Hold ${adding} more seats`;
}

/** The banner over a closed map: a customer holding seats may still pay for them (P-HLD-06 row 2). `closed` is the
 *  map's own banner (model.ts mapBanner), so the shared first sentence is published once in frontend/src. */
export function closedBanner(closed: string, holding: boolean): string {
  return holding ? `${closed} You can still pay for the seats you are holding.` : closed;
}

export type Failure =
  | { kind: "taken"; labels: string[] } // SEAT_UNAVAILABLE: repaint these seats held_by_other, keep the rest
  | { kind: "ended" } // HOLD_EXPIRED / HOLD_NOT_OWNED: forget the hold
  | { kind: "sign_in" } // AUTH_REQUIRED: the selection is kept
  | { kind: "message" }; // every other refusal: show the server's sentence, change nothing else

export function failureOf(code: string, details: unknown): Failure {
  switch (code) {
    case "SEAT_UNAVAILABLE": {
      const labels = (details as { unavailable_seats?: unknown })?.unavailable_seats;
      return { kind: "taken", labels: Array.isArray(labels) ? labels.filter((l): l is string => typeof l === "string") : [] };
    }
    case "HOLD_EXPIRED":
    case "HOLD_NOT_OWNED":
      return { kind: "ended" };
    case "AUTH_REQUIRED":
      return { kind: "sign_in" };
    default:
      return { kind: "message" };
  }
}

/** A seat lost to another customer's hold is held_by_other, never sold - it is sold only once their booking
 *  commits, and the next poll settles it (P-HLD-07). The map is repainted locally, at once. */
export function markTaken(map: SeatMap, labels: string[]): SeatMap {
  const lost = new Set(labels);
  return { ...map, seats: map.seats.map((s) => (lost.has(`${s.row}${s.num}`) && s.state === "available" ? { ...s, state: "held" } : s)) };
}

/** Every other chosen seat stays chosen: only the named ones leave the selection (P-HLD-07). */
export function withoutLabels(selection: number[], map: SeatMap, labels: string[]): number[] {
  const lost = new Set(map.seats.filter((s) => labels.includes(`${s.row}${s.num}`)).map((s) => s.id));
  return selection.filter((id) => !lost.has(id));
}

/** The seats a press would add: chosen and not already in the hold. */
export function adding(selection: number[], hold: Hold | null): number[] {
  const held = new Set((hold?.seats ?? []).map((s) => s.seat_id));
  return selection.filter((id) => !held.has(id));
}

export type Sent<T> =
  | { ok: true; status: number; body: T | null }
  | { ok: false; status: number; code: string; message: string; details: unknown; requestId: string | null };

/** POST / DELETE against the hold endpoints, with the session cookie. Nothing is sent on unload (P-HLD-09). */
export async function send<T>(method: "POST" | "GET" | "DELETE", path: string, body?: unknown): Promise<Sent<T>> {
  let response: Response;
  try {
    response = await fetch(path, {
      method, credentials: "same-origin",
      headers: body === undefined ? undefined : { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    return { ok: false, status: 0, code: "NETWORK", message: "", details: null, requestId: null };
  }
  const data = response.status === 204 ? null : await response.json().catch(() => null);
  if (response.ok) return { ok: true, status: response.status, body: data as T | null };
  const error = data?.error ?? {};
  return { ok: false, status: response.status, code: error.code ?? "INTERNAL_ERROR", message: error.message ?? "",
           details: error.details ?? null, requestId: error.request_id ?? null };
}

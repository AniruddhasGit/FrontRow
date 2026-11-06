// SCR-PAY-01 · the checkout: its rules and its panel, with no clock and no relative import (P-PAY-09, P-PAY-13/14).
// Run: node --test frontend/src/features/booking/   (Node 24 strips the types itself).
//
// The Idempotency-Key is the CLIENT's (P-PAY-09): minted once per confirm attempt, written to sessionStorage beside the
// hold token it was minted against BEFORE the request goes out, re-sent unchanged on any repeat of that attempt -
// including one whose outcome the client never learned - and replaced only when there is none, when the hold token
// changed, or after a 402. The server renders every sentence a failure shows, except the few this screen owns; the
// banner branches on error.code and never on the message text (FR-ADR-052).

import { createElement as h, type ReactNode } from "react";

export const KEY_STORE = "fr.confirm_idempotency_key";
export const LAST_BOOKING = "fr.last_booking_reference";
export const NAMESPACE = "fr.";
// ASSUMED (SCR-PAY-01): long enough for one polite announcement of the zero state before the route changes.
export const CHECKOUT_EXPIRY_RETURN_DELAY_MS = 5000;
// P-PAY-09: automatic re-sends of an in-flight confirm, at most this many.
export const IN_FLIGHT_RESENDS = 3;

export interface Store {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
  removeItem(key: string): void;
  key(index: number): string | null;
  readonly length: number;
}

function read<T>(store: Store, key: string): T | null {
  try {
    const raw = store.getItem(key);
    return raw ? (JSON.parse(raw) as T) : null;
  } catch {
    return null;
  }
}

function write(store: Store, key: string, value: unknown): void {
  try {
    store.setItem(key, JSON.stringify(value));
  } catch {
    // storage refused (a private window): the attempt still runs, it just cannot survive a reload
  }
}

function remove(store: Store, key: string): void {
  try {
    store.removeItem(key);
  } catch {
    // nothing to clear
  }
}

/** The browser's CSPRNG, canonical 36-character form: 122 random bits from [0-9a-f-] only. */
export function mintKey(): string {
  return crypto.randomUUID();
}

/** The key for a press: the stored one when it was minted against this hold token, else a fresh one, stored first. */
export function keyFor(store: Store, holdToken: string, mint: () => string = mintKey): string {
  const stored = read<{ key?: unknown; hold_token?: unknown }>(store, KEY_STORE);
  if (stored && stored.hold_token === holdToken && typeof stored.key === "string") return stored.key;
  const key = mint();
  write(store, KEY_STORE, { key, hold_token: holdToken });
  return key;
}

/** The attempt is over: a 201 (it booked) or a 402 (it committed nothing). Every other ending keeps the key. */
export function endAttempt(store: Store): void {
  remove(store, KEY_STORE);
}

/** Sign-out sweeps the whole fr.* namespace, never a named list (P-ACC-13, SCR-PAY-01). */
export function signOutSweep(store: Store): void {
  const doomed: string[] = [];
  try {
    for (let i = 0; i < store.length; i++) {
      const k = store.key(i);
      if (k !== null && k.startsWith(NAMESPACE)) doomed.push(k);
    }
  } catch {
    return;
  }
  for (const k of doomed) remove(store, k);
}

export function rememberBooking(store: Store, reference: string, showtimeId: number): void {
  write(store, LAST_BOOKING, { booking_reference: reference, showtime_id: showtimeId });
}

/** Called the moment ANY hold response arrives, for any showtime (SCR-PAY-01). */
export function forgetBooking(store: Store): void {
  remove(store, LAST_BOOKING);
}

export interface HeldSeat {
  seat_id: number;
  label: string;
  category: string;
  price_paise?: number | null;
}
export interface HeldHold {
  hold_token: string;
  showtime_id: number;
  expires_at: string;
  seats: HeldSeat[];
}

export type Arrival = { kind: "confirmed"; reference: string } | { kind: "seatmap" } | { kind: "checkout"; hold: HeldHold };

/** Where this route goes on arrival, decided from stored values alone and no request (SCR-PAY-01). */
export function arrival(store: Store, showtimeId: number, holdKey: string): Arrival {
  const last = read<{ booking_reference?: unknown; showtime_id?: unknown }>(store, LAST_BOOKING);
  if (last && last.showtime_id === showtimeId && typeof last.booking_reference === "string") {
    return { kind: "confirmed", reference: last.booking_reference };
  }
  const hold = read<HeldHold>(store, holdKey);
  if (!hold || hold.showtime_id !== showtimeId || typeof hold.hold_token !== "string" || !Array.isArray(hold.seats) || hold.seats.length === 0) {
    return { kind: "seatmap" };
  }
  return { kind: "checkout", hold };
}

/** The sum of the snapshot prices, or null when any is missing: a partial total is a wrong number. */
export function checkoutTotal(seats: HeldSeat[]): number | null {
  let sum = 0;
  for (const s of seats) {
    if (typeof s.price_paise !== "number" || !Number.isInteger(s.price_paise)) return null;
    sum += s.price_paise;
  }
  return seats.length > 0 ? sum : null;
}

/** "Pay 12 dollars 99 cents", "Pay 1 dollar 1 cent" - the pay action's accessible name (SCR-PAY-01, SRC-006).
 *  `ratio` is cents per dollar. */
export function payName(totalPaise: number, ratio: number): string {
  const whole = Math.floor(totalPaise / ratio);
  const cents = totalPaise % ratio;
  return `Pay ${whole.toLocaleString("en-US")} ${whole === 1 ? "dollar" : "dollars"} ${cents} ${cents === 1 ? "cent" : "cents"}`;
}

export const BUSY = "Confirming…";
export const EXPIRED_LABEL = "Hold expired";
export const BACK = "Back to seats";

export function payLabel(formatted: string | null, state: { inFlight: boolean; expired: boolean }): string {
  if (state.inFlight) return BUSY;
  if (state.expired) return EXPIRED_LABEL;
  return formatted === null ? "Pay" : `Pay ${formatted}`;
}

// The sentences this screen owns (P-PAY-01, P-PAY-09). The four hold-related codes and RATE_LIMITED are the server's.
const OWN: Record<string, string> = {
  AUTH_REQUIRED: "Sign in to complete this booking.",
  IDEMPOTENCY_KEY_REUSED: "This checkout is out of date. Return to the seat map and choose your seats again.",
  REQUEST_INVALID: "This request could not be processed. Return to the seat map and choose your seats again.",
  PAYMENT_FAILED:
    "The payment did not go through and you have not been charged. You can try again while the countdown is still running. " +
    "If it has reached zero your hold has ended and you will need to choose your seats again.",
  IDEMPOTENCY_IN_FLIGHT: "This booking is still being processed.",
};

/** The banner for a failure, chosen by code. `null` means no banner (a dropped connection publishes no sentence). */
export function bannerText(code: string, message: string, requestId: string | null): string | null {
  if (code === "NETWORK") return null;
  if (code === "INTERNAL_ERROR") {
    return `Something went wrong and your booking was not completed. No payment was taken. If you need help, quote ${requestId ?? ""}.`;
  }
  return OWN[code] ?? message;
}

export interface Confirmed {
  booking_id: number;
  booking_reference: string;
  showtime_id: number;
  movie_title: string;
  screen_name: string;
  starts_at: string;
  seats: { seat_id: number; seat_label: string; seat_category_name: string; price_paise: number }[];
  total_paise: number;
  currency_code: string;
  payment_status: string;
  created_at: string;
}

export type Outcome =
  | { ok: true; body: Confirmed }
  | { ok: false; status: number; code: string; message: string; requestId: string | null; details: unknown };

type Fetch = (url: string, init: { method: string; credentials: "same-origin"; headers: Record<string, string>; body: string }) => Promise<{
  status: number; ok: boolean; headers: { get(name: string): string | null }; json(): Promise<unknown>;
}>;

async function post(fetchFn: Fetch, key: string, hold: HeldHold): Promise<Outcome & { retryAfter?: number }> {
  let r;
  try {
    r = await fetchFn("/api/bookings", {
      method: "POST", credentials: "same-origin",
      headers: { "Content-Type": "application/json", "Idempotency-Key": key },
      body: JSON.stringify({ hold_token: hold.hold_token, showtime_id: hold.showtime_id }),
    });
  } catch {
    return { ok: false, status: 0, code: "NETWORK", message: "", requestId: null, details: null };
  }
  const data = (await r.json().catch(() => null)) as { error?: Record<string, unknown> } | null;
  if (r.status === 201 && data) return { ok: true, body: data as unknown as Confirmed };
  const e = data?.error ?? {};
  const retry = Number(r.headers.get("Retry-After"));
  return { ok: false, status: r.status, code: String(e.code ?? "INTERNAL_ERROR"), message: String(e.message ?? ""),
           requestId: (e.request_id as string | undefined) ?? null, details: e.details ?? null,
           retryAfter: Number.isFinite(retry) && retry > 0 ? retry : undefined };
}

/** One press of the pay action: the key stored first, then one POST; on 409 IDEMPOTENCY_IN_FLIGHT the identical request
 *  again after Retry-After seconds, at most three times. `wait` is the screen's timer, so tests own time. A 201 stores the
 *  reference (before the caller navigates) and ends the attempt; a 402 ends it; every other outcome keeps the key. */
export async function pay(deps: { fetch: Fetch; store: Store; wait: (ms: number) => Promise<void>; hold: HeldHold;
                                  onInFlight?: () => void; mint?: () => string }): Promise<Outcome> {
  const key = keyFor(deps.store, deps.hold.hold_token, deps.mint);
  let outcome = await post(deps.fetch, key, deps.hold);
  for (let resend = 0; !outcome.ok && outcome.code === "IDEMPOTENCY_IN_FLIGHT" && resend < IN_FLIGHT_RESENDS; resend++) {
    deps.onInFlight?.();
    await deps.wait((outcome.retryAfter ?? 1) * 1000);
    outcome = await post(deps.fetch, key, deps.hold);
  }
  if (outcome.ok) {
    rememberBooking(deps.store, outcome.body.booking_reference, outcome.body.showtime_id);
    endAttempt(deps.store);
  } else if (outcome.code === "PAYMENT_FAILED") {
    endAttempt(deps.store);
  }
  return outcome;
}

// ---- the panel (COMPONENTS.md §8). Written with createElement rather than JSX so node --test can render it to markup.
// It reads no clock: the countdown arrives as an element the screen built from the instant it holds.


export const NOTICE = "No real payment is taken. This is a demonstration system. Nothing is charged and no card details are collected.";
export const HEADING = "Confirm your booking";
export const TOTAL_LABEL = "TOTAL";

export interface PanelProps {
  title: string;
  hall: string;
  startsLabel: string; // the wall-clock part as the server gave it (S7.19); this module converts nothing
  seats: HeldSeat[];
  money: (paise: number) => string; // rendering only; the integer is the value
  ratio: number;
  countdown: ReactNode;
  live: boolean;
  expired: boolean;
  inFlight: boolean;
  onPay: () => void;
  onBack: () => void;
}

export function CheckoutPanel(p: PanelProps) {
  const total = checkoutTotal(p.seats);
  const formatted = total === null ? null : p.money(total);
  const disabled = !p.live || p.expired || p.inFlight || total === null;
  return h("section", { className: "fr-checkout", "aria-labelledby": "fr-checkout-heading" },
    h("div", { className: "fr-notice", key: "notice" }, NOTICE),
    h("h1", { id: "fr-checkout-heading", key: "heading", tabIndex: -1 }, HEADING),
    h("p", { className: "fr-checkout-showtime fr-mono", key: "showtime" }, `${p.title} · ${p.hall} · ${p.startsLabel}`),
    ...p.seats.map((s) => h("p", { className: "fr-checkout-line", key: `seat-${s.seat_id}` },
      h("span", { className: "fr-mono" }, s.label),
      h("span", { className: "fr-checkout-cat" }, s.category),
      typeof s.price_paise === "number"
        ? h("span", { className: "fr-mono" }, p.money(s.price_paise))
        : h("span", { className: "fr-checkout-pending", "aria-hidden": "true" }))),
    h("hr", { className: "fr-perforation", key: "perforation" }),
    total === null ? null : h("p", { className: "fr-checkout-total", key: "total" },
      h("span", { className: "fr-total-label" }, TOTAL_LABEL), h("span", { className: "fr-total fr-mono" }, formatted)),
    h("div", { className: "fr-checkout-countdown", key: "countdown" }, p.countdown),
    h("button", { type: "button", className: "fr-action", key: "pay", disabled, "aria-busy": p.inFlight || undefined,
                  "aria-label": total === null || p.inFlight || p.expired ? undefined : payName(total, p.ratio), onClick: p.onPay },
      payLabel(formatted, p)),
    h("button", { type: "button", className: "fr-action-secondary", key: "back", onClick: p.onBack }, BACK),
  );
}

/** The error banner region: always present and assertive, so a banner that arrives is announced; it holds text and the
 *  request id line only - no control (SCR-PAY-01). It precedes the panel in the DOM and in focus order. */
export function CheckoutBanner({ text }: { text: string | null }) {
  return h("div", { className: "fr-banner-region", "aria-live": "assertive" },
    text === null ? null : h("p", { className: "fr-banner" }, text));
}

export function CheckoutView(p: PanelProps & { banner: string | null }) {
  return h("div", { className: "fr-checkout-view" }, h(CheckoutBanner, { text: p.banner }), h(CheckoutPanel, p));
}

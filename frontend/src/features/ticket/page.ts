// SCR-TKT-01 · the booking confirmation page at /bookings/{reference} - the one booking page in the product.
// Written with createElement rather than JSX so node --test can render it; no relative import, no clock.
// This page owns every string it shows. The reference is on screen whether or not the email ever arrives.
import { createElement as h } from "react";

export const HEADING = "Your booking is confirmed.";
export const REF_LABEL = "BOOKING REFERENCE";
export const ENTRY = "Show this reference at the entrance. A person will check it.";
export const POLICY = "This booking cannot be changed, cancelled or refunded.";
export const COPY = "Copy reference";
export const COPIED = "Reference copied.";
export const RESEND = "Send the receipt again";
export const IN_FLIGHT = "A receipt is already being sent for this booking.";
export const NOT_FOUND = "No booking with that reference is on your account.";
export const UNAVAILABLE = "This page is unavailable right now. Your booking is not affected.";
export const FACT_LABELS = ["FILM", "HALL", "SHOWTIME", "SEATS", "PAID"] as const;

export function failed(requestId: string | null): string {
  return `Something went wrong. Your booking is not affected. If you need help, quote ${requestId ?? ""}.`;
}

/** The resend's 202 (EP-TKT-02). [JUDGMENT CALL] queued=false is both "first receipt not attempted yet" and "a send is in
 *  flight": the body does not tell them apart, so the in-flight line is shown for both (PRD gap, SCR-TKT-01 states). */
export function resendLine(queued: boolean, email: string): string {
  return queued ? `A receipt was requested. It will arrive at ${email}.` : IN_FLIGHT;
}

export function receiptLine(email: string): string {
  return `A receipt is on its way to ${email}.`;
}

/** The reference spelled for a screen reader: "F R, A C D E, F H J D". */
export function spoken(reference: string): string {
  return reference.split("-").map((part) => part.split("").join(" ")).join(", ");
}

export interface Booking {
  reference: string;
  movie_title: string;
  hall_name: string;
  showtime_starts_at: string;
  seats: { seat_label: string }[];
  total_paise: number;
}

export function ConfirmationPage(p: {
  booking: Booking | null; // null while loading: the frame, the heading and inset blocks, never a placeholder reference
  startsLabel: string; money: (paise: number) => string;
  receiptTo: string | null; // set only on the first render after a confirm (P-TKT-03); null on every later visit
  copied: boolean; onCopy: () => void;
  resending?: boolean; resendNote?: string | null; onResend?: () => void;
}) {
  const b = p.booking;
  // Seats in the order the server returned them; this page never re-sorts.
  const facts: [string, string][] = b ? [["FILM", b.movie_title], ["HALL", b.hall_name], ["SHOWTIME", p.startsLabel],
    ["SEATS", b.seats.map((s) => s.seat_label).join(", ")], ["PAID", p.money(b.total_paise)]] : FACT_LABELS.map((l) => [l, ""]);
  return h("section", { className: "fr-ticket", "aria-busy": b ? undefined : true },
    h("h1", { tabIndex: -1, key: "h" }, HEADING),
    h("div", { className: "fr-ref-block", key: "ref" },
      h("p", { className: "fr-ref-label" }, REF_LABEL),
      h("p", { className: "fr-ref", "aria-label": b ? spoken(b.reference) : undefined }, b ? b.reference : ""),
      b ? h("button", { type: "button", className: "fr-link-action", onClick: p.onCopy }, COPY) : null,
      h("p", { className: "fr-ref-copied", "aria-live": "polite" }, p.copied ? COPIED : "")),
    !b || p.receiptTo === null ? null : h("p", { className: "fr-ticket-receipt", key: "receipt" }, receiptLine(p.receiptTo)),
    b ? h("p", { className: "fr-ticket-entry", key: "entry" }, ENTRY) : null,
    b ? h("p", { className: "fr-ticket-policy", key: "policy" }, POLICY) : null,
    h("dl", { className: b ? "fr-ticket-facts" : "fr-ticket-facts fr-ticket-wait", key: "facts" },
      ...facts.map(([label, value]) => h("div", { key: label }, h("dt", null, b ? label : ""), h("dd", { className: "fr-mono" }, value)))),
    b ? h("button", { type: "button", className: "fr-link-action", key: "resend", disabled: !!p.resending, onClick: p.onResend }, RESEND) : null,
    b ? h("p", { className: "fr-ticket-resent", key: "resent", "aria-live": "polite" }, p.resendNote ?? "") : null,
  );
}

/** CR-001 B.2: the still rendered from the middle of this booking's hall (/art/hall_<n>_view.jpg, n from the hall's
 *  name, e.g. "SCREEN 6"), or null when the name carries no number. */
export function hallViewSrc(hallName: string): string | null {
  const n = /(\d+)/.exec(hallName)?.[1];
  return n ? `/art/hall_${Number(n)}_view.jpg` : null;
}

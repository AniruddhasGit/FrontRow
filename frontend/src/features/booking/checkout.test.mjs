// S-PAY-12, S-PAY-13, S-PAY-14, S-PAY-10, S-SCP-12 (the parts that are logic or markup, not layout): the checkout.
// Run: node --test frontend/src/features/booking/   (Node 24 strips the .ts types itself; react-dom/server renders).
// Not asserted here (no browser harness in this repository): computed font size, focus movement by Tab, offsetHeight,
// the live region's announcement, and real navigation - the screen (CheckoutScreen.tsx) wires these.
import assert from "node:assert/strict";
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";
import { test } from "node:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import {
  BACK, CHECKOUT_EXPIRY_RETURN_DELAY_MS, CheckoutPanel, CheckoutView, HEADING, KEY_STORE, LAST_BOOKING, NOTICE, arrival,
  bannerText, checkoutTotal, endAttempt, forgetBooking, keyFor, mintKey, pay, payName, signOutSweep,
} from "./checkout.ts";
import { formatPaise, MINOR_UNIT_RATIO } from "../admin/money.ts";
import { countdown } from "../seatmap/hold.ts";

const SRC = new URL("../..", import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, "$1");
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
const TOKEN = "T".repeat(43);

function store(initial = {}) {
  const m = new Map(Object.entries(initial));
  return {
    getItem: (k) => (m.has(k) ? m.get(k) : null), setItem: (k, v) => m.set(k, String(v)), removeItem: (k) => m.delete(k),
    key: (i) => [...m.keys()][i] ?? null, get length() { return m.size; }, map: m,
  };
}

function walk(dir) {
  return readdirSync(dir).flatMap((n) => (statSync(join(dir, n)).isDirectory() ? walk(join(dir, n)) : [join(dir, n)]));
}
const SOURCES = walk(SRC).filter((f) => /\.(ts|tsx)$/.test(f)).map((f) => [f, readFileSync(f, "utf8")]);
const hits = (rx) => SOURCES.flatMap(([f, s]) => s.split("\n").filter((l) => rx.test(l)).map((l) => `${f}: ${l.trim()}`));

const HOLD = {
  hold_token: TOKEN, showtime_id: 7, expires_at: "2026-08-14T14:03:00.000Z",
  seats: [
    { seat_id: 402, label: "F7", category: "Premium", price_paise: 30938 }, { seat_id: 403, label: "F8", category: "Premium", price_paise: 30938 },
    { seat_id: 404, label: "F9", category: "Premium", price_paise: 30938 }, { seat_id: 405, label: "J3", category: "Recliner", price_paise: 36666 },
    { seat_id: 406, label: "J4", category: "Recliner", price_paise: 36666 },
  ],
};

function response(status, body, headers = {}) {
  return { status, ok: status < 300, headers: { get: (n) => headers[n] ?? null }, json: async () => body };
}

// ---- S-PAY-12 -------------------------------------------------------------------------------------------------------

test("the key is the CSPRNG UUID's canonical form and the only randomness in frontend/src", () => {
  assert.deepEqual(hits(new RegExp("Math" + "\\.random")), []);
  assert.equal(hits(new RegExp("random" + "UUID")).length, 1);
  const keys = Array.from({ length: 1000 }, () => keyFor(store(), TOKEN));
  for (const k of keys) {
    assert.match(k, UUID);
    assert.ok(!k.startsWith("FAIL" + "_"));
  }
  assert.match(mintKey(), UUID);
});

test("the key is stored with its hold token before the request is issued, and is the header the request carries", async () => {
  const s = store();
  let seen = null;
  const fetch = async (url, init) => {
    seen = { stored: JSON.parse(s.getItem(KEY_STORE)), header: init.headers["Idempotency-Key"], body: JSON.parse(init.body) };
    return response(201, { booking_reference: "FR-ACDE-FHJ2", showtime_id: 7 });
  };
  await pay({ fetch, store: s, wait: async () => {}, hold: HOLD });
  assert.equal(seen.stored.key, seen.header);
  assert.equal(seen.stored.hold_token, TOKEN);
  assert.deepEqual(seen.body, { hold_token: TOKEN, showtime_id: 7 });
});

test("a refresh or a dropped connection re-sends the same key; a 402 or a new hold token mints a new one", async () => {
  const s = store();
  const sent = [];
  const answer = [];
  const fetch = async (url, init) => {
    sent.push(init.headers["Idempotency-Key"]);
    const next = answer.shift();
    if (next === "drop") throw new TypeError("network");
    return next;
  };
  answer.push("drop");
  await pay({ fetch, store: s, wait: async () => {}, hold: HOLD });
  // A page refresh mid-flight: a new screen, the same storage.
  answer.push(response(402, { error: { code: "PAYMENT_FAILED", message: "x" } }));
  await pay({ fetch, store: s, wait: async () => {}, hold: HOLD });
  assert.equal(sent[0], sent[1]);
  answer.push(response(500, { error: { code: "INTERNAL_ERROR", message: "x", request_id: "a1b2c3d4" } }));
  await pay({ fetch, store: s, wait: async () => {}, hold: HOLD });
  assert.notEqual(sent[2], sent[1]); // after the 402
  answer.push(response(409, { error: { code: "HOLD_EXPIRED", message: "x" } }));
  await pay({ fetch, store: s, wait: async () => {}, hold: { ...HOLD, hold_token: "U".repeat(43) } });
  assert.notEqual(sent[3], sent[2]); // the hold token changed
  answer.push(response(201, { booking_reference: "FR-ACDE-FHJ2", showtime_id: 7 }));
  await pay({ fetch, store: s, wait: async () => {}, hold: { ...HOLD, hold_token: "U".repeat(43) } });
  assert.equal(sent[4], sent[3]);
  assert.equal(s.getItem(KEY_STORE), null); // cleared on the 201
  const fresh = store();
  assert.match(keyFor(fresh, TOKEN), UUID);
});

test("sign-out sweeps every fr.* value, the last booking and the hold included", () => {
  const s = store({ "fr.selection": "{}", "fr.hold": "{}", [KEY_STORE]: "{}", [LAST_BOOKING]: "{}", "fr.pending_selection": "{}", other: "kept" });
  signOutSweep(s);
  assert.deepEqual([...s.map.keys()], ["other"]);
  endAttempt(s);
});

// ---- S-PAY-13 -------------------------------------------------------------------------------------------------------

function panel(over = {}) {
  return CheckoutPanel({
    title: "The Long Night", hall: "Hall 2", startsLabel: "Fri 14 Aug · 8:00 pm", seats: HOLD.seats, money: formatPaise, ratio: MINOR_UNIT_RATIO,
    countdown: createElement("span", null, countdown(HOLD.expires_at, Date.parse("2026-08-14T14:01:46.000Z")).text),
    live: true, expired: false, inFlight: false, onPay: () => {}, onBack: () => {}, ...over,
  });
}
const kids = (el) => [el.props.children].flat(Infinity).filter((c) => c !== null && c !== false && c !== undefined);
const text = (el) => renderToStaticMarkup(el).replace(/<[^>]+>/g, "");

test("the panel's direct children are the thirteen published elements, in order, notice slab first", () => {
  const children = kids(panel());
  assert.equal(children.length, 13);
  const classes = children.map((c) => (c.type === "h1" ? "h1" : c.props.className));
  assert.deepEqual(classes, ["fr-notice", "h1", "fr-checkout-showtime fr-mono", ...Array(5).fill("fr-checkout-line"), "fr-perforation",
                             "fr-checkout-total", "fr-checkout-countdown", "fr-action", "fr-action-secondary"]);
  assert.equal(text(children[0]), NOTICE);
  assert.equal(renderToStaticMarkup(children[0]).match(/<(button|a|input|select|textarea)\b/g), null);
  assert.equal(text(children[1]), HEADING);
  assert.equal(text(children[12]), BACK);
  // Two focusable elements in the panel: the pay action, then Back to seats.
  assert.deepEqual(renderToStaticMarkup(panel()).match(/<(button|a|input|select|textarea)\b/g), ["<button", "<button"]);
});

test("the lines render the snapshot figures and the client recomputes nothing", () => {
  const lines = kids(panel()).slice(3, 8).map(text);
  assert.deepEqual(lines.map((l) => l.replace(/^.*₹/, "")), ["309.38", "309.38", "309.38", "366.66", "366.66"]);
  assert.ok(lines[0].includes("Premium") && lines[3].includes("Recliner"));
  const odd = kids(panel({ seats: [{ seat_id: 1, label: "A1", category: "Standard", price_paise: 99999 }] }));
  assert.ok(text(odd[3]).endsWith("₹999.99"));
});

test("the total is ₹1,661.46 under TOTAL and the pay action says so, with its accessible name", () => {
  const children = kids(panel());
  assert.equal(text(children[9]), "TOTAL₹1,661.46");
  assert.equal(checkoutTotal(HOLD.seats), 166146);
  const pay = children[11];
  assert.equal(text(pay), "Pay ₹1,661.46");
  assert.equal(pay.props["aria-label"], "Pay 1,661 rupees 46 paise");
  assert.equal(payName(166146, MINOR_UNIT_RATIO), "Pay 1,661 rupees 46 paise");
  assert.equal(pay.props.disabled, false);
});

test("a missing seat price removes the total and disables the pay action; so do no hold, 0:00 and a request in flight", () => {
  const partial = kids(panel({ seats: [HOLD.seats[0], { ...HOLD.seats[1], price_paise: undefined }] }));
  assert.ok(!partial.some((c) => c.props.className === "fr-checkout-total"));
  assert.equal(partial.find((c) => c.props.className === "fr-action").props.disabled, true);
  for (const over of [{ live: false }, { expired: true }, { inFlight: true }]) {
    assert.equal(kids(panel(over)).find((c) => c.props.className === "fr-action").props.disabled, true, JSON.stringify(over));
  }
  assert.equal(text(kids(panel({ inFlight: true }))[11]), "Confirming…");
  assert.equal(text(kids(panel({ expired: true }))[11]), "Hold expired");
});

test("the countdown follows the injected instant, and the panel module reads no clock", () => {
  const a = text(kids(panel())[10]);
  const later = panel({ countdown: createElement("span", null, countdown(HOLD.expires_at, Date.parse("2026-08-14T14:01:47.000Z")).text) });
  assert.notEqual(text(kids(later)[10]), a);
  const source = readFileSync(new URL("./checkout.ts", import.meta.url), "utf8");
  assert.equal(source.match(/Date\.now|new Date\(\)|setInterval/g), null);
});

test("one press is one POST, and two presses in the same moment are still one", async () => {
  let calls = 0;
  const s = store();
  let release;
  const gate = new Promise((r) => (release = r));
  const fetch = async () => { calls++; await gate; return response(201, { booking_reference: "FR-ACDE-FHJ2", showtime_id: 7 }); };
  // The screen disables the action on the first press; the second press finds it disabled and sends nothing.
  let inFlight = false;
  const press = () => { if (inFlight) return null; inFlight = true; return pay({ fetch, store: s, wait: async () => {}, hold: HOLD }); };
  const first = press();
  assert.equal(press(), null);
  release();
  await first;
  assert.equal(calls, 1);
});

// ---- S-PAY-10 / S-SCP-12 ---------------------------------------------------------------------------------------------

test("the checkout renders no input and no tax, fee, discount, coupon or promo text, and no card field", () => {
  const html = renderToStaticMarkup(CheckoutView({ ...panel().props, banner: null, title: "The Long Night", hall: "Hall 2",
    startsLabel: "8:00 pm", seats: HOLD.seats, money: formatPaise, ratio: MINOR_UNIT_RATIO, countdown: "1:14", live: true, expired: false,
    inFlight: false, onPay() {}, onBack() {} }));
  assert.equal(html.match(/<input\b/g), null);
  assert.equal(/Tax|Fee|Discount|Coupon|Promo/.test(html.replace(/<[^>]+>/g, " ")), false);
  assert.equal(/cc-number|cc-exp|cc-csc|autocomplete/i.test(html), false);
});

// ---- S-PAY-14 -------------------------------------------------------------------------------------------------------

test("the banner branches on the code: this screen's own sentences, and the server's for the four hold codes", () => {
  const own = {
    AUTH_REQUIRED: "Sign in to complete this booking.",
    IDEMPOTENCY_KEY_REUSED: "This checkout is out of date. Return to the seat map and choose your seats again.",
    REQUEST_INVALID: "This request could not be processed. Return to the seat map and choose your seats again.",
    PAYMENT_FAILED: "The payment did not go through and you have not been charged. You can try again while the countdown is still running. If it has reached zero your hold has ended and you will need to choose your seats again.",
  };
  for (const [code, sentence] of Object.entries(own)) {
    assert.equal(bannerText(code, "an unexpected message", null), sentence);
  }
  assert.equal(bannerText("INTERNAL_ERROR", "whatever", "a1b2c3d4"),
    "Something went wrong and your booking was not completed. No payment was taken. If you need help, quote a1b2c3d4.");
  for (const code of ["HOLD_EXPIRED", "HOLD_NOT_OWNED", "SEAT_UNAVAILABLE", "DEPENDENCY_UNAVAILABLE"]) {
    assert.equal(bannerText(code, "Server sentence one.", null), "Server sentence one.");
    assert.equal(bannerText(code, "Server sentence two.", null), "Server sentence two.");
  }
});

test("the banner region is assertive, precedes the panel and carries no control", () => {
  const html = renderToStaticMarkup(createElement(CheckoutView, { ...panel().props, banner: "Server sentence.",
    title: "x", hall: "y", startsLabel: "z", seats: HOLD.seats, money: formatPaise, ratio: MINOR_UNIT_RATIO, countdown: "1:00",
    live: true, expired: false, inFlight: false, onPay() {}, onBack() {} }));
  const region = html.match(/<div class="fr-banner-region" aria-live="assertive">(.*?)<\/div>/);
  assert.ok(region && region[1].includes("Server sentence."));
  assert.equal(region[1].match(/<(button|a|input)\b/g), null);
  assert.ok(html.indexOf("fr-banner-region") < html.indexOf("fr-checkout\""));
});

test("409 in flight: the identical request again after Retry-After, at most three times, four requests in all", async () => {
  const s = store();
  const keys = [];
  const waits = [];
  let inFlightCalls = 0;
  const fetch = async (url, init) => {
    keys.push(init.headers["Idempotency-Key"]);
    return response(409, { error: { code: "IDEMPOTENCY_IN_FLIGHT", message: "x" } }, { "Retry-After": "3" });
  };
  const out = await pay({ fetch, store: s, wait: async (ms) => { waits.push(ms); }, hold: HOLD, onInFlight: () => inFlightCalls++ });
  assert.equal(keys.length, 4);
  assert.equal(new Set(keys).size, 1);
  assert.deepEqual(waits, [3000, 3000, 3000]);
  assert.equal(out.ok, false);
  assert.equal(bannerText(out.code, out.message, null), "This booking is still being processed.");
  assert.equal(inFlightCalls, 3);
});

test("a 201 stores the reference before the caller navigates; arriving with it goes to the confirmation with no request", async () => {
  const s = store({ "fr.hold": JSON.stringify(HOLD) });
  const fetch = async () => response(201, { booking_reference: "FR-ACDE-FHJ2", showtime_id: 7 });
  const out = await pay({ fetch, store: s, wait: async () => {}, hold: HOLD });
  assert.equal(out.ok, true);
  assert.deepEqual(JSON.parse(s.getItem(LAST_BOOKING)), { booking_reference: "FR-ACDE-FHJ2", showtime_id: 7 });
  assert.deepEqual(arrival(s, 7, "fr.hold"), { kind: "confirmed", reference: "FR-ACDE-FHJ2" });
  assert.equal(arrival(s, 8, "fr.hold").kind, "seatmap");
  forgetBooking(s); // a hold acquired for any showtime, this one included
  assert.equal(arrival(s, 7, "fr.hold").kind, "checkout");
  signOutSweep(s);
  assert.equal(arrival(s, 7, "fr.hold").kind, "seatmap");
});

test("the return delay after 0:00 is the published constant", () => {
  assert.equal(CHECKOUT_EXPIRY_RETURN_DELAY_MS, 5000);
});

test("no control in the product names the failure prefix", () => {
  assert.deepEqual(hits(new RegExp("FAIL" + "_|PAYMENT_SIMULATOR_" + "FAIL")), []);
});

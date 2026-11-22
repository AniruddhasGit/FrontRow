// CR-008 T3-T8: the account rules (account.ts) and the first render of the new screens.
// Run: node --test frontend/src/features/account/
import assert from "node:assert/strict";
import { test } from "node:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import {
  PENDING_BOOKMARK, greeting, loaded, payExtras, points, profileBody, profileErrors, rememberBookmark, savedReducer, takeBookmark,
  unreadBadge, unreadName,
} from "./account.ts";
import { CheckoutPanel } from "../booking/checkout.ts";
import { all, atUrl, load, name, parse, render, role, text } from "../../test/render.mjs";

function store(initial = {}) {
  const m = new Map(Object.entries(initial));
  return { getItem: (k) => (m.has(k) ? m.get(k) : null), setItem: (k, v) => m.set(k, String(v)), removeItem: (k) => m.delete(k), map: m };
}

test("a read lands in exactly one state, and a 401 is the guest state, not an error", () => {
  assert.deepEqual(loaded({ ok: true, body: 1 }), { kind: "ready", data: 1 });
  assert.deepEqual(loaded({ ok: false, status: 401, message: "x" }), { kind: "guest" });
  assert.equal(loaded({ ok: false, status: 0, message: "" }).kind, "error"); // never answered / network: error with a retry
});

test("the greeting, points and unread wording", () => {
  assert.equal(greeting({ display_name: "Asha", email: "a@example.invalid" }), "Hi, Asha");
  assert.equal(greeting({ display_name: "  ", email: "asha.k@example.invalid" }), "Hi, asha.k");
  assert.equal(points(1), "1 point");
  assert.equal(points(12500), "12,500 points");
  assert.equal(unreadName(0), "No unread notifications");
  assert.equal(unreadName(2), "2 unread notifications");
  assert.deepEqual([unreadBadge(0), unreadBadge(7), unreadBadge(120)], [null, "7", "99+"]);
});

test("pay carries the total the screen shows: the discounted one only when points are chosen and offered", () => {
  const q = { points: 15469, discount_paise: 15469, total_paise: 15470 };
  assert.deepEqual(payExtras(30939, q, true), { use_points: true, expected_total_paise: 15470 });
  assert.deepEqual(payExtras(30939, q, false), { use_points: false, expected_total_paise: 30939 });
  assert.deepEqual(payExtras(30939, null, true), { use_points: false, expected_total_paise: 30939 }); // no offer read
  assert.deepEqual(payExtras(30939, { ...q, points: 0 }, true), { use_points: false, expected_total_paise: 30939 });
});

test("a guest's Save is remembered once and read once", () => {
  const s = store();
  rememberBookmark(s, 42);
  assert.equal(s.map.get(PENDING_BOOKMARK), "42");
  assert.ok(PENDING_BOOKMARK.startsWith("fr."), "inside the fr.* sign-out sweep");
  assert.equal(takeBookmark(s), 42);
  assert.equal(takeBookmark(s), null);
  assert.equal(takeBookmark(store({ [PENDING_BOOKMARK]: "nope" })), null);
});

test("the saved-set reducer: press, answer, refusal reverts; nothing happens before it has loaded", () => {
  let s = { kind: "loading" };
  assert.deepEqual(savedReducer(s, { type: "press", id: 1 }), s);
  s = savedReducer(s, { type: "loaded", ids: [3] });
  s = savedReducer(s, { type: "press", id: 1 });
  assert.deepEqual(s, { kind: "ready", ids: [3], pending: [1], failed: null });
  assert.deepEqual(savedReducer(s, { type: "press", id: 1 }), s, "a double click while pending is one press");
  const saved = savedReducer(s, { type: "answered", id: 1, saved: true });
  assert.deepEqual(saved, { kind: "ready", ids: [3, 1], pending: [], failed: null });
  const refused = savedReducer(s, { type: "refused", id: 1 });
  assert.deepEqual(refused, { kind: "ready", ids: [3], pending: [], failed: 1 });
  assert.deepEqual(savedReducer(saved, { type: "answered", id: 3, saved: false }).ids, [1]);
  assert.deepEqual(savedReducer(s, { type: "guest" }), { kind: "guest" });
});

test("profile validation mirrors the server's bounds and the body nulls empty fields", () => {
  const ok = { display_name: "Asha", phone: "+91 98765-43210", preferred_language_id: "2", preferred_format_id: "" };
  assert.deepEqual(profileErrors(ok), {});
  assert.deepEqual(Object.keys(profileErrors({ ...ok, display_name: "x".repeat(61), phone: "12ab" })).sort(), ["display_name", "phone"]);
  assert.deepEqual(profileBody(ok), { display_name: "Asha", phone: "+919876543210", preferred_language_id: 2, preferred_format_id: null });
  assert.deepEqual(profileBody({ display_name: " ", phone: "", preferred_language_id: "", preferred_format_id: "" }),
    { display_name: null, phone: null, preferred_language_id: null, preferred_format_id: null });
});

test("the checkout panel shows the points discount and charges the smaller total", () => {
  const seats = [{ seat_id: 1, label: "C1", category: "Standard", price_paise: 27500 }];
  const money = (p) => `$${(p / 100).toFixed(2)}`;
  const doc = parse(renderToStaticMarkup(createElement(CheckoutPanel, {
    title: "T", hall: "Hall 1", startsLabel: "", seats, money, ratio: 100, countdown: null, live: true, expired: false, inFlight: false,
    onPay() {}, onBack() {}, discountPaise: 1000,
  })));
  assert.ok(text(doc).includes("Points discount"));
  assert.ok(text(doc).includes("−$10.00"));
  const payBtn = all(doc, (e) => e.tag === "button")[0];
  assert.equal(text(payBtn), "Pay $265.00");
  assert.equal(name(payBtn, doc), "Pay 265 dollars 0 cents");
});

atUrl("/help");
const { HelpScreen } = await load("/src/features/account/HelpScreen.tsx");
const { AccountMenu } = await load("/src/features/account/AccountMenu.tsx");
const { RewardsScreen, NotificationsScreen } = await load("/src/features/account/AccountScreens.tsx");

test("Help: an FAQ of native disclosure widgets covering every topic, and a labelled contact form", () => {
  const doc = render(HelpScreen);
  const qs = all(doc, (e) => e.tag === "summary").map(text);
  for (const topic of [/book/i, /countdown/i, /payment/i, /points/i, /bookmark/i, /cancel/i]) assert.ok(qs.some((q) => topic.test(q)), String(topic));
  const fields = all(doc, (e) => ["textbox", "combobox"].includes(role(e))).map((e) => name(e, doc));
  assert.deepEqual(fields, ["Topic", "Your email (not needed when signed in)", "Message"]);
});

test("the account menu: closed, it is one button whose name carries the unread count, and no panel content", () => {
  const signedIn = render(AccountMenu, { summary: { display_name: null, email: "a@example.invalid", points_balance: 10, unread_notifications: 2 },
                                         pathname: "/", onSignOut() {}, leaving: false });
  const buttons = all(signedIn, (e) => role(e) === "button");
  assert.deepEqual(buttons.map((b) => name(b, signedIn)), ["Account menu, 2 unread notifications"]);
  assert.equal(buttons[0].attrs["aria-haspopup"], "dialog");
  assert.equal(all(signedIn, (e) => e.tag === "a").length, 0);
  const guest = render(AccountMenu, { summary: null, pathname: "/", onSignOut() {}, leaving: false });
  assert.deepEqual(all(guest, (e) => role(e) === "button").map((b) => name(b, guest)), ["Account menu"]);
});

test("Rewards and Notifications render their ready, empty and guest states", () => {
  const rules = { earn_points_per_unit: 10, redeem_points_per_unit: 100, redeem_cap_percent: 50 };
  const ready = render(RewardsScreen, { seed: { kind: "ready", data: { points_balance: 6180, rules, history: [
    { kind: "earned", points: 6180, discount_paise: null, created_at: "2026-08-14T14:00:00Z", booking_reference: "FR-ACDE-FHJK" }] } } });
  assert.ok(text(ready).includes("6,180 points"));
  assert.ok(text(ready).includes("+6,180 points"));
  const guest = render(RewardsScreen, { seed: { kind: "guest" } });
  assert.deepEqual(all(guest, (e) => role(e) === "link").map((l) => l.attrs.href), ["/sign-in?next=%2Faccount%2Frewards"]);
  const inbox = render(NotificationsScreen, { seed: { kind: "ready", data: { unread: 1, items: [
    { id: 5, kind: "booking_confirmed", title: "Booking FR-ACDE-FHJK confirmed", body: "T, today.", read: false, created_at: "2026-08-14T14:00:00Z",
      booking_reference: "FR-ACDE-FHJK" }] } } });
  const names = all(inbox, (e) => role(e) === "button").map((b) => name(b, inbox));
  assert.deepEqual(names, ["Mark all as read", 'Mark "Booking FR-ACDE-FHJK confirmed" as read']);
  const failed = render(NotificationsScreen, { seed: { kind: "error", message: "Down." } });
  assert.deepEqual(all(failed, (e) => role(e) === "button").map((b) => name(b, failed)), ["Try again"]);
});

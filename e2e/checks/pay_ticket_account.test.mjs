// Real-browser checks for the open clauses of S-PAY-13, S-PAY-14, S-TKT-04, S-SCP-15, S-SCP-10, S-ACC-07 (SCR-ACC-02),
// S-XCT-22 (interface), S-XCT-38 (keyboard per route, Tab in and out of the seat map).
// Run: cd e2e && node --test checks/pay_ticket_account.test.mjs   (needs the local stack and Vite on :5173)
// Reads Redis and the containers' logs with `docker exec` / `docker logs`; writes nothing to either.
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { after, before, test } from "node:test";
import { BASE, gridSeats, launch } from "../lib.mjs";

const EMAIL = "e2e-pay-1@example.com";
const PASSWORD = "e2e-check-password-123";
const REF = /^FR-[23456789ACDEFHJKMNPQRTVWXY]{4}-[23456789ACDEFHJKMNPQRTVWXY]{4}$/;
const EV = new URL("../evidence/", import.meta.url);
const shot = (page, name) => page.screenshot({ path: fileURLToPath(new URL(`${name}.png`, EV)), fullPage: true });
const redis = (...a) => execFileSync("docker", ["exec", "frontrow-redis-1", "redis-cli", ...a], { encoding: "utf8" }).trim();
const hex8 = () => Math.floor(Math.random() * 0xffffffff).toString(16).padStart(8, "0");
const err = (status, code, message, extra = {}) => ({
  status, contentType: "application/json", headers: extra.headers ?? {},
  body: JSON.stringify({ error: { code, message, details: extra.details ?? {}, request_id: extra.request_id ?? hex8() } }),
});

let browser, state, sid, starts;
before(async () => {
  browser = await launch();
  const ctx = await browser.newContext();
  const page = await ctx.newPage();
  await page.goto(BASE + "/films");
  const status = await page.evaluate(async ([email, password]) => {
    const h = { "content-type": "application/json" };
    const body = JSON.stringify({ email, password });
    const r = await fetch("/api/auth/login", { method: "POST", headers: h, body });
    if (r.status === 200) return 200;
    return (await fetch("/api/auth/register", { method: "POST", headers: h, body })).status;
  }, [EMAIL, PASSWORD]);
  assert.ok(status === 200 || status === 201, `sign-in for ${EMAIL} returned ${status}`);
  state = await ctx.storageState();
  // One open showtime with room for every booking this file makes.
  [sid, starts] = await page.evaluate(async () => {
    for (const f of (await (await fetch("/api/movies")).json()).movies) {
      for (const s of (await (await fetch(`/api/showtimes?movie_id=${f.id}`)).json()).showtimes ?? []) {
        if (s.sales_closed) continue;
        const m = await (await fetch(`/api/showtimes/${s.id}/seatmap`)).json();
        if ((m.seats ?? []).filter((x) => x.state === "available" && x.is_active !== false).length >= 30) return [s.id, s.starts_at];
      }
    }
    return [null, null];
  });
  assert.ok(sid, "no open showtime with 30 free seats");
  await ctx.close();
});
after(() => browser?.close());

async function customer(opts = {}) {
  const ctx = await browser.newContext({ storageState: state, viewport: { width: 1440, height: 900 }, ...opts });
  return { ctx, page: await ctx.newPage() };
}
async function guest(opts = {}) {
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, ...opts });
  return { ctx, page: await ctx.newPage() };
}

/** Select k free seats on the real map, hold them and continue to the checkout. Returns the stored hold. */
async function toCheckout(page, k = 2) {
  await page.goto(`${BASE}/showtimes/${sid}`);
  const free = page.locator('[role="grid"] .fr-seat[aria-label$=", available"]');
  await free.first().waitFor();
  const labels = await free.evaluateAll((els, k) => els.slice(0, k).map((e) => e.getAttribute("aria-label")), k);
  for (const l of labels) await page.locator(`[role="grid"] [aria-label="${l}"]`).click();
  await page.getByRole("button", { name: /^Hold (these seats|\d+ more seats?)$/ }).click();
  await page.getByRole("button", { name: "Continue to payment" }).click();
  await page.waitForURL(/\/checkout$/);
  await page.locator(".fr-checkout").waitFor();
  return JSON.parse(await page.evaluate(() => sessionStorage.getItem("fr.hold")));
}
const release = (page, token) => page.evaluate((t) => fetch(`/api/holds/${t}`, { method: "DELETE" }), token).catch(() => null);

/** A hold that exists only in this tab's storage: enough for the checkout route, which decides from storage alone. */
async function seedHold(page, expiresAt, seats = [{ seat_id: 1, label: "A1", category: "Standard", price_paise: 1299 }]) {
  await page.goto(BASE + "/films");
  await page.evaluate(([h]) => sessionStorage.setItem("fr.hold", JSON.stringify(h)),
    [{ hold_token: "e2e-local-only-token", showtime_id: sid, expires_at: new Date(expiresAt).toISOString(), seats,
       total_paise: seats.reduce((a, s) => a + s.price_paise, 0) }]);
}
// Records every setTimeout the page registers, with the (possibly injected) instant it was registered at.
const TIMERS = `(() => { const st = window.setTimeout; window.__timers = [];
  window.setTimeout = function (fn, ms, ...a) { window.__timers.push({ ms, at: Date.now() }); return st.call(this, fn, ms, ...a); }; })()`;

let booked = null; // { reference, page, ctx } from the real confirm in S-PAY-13 (offsetHeight)

// ---------------------------------------------------------------- S-PAY-13
test("S-PAY-13: the notice slab is first, holds no control, and its computed font size is not below --fr-text-md", async () => {
  const { ctx, page } = await customer();
  const hold = await toCheckout(page, 2);
  const r = await page.evaluate(() => {
    const panel = document.querySelector(".fr-checkout");
    const n = panel.firstElementChild;
    const probe = document.createElement("div");
    probe.style.fontSize = "var(--fr-text-md)";
    document.body.append(probe);
    const md = getComputedStyle(probe).fontSize;
    probe.remove();
    return { cls: n.className, text: n.textContent, fs: getComputedStyle(n).fontSize, md,
             controls: n.querySelectorAll("a,button,input,select,textarea,[tabindex]").length,
             second: panel.children[1].tagName + ":" + panel.children[1].textContent };
  });
  assert.equal(r.cls, "fr-notice");
  assert.equal(r.text, "No real payment is taken. This is a demonstration system. Nothing is charged and no card details are collected.");
  assert.equal(r.controls, 0);
  assert.equal(r.second, "H1:Confirm your booking");
  assert.ok(parseFloat(r.fs) >= parseFloat(r.md), `notice ${r.fs} < --fr-text-md ${r.md}`);
  await shot(page, "pay_checkout_panel");
  await release(page, hold.hold_token);
  await ctx.close();
});

test("S-PAY-13: Tab from the top of the panel reaches the pay action, then 'Back to seats', and then leaves the panel", async () => {
  const { ctx, page } = await customer();
  const hold = await toCheckout(page, 2);
  await page.locator("#fr-checkout-heading").focus();
  const stops = [];
  for (let i = 0; i < 3; i++) {
    await page.keyboard.press("Tab");
    stops.push(await page.evaluate(() => ({ inPanel: !!document.activeElement.closest(".fr-checkout"), text: document.activeElement.textContent })));
  }
  assert.match(stops[0].text, /^Pay \$[\d,]+\.\d\d$/);
  assert.ok(stops[0].inPanel);
  assert.deepEqual(stops[1], { inPanel: true, text: "Back to seats" });
  assert.equal(stops[2].inPanel, false, `third Tab stayed in the panel on ${stops[2].text}`);
  await release(page, hold.hold_token);
  await ctx.close();
});

test("S-PAY-13: in flight the panel keeps its offsetHeight, reads 'Confirming…', and the countdown keeps changing", async () => {
  const { ctx, page } = await customer();
  await toCheckout(page, 2);
  let open;
  const gate = new Promise((r) => (open = r));
  await page.route("**/api/bookings", async (route) => {
    await gate;
    await route.continue();
  });
  const before = await page.locator(".fr-checkout").evaluate((e) => e.offsetHeight);
  const pay = page.locator(".fr-checkout .fr-action");
  await pay.click();
  await page.waitForFunction(() => document.querySelector(".fr-checkout .fr-action").textContent === "Confirming…");
  const during = await page.locator(".fr-checkout").evaluate((e) => e.offsetHeight);
  assert.ok(await pay.isDisabled());
  const d1 = await page.locator(".fr-countdown-digits").textContent();
  await page.waitForTimeout(1300);
  const d2 = await page.locator(".fr-countdown-digits").textContent();
  await shot(page, "pay_in_flight");
  assert.equal(during, before);
  assert.notEqual(d1, d2, "the countdown froze while the confirm was in flight");
  open();
  await page.waitForURL(/\/bookings\/FR-/);
  booked = { reference: decodeURIComponent(page.url().split("/bookings/")[1]), page, ctx };
});

test("S-PAY-13: 'Back to seats' only navigates: no request releases the hold and every lock keeps its token and TTL", async () => {
  const { ctx, page } = await customer();
  const hold = await toCheckout(page, 2);
  const keys = hold.seats.map((s) => `lock:seat:${sid}:${s.seat_id}`);
  const before = keys.map((k) => Number(redis("PTTL", k)));
  const sent = [];
  page.on("request", (r) => r.url().includes("/api/") && sent.push(`${r.method()} ${new URL(r.url()).pathname}`));
  await page.getByRole("button", { name: "Back to seats" }).click();
  await page.waitForURL(new RegExp(`/showtimes/${sid}$`));
  await gridSeats(page).first().waitFor();
  // The seat map that opens reads (GET) its hold back; nothing may write or release it.
  assert.deepEqual(sent.filter((s) => !s.startsWith("GET ")), [], "pressing Back to seats sent a write");
  keys.forEach((k, i) => {
    assert.equal(redis("EXISTS", k), "1", k);
    assert.equal(redis("GET", k), hold.hold_token, k);
    const now = Number(redis("PTTL", k));
    assert.ok(now > 0 && now <= before[i], `${k}: PTTL ${now} vs ${before[i]} before the press`);
  });
  await release(page, hold.hold_token);
  await ctx.close();
});

// ---------------------------------------------------------------- S-PAY-14
test("S-PAY-14: at 0:00 'Hold expired', the zero state once in a polite region, and the map only after 5000 ms", async () => {
  const { ctx, page } = await customer();
  const free = await page.goto(`${BASE}/films`).then(() => page.evaluate(async (sid) =>
    (await (await fetch(`/api/showtimes/${sid}/seatmap`)).json()).seats.find((s) => s.state === "available"), sid));
  const t0 = Date.parse("2026-11-07T10:00:00Z");
  await page.clock.install({ time: t0 });
  await page.addInitScript(TIMERS);
  await seedHold(page, t0 + 60_000 * 60 + 3000, [{ seat_id: free.id, label: free.label ?? "A1", category: "Standard", price_paise: 1299 }]);
  await page.clock.pauseAt(t0 + 60_000 * 60); // pauseAt may only move forward
  await page.goto(`${BASE}/showtimes/${sid}/checkout`);
  await page.locator(".fr-checkout").waitFor();
  const path = `/showtimes/${sid}/checkout`;
  for (let i = 0; i < 20 && (await page.locator(".fr-countdown-digits").textContent()) !== "0:00"; i++) {
    await page.clock.runFor(250);
    await page.waitForTimeout(30);
  }
  await page.waitForFunction(() => document.querySelector(".fr-checkout .fr-action").textContent === "Hold expired");
  const pay = page.locator(".fr-checkout .fr-action");
  assert.ok(await pay.isDisabled());
  const zero = "Your hold has ended and your seats have been released. You have not been charged.";
  const inPolite = await page.evaluate((z) => [...document.querySelectorAll('[aria-live="polite"]')]
    .reduce((n, el) => n + el.textContent.split(z).length - 1, 0), zero);
  assert.equal(inPolite, 1);
  await shot(page, "pay_hold_expired");
  const timer = await page.evaluate(() => window.__timers.filter((t) => t.ms === 5000));
  assert.equal(timer.length, 1, "exactly one return timer");
  const now = await page.evaluate(() => Date.now());
  await page.clock.runFor(timer[0].at + 4999 - now);
  assert.equal(await page.evaluate(() => location.pathname), path, "the route changed before 5000 ms");
  await page.clock.runFor(1);
  await page.waitForURL(new RegExp(`/showtimes/${sid}$`));
  const sel = JSON.parse(await page.evaluate(() => sessionStorage.getItem("fr.selection")));
  assert.deepEqual(sel, { showtime_id: sid, seat_ids: [free.id] });
  await ctx.close();
});

test("S-PAY-14: at 0:00 with a confirm in flight the route stays, no return timer starts, and the response is handled as before", async () => {
  const { ctx, page } = await customer();
  const t0 = Date.parse("2026-11-07T10:00:00Z");
  await page.clock.install({ time: t0 });
  await page.addInitScript(TIMERS);
  await page.addInitScript(() => {
    const f = window.fetch;
    window.__aborted = 0;
    window.fetch = (u, init) => {
      init?.signal?.addEventListener("abort", () => window.__aborted++);
      return f(u, init);
    };
  });
  await seedHold(page, t0 + 3_600_000 + 3000);
  await page.clock.pauseAt(t0 + 3_600_000);
  let answer;
  const gate = new Promise((r) => (answer = r));
  let failed = 0;
  page.on("requestfailed", (r) => r.url().endsWith("/api/bookings") && failed++);
  await page.route("**/api/bookings", async (route) => {
    await gate;
    await route.fulfill({ status: 201, contentType: "application/json", body: JSON.stringify({
      booking_id: 1, booking_reference: "FR-ACDE-FHJD", showtime_id: sid, movie_title: "x", screen_name: "x", starts_at: starts,
      seats: [], total_paise: 1299, currency_code: "USD", payment_status: "succeeded", created_at: new Date(t0).toISOString() }) });
  });
  const path = `/showtimes/${sid}/checkout`;
  await page.goto(BASE + path);
  await page.locator(".fr-checkout .fr-action").click();
  await page.waitForFunction(() => document.querySelector(".fr-checkout .fr-action").textContent === "Confirming…");
  await page.clock.runFor(3000 + 6000);
  await page.waitForTimeout(100);
  assert.equal(await page.locator(".fr-countdown-digits").textContent(), "0:00");
  assert.equal(await page.evaluate(() => location.pathname), path);
  assert.deepEqual(await page.evaluate(() => window.__timers.filter((t) => t.ms === 5000)), [], "a return timer started");
  answer();
  await page.waitForURL(/\/bookings\/FR-ACDE-FHJD$/);
  assert.equal(await page.evaluate(() => window.__aborted), 0);
  assert.equal(failed, 0, "the confirm request was aborted");
  assert.deepEqual(JSON.parse(await page.evaluate(() => sessionStorage.getItem("fr.last_booking_reference"))),
    { booking_reference: "FR-ACDE-FHJD", showtime_id: sid });
  await ctx.close();
});

test("S-PAY-14: a hold response clears fr.last_booking_reference before any navigation, so a second booking reaches checkout", async () => {
  const { ctx, page } = await customer();
  await page.goto(BASE + "/films");
  await page.evaluate((sid) => sessionStorage.setItem("fr.last_booking_reference", JSON.stringify({ booking_reference: "FR-ACDE-FHJD", showtime_id: sid })), sid);
  await page.goto(`${BASE}/showtimes/${sid}`);
  const free = page.locator('[role="grid"] .fr-seat[aria-label$=", available"]');
  await free.first().waitFor();
  await free.first().click();
  let seen = null;
  page.on("response", async (r) => {
    if (r.request().method() === "POST" && r.url().endsWith(`/api/showtimes/${sid}/holds`)) seen = page.url();
  });
  await page.getByRole("button", { name: "Hold these seats" }).click();
  await page.getByRole("button", { name: "Continue to payment" }).waitFor();
  assert.equal(seen, `${BASE}/showtimes/${sid}`, "the hold response arrived on the seat map");
  assert.equal(await page.evaluate(() => sessionStorage.getItem("fr.last_booking_reference")), null);
  assert.equal(page.url(), `${BASE}/showtimes/${sid}`);
  await page.getByRole("button", { name: "Continue to payment" }).click();
  await page.waitForURL(/\/checkout$/);
  await page.locator(".fr-checkout").waitFor();
  await release(page, JSON.parse(await page.evaluate(() => sessionStorage.getItem("fr.hold"))).hold_token);
  await ctx.close();
});

test("S-PAY-14: passing the sales cut-off with the screen open changes no panel text and sends no request", async () => {
  const { ctx, page } = await customer();
  const cutoff = Date.parse(starts) + 15 * 60_000; // SRC-003 OPEN-BOOK-03 (PROVISIONAL): sales close 15 minutes after the start
  await page.clock.install({ time: cutoff - 60_000 });
  await seedHold(page, cutoff + 3_600_000);
  await page.clock.pauseAt(cutoff - 10_000);
  await page.goto(`${BASE}/showtimes/${sid}/checkout`);
  await page.locator(".fr-checkout-showtime").filter({ hasText: /\S · \S/ }).waitFor();
  await page.waitForTimeout(500);
  // The countdown is the one part of the panel that must change with the instant; everything else must not.
  const text = () => page.locator(".fr-checkout").evaluate((p) => {
    const c = p.cloneNode(true);
    c.querySelector(".fr-checkout-countdown").remove();
    return c.textContent;
  });
  const before = await text();
  const sent = [];
  page.on("request", (r) => sent.push(r.url()));
  await page.clock.runFor(20_000);
  await page.waitForTimeout(300);
  assert.equal(await text(), before);
  assert.deepEqual(sent, []);
  await ctx.close();
});

// ---------------------------------------------------------------- S-TKT-04 + S-SCP-15 (the confirmation page)
test("S-TKT-04: the loading state renders the reference element with an empty textContent", async () => {
  const { ctx, page } = await customer();
  let open;
  const gate = new Promise((r) => (open = r));
  await page.route("**/api/me/bookings/FR-ACDE-FHJD", async (route) => {
    await gate;
    await route.fulfill(err(404, "NOT_FOUND", "No booking with that reference is on your account."));
  });
  await page.goto(`${BASE}/bookings/FR-ACDE-FHJD`);
  await page.locator("h1").waitFor();
  const r = await page.evaluate(() => {
    const el = [...document.querySelectorAll(".fr-ref")];
    return { n: el.length, len: el.map((e) => e.textContent.length), h1: document.querySelector("main h1")?.textContent };
  });
  await shot(page, "tkt_loading");
  open();
  assert.equal(r.n, 1, "no reference element in the loading state");
  assert.deepEqual(r.len, [0]);
  assert.equal(r.h1, "Your booking is confirmed.");
  await ctx.close();
});

test("S-TKT-04 / S-SCP-15: first render after confirming - focus, copy, tab order, receipt line once, no svg or canvas", async () => {
  assert.ok(booked, "needs the real confirm from the S-PAY-13 in-flight check");
  const { page, ctx, reference } = booked;
  await ctx.grantPermissions(["clipboard-read", "clipboard-write"], { origin: BASE });
  const h1 = page.locator("main h1");
  await page.locator(".fr-ticket-facts dd").first().waitFor();
  await page.locator(".fr-ticket-receipt").waitFor();
  assert.equal(await h1.textContent(), "Your booking is confirmed.");
  assert.ok(await h1.evaluate((e) => e === document.activeElement), "focus is not on the h1 after arrival");
  const ref = page.locator(".fr-ref");
  assert.match(reference, REF);
  assert.equal(await ref.textContent(), reference);
  assert.equal(await ref.getAttribute("aria-label"), reference.split("-").map((p) => p.split("").join(" ")).join(", "));
  assert.equal(await page.locator(".fr-ref-label").textContent(), "BOOKING REFERENCE");
  const text = await page.locator("main").textContent();
  assert.equal(text.split("A receipt is on its way to e2e-pay-1@example.com.").length - 1, 1);
  assert.deepEqual(await page.locator(".fr-ticket-facts dt").allTextContents(), ["FILM", "HALL", "SHOWTIME", "SEATS", "PAID"]);
  // Order: heading, reference, copy control, facts, resend control - in the DOM, and the focus stops among them in that order.
  const order = await page.evaluate(() => {
    const at = (el) => [...document.querySelectorAll("main *")].indexOf(el);
    const q = (s) => document.querySelector(s);
    const btn = (t) => [...document.querySelectorAll("main button")].find((b) => b.textContent === t);
    return [at(q("main h1")), at(q(".fr-ref")), at(btn("Copy reference")), at(q(".fr-ticket-facts")), at(btn("Send the receipt again"))];
  });
  assert.ok(order.every((x) => x >= 0), `missing element: ${order}`);
  assert.deepEqual([...order].sort((a, b) => a - b), order);
  await page.keyboard.press("Tab");
  assert.equal(await page.evaluate(() => document.activeElement.textContent), "Copy reference");
  await page.keyboard.press("Tab");
  assert.equal(await page.evaluate(() => document.activeElement.textContent), "Send the receipt again");
  // S-SCP-15 on this page.
  assert.equal(await page.evaluate(() => document.querySelectorAll("svg, canvas").length), 0);
  await page.getByRole("button", { name: "Copy reference" }).click();
  await page.locator('[aria-live="polite"]', { hasText: "Reference copied." }).waitFor();
  assert.equal(await page.evaluate(() => navigator.clipboard.readText()), reference);
  // The resend control (SCR-TKT-01): its 202 is announced in a polite region and the reference block does not change.
  await page.route("**/resend-receipt", (r) => r.fulfill({ status: 202, json: { queued: true, email_address: EMAIL } }));
  await page.getByRole("button", { name: "Send the receipt again" }).click();
  await page.locator('[aria-live="polite"]', { hasText: `A receipt was requested. It will arrive at ${EMAIL}.` }).waitFor();
  assert.equal(await ref.textContent(), reference);
  await page.unroute("**/resend-receipt");
  await shot(page, "tkt_first_render");
});

test("S-TKT-04 / S-SCP-15: a later visit has the same blocks, no email sentence, no svg or canvas, and the reference matches P-TKT-01", async () => {
  assert.ok(booked);
  const { page, ctx, reference } = booked;
  await page.reload();
  await page.locator(".fr-ticket-facts dd").first().waitFor();
  await page.waitForTimeout(500);
  const text = await page.evaluate(() => document.body.textContent);
  for (const p of ["on its way", "has been sent", "was sent", "delayed"]) assert.ok(!text.includes(p), `later visit says "${p}"`);
  for (const s of ["Your booking is confirmed.", "BOOKING REFERENCE", "Show this reference at the entrance. A person will check it.",
                   "This booking cannot be changed, cancelled or refunded."]) assert.ok(text.includes(s), s);
  const labelled = await page.evaluate(() => {
    const label = [...document.querySelectorAll("*")].find((e) => e.children.length === 0 && e.textContent === "BOOKING REFERENCE");
    return label.parentElement.querySelector(".fr-ref").textContent;
  });
  assert.match(labelled, REF);
  assert.equal(labelled, reference);
  assert.equal(await page.evaluate(() => document.querySelectorAll("svg, canvas").length), 0);
  await shot(page, "tkt_later_visit");
  // The bookings list links here and is the only other place a booking is shown.
  await page.goto(`${BASE}/bookings`);
  await page.locator(".fr-booking-row").first().waitFor();
  assert.equal(await page.evaluate(() => document.querySelectorAll("svg, canvas").length), 0);
  await shot(page, "acc_bookings_list");
  await ctx.close();
});

test("S-SCP-15: every img on the confirmation page and the bookings list is /api/movies/{id}/poster", {
  todo: "CR-001 B.2 (approved) puts /art/hall_N_view.jpg on the confirmation page; the cell still names the poster route only",
}, async () => {
  const { ctx, page } = await customer();
  const reference = booked?.reference ?? null;
  assert.ok(reference);
  const bad = [];
  for (const path of [`/bookings/${reference}`, "/bookings"]) {
    await page.goto(BASE + path);
    await page.waitForLoadState("networkidle");
    bad.push(...(await page.evaluate(() => [...document.images].map((i) => new URL(i.src, location.href))
      .map((u) => u.pathname + u.search).filter((s) => !/^\/api\/movies\/[0-9]+\/poster([?].*)?$/.test(s)))));
  }
  await ctx.close();
  assert.deepEqual(bad, []);
});

// ---------------------------------------------------------------- S-SCP-10
test("S-SCP-10: changing Language sends GET /api/movies?language_id and leaves html lang and the nav's link names unchanged", async () => {
  for (const who of [guest, customer]) {
    const { ctx, page } = await who();
    await page.goto(BASE + "/films");
    // The Language control is a single-choice button group (S-BRW-03: the listing renders no select).
    const select = page.getByRole("group", { name: "Language", exact: true });
    await select.waitFor({ state: "attached" });
    await page.waitForLoadState("networkidle");
    const snap = () => page.evaluate(() => ({
      lang: document.documentElement.getAttribute("lang"),
      links: [...document.querySelectorAll('nav a, [role="navigation"] a')].map((a) => a.getAttribute("aria-label") ?? a.textContent),
    }));
    const before = await snap();
    const req = page.waitForRequest((r) => r.method() === "GET" && new URL(r.url()).pathname === "/api/movies"
      && !!new URL(r.url()).searchParams.get("language_id"));
    const choice = select.getByRole("button").nth(1);
    if (!(await choice.isVisible())) await page.getByRole("button", { name: /filter/i }).first().click();
    await choice.click();
    await req;
    await page.waitForLoadState("networkidle");
    assert.deepEqual(await snap(), before);
    if (who === customer) assert.ok(before.links.length > 0, "a signed-in customer has a navigation landmark");
    await ctx.close();
  }
});

// ---------------------------------------------------------------- S-ACC-07 (SCR-ACC-02's panel)
test("S-ACC-07: the 202 body, SCR-ACC-02's panel and the rendered email carry the same TTL minutes in one run", async () => {
  const ttl = Number(execFileSync("docker", ["exec", "frontrow-api-1", "python", "-c",
    "from app.core.config import load_settings; print(load_settings().PASSWORD_RESET_TTL_SECONDS)"], { encoding: "utf8" }).trim());
  const minutes = `expires in ${Math.floor(ttl / 60)} minutes`;
  const since = new Date().toISOString();
  const { ctx, page } = await guest();
  await page.goto(BASE + "/account/reset");
  await page.getByLabel("Email address").fill(EMAIL);
  const resp = page.waitForResponse((r) => r.url().endsWith("/api/auth/password-reset/request"));
  await page.getByRole("button", { name: "Send a reset link" }).click();
  const r = await resp;
  assert.equal(r.status(), 202);
  const body = await r.json();
  const panel = page.locator(".fr-panel");
  await panel.waitFor();
  await shot(page, "acc_reset_sent");
  assert.equal(await panel.textContent(), body.message);
  assert.ok(body.message.includes(minutes), `202 body: ${body.message}`);
  assert.equal(await page.locator("form").count(), 0, "the form is replaced: no second send control");
  // The worker's stub transport logs the rendered message (MAIL_PROVIDER=stub); the token itself is never printed here.
  let mail = null;
  for (let i = 0; i < 40 && !mail; i++) {
    const log = execFileSync("docker", ["logs", "--since", since, "frontrow-worker-1"], { encoding: "utf8", stdio: ["ignore", "pipe", "pipe"] });
    mail = log.split("\n").filter((l) => l.includes("stub mail transport")).map((l) => JSON.parse(l).mime)
      .find((m) => /reset/i.test(m.split("\n\n")[0]));
    if (!mail) await page.waitForTimeout(500);
  }
  assert.ok(mail, "no reset email reached the stub transport");
  const decoded = mail.replace(/=\r?\n/g, "").replace(/=([0-9A-F]{2})/g, (_, h) => String.fromCharCode(parseInt(h, 16)));
  const parts = [...decoded.matchAll(/\n\n([A-Za-z0-9+/=\n]{40,})\n/g)].map((m) => Buffer.from(m[1], "base64").toString("utf8"));
  assert.ok([decoded, ...parts].some((t) => t.includes(`${Math.floor(ttl / 60)} minutes`)), "the email does not carry the same minutes");
  await ctx.close();
});

// ---------------------------------------------------------------- S-XCT-22 (interface)
test("S-XCT-22: the five 409 codes drive five branches, each rendering a different string", async () => {
  const shown = {};
  const SEAT = "Seat {L} was taken by another customer. Choose a different seat and press Hold these seats again.";
  // SEAT_UNAVAILABLE and SALES_CLOSED: the seat map's hold.
  for (const code of ["SEAT_UNAVAILABLE", "SALES_CLOSED"]) {
    const { ctx, page } = await customer();
    await page.goto(`${BASE}/showtimes/${sid}`);
    const free = page.locator('[role="grid"] .fr-seat[aria-label$=", available"]');
    await free.first().waitFor();
    const label = await free.first().getAttribute("aria-label");
    const seat = label.replace(/^Row ([A-Z]+) seat (\d+).*$/, "$1$2");
    await free.first().click();
    const msg = code === "SALES_CLOSED" ? "Sales for this showtime closed at 6:15 pm. Choose another showtime." : SEAT.replace("{L}", seat);
    await page.route(`**/api/showtimes/${sid}/holds`, (r) => r.fulfill(err(409, code, msg, { details: code === "SEAT_UNAVAILABLE" ? { unavailable_seats: [seat] } : {} })));
    await page.getByRole("button", { name: "Hold these seats" }).click();
    await page.getByText(msg).waitFor();
    shown[code] = msg;
    if (code === "SEAT_UNAVAILABLE") {
      assert.equal(await page.locator(`[role="grid"] [aria-label^="Row ${seat.match(/^[A-Z]+/)[0]} seat ${seat.match(/\d+$/)[0]},"]`).getAttribute("aria-label")
        .then((l) => l.endsWith("held by someone else")), true, "the taken seat was not repainted");
    }
    await shot(page, `pay_409_${code.toLowerCase()}`);
    await ctx.close();
  }
  // HOLD_EXPIRED and IDEMPOTENCY_IN_FLIGHT: the checkout's confirm.
  {
    const { ctx, page } = await customer();
    await seedHold(page, Date.now() + 170_000);
    const msg = "The hold on your seats has ended and they have been released. You have not been charged. Choose them again if they are still free.";
    await page.route("**/api/bookings", (r) => r.fulfill(err(409, "HOLD_EXPIRED", msg)));
    await page.goto(`${BASE}/showtimes/${sid}/checkout`);
    await page.locator(".fr-checkout .fr-action").click();
    assert.equal(await page.locator(".fr-banner").textContent(), msg);
    shown.HOLD_EXPIRED = msg;
    await ctx.close();
  }
  {
    const { ctx, page } = await customer();
    await seedHold(page, Date.now() + 170_000);
    const keys = [];
    await page.route("**/api/bookings", (r) => {
      keys.push(r.request().headers()["idempotency-key"]);
      return r.fulfill(err(409, "IDEMPOTENCY_IN_FLIGHT", "A request with this key is already being processed.", { headers: { "Retry-After": "1" } }));
    });
    await page.goto(`${BASE}/showtimes/${sid}/checkout`);
    const pay = page.locator(".fr-checkout .fr-action");
    await pay.click();
    await page.waitForFunction(() => !document.querySelector(".fr-checkout .fr-action").disabled, null, { timeout: 10_000 });
    assert.equal(keys.length, 4);
    assert.equal(new Set(keys).size, 1);
    shown.IDEMPOTENCY_IN_FLIGHT = await page.locator(".fr-banner").textContent();
    assert.equal(shown.IDEMPOTENCY_IN_FLIGHT, "This booking is still being processed.");
    await ctx.close();
  }
  // VERSION_CONFLICT: an admin save, every response stubbed (no admin credentials are used).
  {
    const { ctx, page } = await guest();
    const STALE = "This film was changed by someone else while you were editing. Reload to see the current details, then make your change again. Nothing you typed has been saved.";
    const film = { id: 1, title: "Stub film", synopsis: "s", runtime_minutes: 100, certification_id: 1, language_id: 1, genre_ids: [1],
                   version: 3, status: "draft", display_from: null, display_until: null, poster_url: null };
    await page.route("**/api/auth/me", (r) => r.fulfill({ json: { user_id: 1, email: "admin@example.invalid", role: "admin" } }));
    await page.route("**/api/admin/**", (r) => {
      const u = new URL(r.request().url());
      if (r.request().method() === "PATCH") return r.fulfill(err(409, "VERSION_CONFLICT", STALE));
      if (u.pathname.startsWith("/api/admin/lookups/")) return r.fulfill({ json: { items: [{ id: 1, name: "One" }] } });
      if (u.pathname === "/api/admin/cinemas") return r.fulfill({ json: { items: [{ timezone: "Asia/Kolkata" }] } });
      return r.fulfill({ json: film });
    });
    await page.goto(`${BASE}/admin/movies/1`);
    const title = page.getByLabel("Title");
    await title.waitFor();
    await page.waitForFunction(() => document.querySelector("input")?.value === "Stub film");
    await title.fill("Typed title");
    await page.getByRole("button", { name: /^Save/ }).click();
    await page.getByText(STALE).waitFor();
    assert.equal(await title.inputValue(), "Typed title", "the conflict dropped what was typed");
    shown.VERSION_CONFLICT = STALE;
    await ctx.close();
  }
  assert.equal(Object.keys(shown).length, 5);
  assert.equal(new Set(Object.values(shown)).size, 5, JSON.stringify(shown));
});

test("S-XCT-22: on every page a 4xx's request id is not displayed and a 5xx's is", async () => {
  const pages = [
    { name: "checkout", path: () => `/showtimes/${sid}/checkout`, seed: true, api: "**/api/bookings", act: (p) => p.locator(".fr-checkout .fr-action").click(),
      four: (id) => err(409, "SEAT_UNAVAILABLE", "Seat A1 was taken by another customer.", { request_id: id }) },
    { name: "confirmation", path: () => "/bookings/FR-ACDE-FHJD", api: "**/api/me/bookings/FR-ACDE-FHJD",
      four: (id) => err(404, "NOT_FOUND", "No booking with that reference is on your account.", { request_id: id }) },
    { name: "my bookings", path: () => "/bookings", api: "**/api/me/bookings?*",
      four: (id) => err(429, "RATE_LIMITED", "Too many attempts. Try again in 3 seconds.", { request_id: id }) },
    { name: "reset request", path: () => "/account/reset", guest: true, api: "**/api/auth/password-reset/request",
      act: async (p) => { await p.getByLabel("Email address").fill("x@example.com"); await p.getByRole("button", { name: "Send a reset link" }).click(); },
      four: (id) => err(422, "VALIDATION_FAILED", "Enter an email address.", { request_id: id }) },
    { name: "sign in", path: () => "/sign-in", guest: true, api: "**/api/auth/login",
      act: async (p) => { await p.getByLabel("Email address").fill("x@example.com"); await p.locator("#fr-password").fill("abcdefghijklm"); await p.locator("form .fr-action").click(); },
      four: (id) => err(401, "CREDENTIALS_INVALID", "That email address and password do not match an account.", { request_id: id }) },
  ];
  const five = (id) => err(500, "INTERNAL_ERROR", `The server could not complete this request. If you need help, quote ${id}.`, { request_id: id });
  for (const pg of pages) {
    for (const [kind, make] of [["4xx", pg.four], ["5xx", five]]) {
      const { ctx, page } = await (pg.guest ? guest() : customer());
      const id = hex8();
      if (pg.seed) await seedHold(page, Date.now() + 170_000);
      await page.route(pg.api, (r) => r.fulfill(make(id)));
      const res = page.waitForResponse((r) => r.status() >= 400 && r.url().includes(pg.api.replace(/\*+/g, "").split("?")[0]));
      await page.goto(BASE + pg.path());
      if (pg.act) await pg.act(page);
      await res;
      await page.waitForTimeout(400);
      const text = await page.evaluate(() => document.body.innerText);
      if (kind === "4xx") assert.ok(!text.includes(id), `${pg.name}: a ${kind} page shows its request id`);
      else assert.ok(text.includes(id), `${pg.name}: a 5xx page does not show its request id`);
      await ctx.close();
    }
  }
});

// ---------------------------------------------------------------- S-XCT-38 (keyboard)
/** Every visible, enabled element with a React onClick, and whether Tab lands on it (or on a focusable inside it). A
 *  roving-tabindex member (tabindex -1 inside a composite holding exactly one tabindex 0 - the seat map, the day and filter
 *  groups) is counted reached when its group's one tab stop is, because the arrow keys move within it (SCR-SEA-01, S-BRW-03). */
async function unreachable(page) {
  const n = await page.evaluate(() => {
    let i = 0;
    for (const el of document.querySelectorAll("body *")) {
      const k = Object.keys(el).find((x) => x.startsWith("__reactProps$"));
      if (!k || typeof el[k].onClick !== "function" || el.disabled || el.getAttribute("aria-disabled") === "true" || !el.getClientRects().length) continue; // disabled = not interactive
      let id = String(i++);
      const group = el.getAttribute("tabindex") === "-1" && el.parentElement?.closest('[role="grid"],[role="group"],[role="toolbar"],[role="tablist"],[role="radiogroup"]');
      const stop = group && group.querySelectorAll('[tabindex="0"]').length === 1 ? group.querySelector('[tabindex="0"]') : null;
      if (stop) id = "g:" + (stop.getAttribute("data-e2e-stop") ?? (stop.setAttribute("data-e2e-stop", String(i)), String(i)));
      el.setAttribute("data-e2e-click", id);
    }
    return i;
  });
  const reached = new Set();
  await page.evaluate(() => { document.activeElement?.blur(); window.getSelection()?.removeAllRanges(); });
  for (let step = 0; step < n * 2 + 60; step++) {
    await page.keyboard.press("Tab");
    const hit = await page.evaluate(() => {
      const a = document.activeElement;
      if (!a || a === document.body || a.tabIndex < 0) return [];
      const own = a.closest("[data-e2e-click]")?.getAttribute("data-e2e-click");
      const stop = a.getAttribute("data-e2e-stop");
      return [own, stop && "g:" + stop].filter(Boolean);
    });
    hit.forEach((h) => reached.add(h));
  }
  return page.evaluate((r) => [...document.querySelectorAll("[data-e2e-click]")].filter((e) => !r.includes(e.getAttribute("data-e2e-click")))
    .map((e) => `${e.tagName.toLowerCase()}.${e.className}: ${(e.getAttribute("aria-label") ?? e.textContent).slice(0, 60)}`), [...reached]);
}

test("S-XCT-38: every element with an onClick handler on every customer and guest route is reached by Tab", async () => {
  const misses = {};
  const { ctx, page } = await customer();
  await page.goto(BASE + "/films");
  const movie = await page.evaluate(async () => (await (await fetch("/api/movies")).json()).movies[0].id);
  const routes = ["/", "/films", `/movies/${movie}`, `/showtimes/${sid}`, "/bookings", ...(booked ? [`/bookings/${booked.reference}`] : []),
                  "/no-such-page"];
  for (const r of routes) {
    await page.goto(BASE + r);
    await page.waitForLoadState("networkidle").catch(() => null);
    await page.waitForTimeout(800);
    const m = await unreachable(page);
    if (m.length) misses[r] = m;
  }
  const hold = await toCheckout(page, 1);
  await page.waitForTimeout(300);
  const m = await unreachable(page);
  if (m.length) misses["/showtimes/:id/checkout"] = m;
  await release(page, hold.hold_token);
  await ctx.close();
  const g = await guest();
  for (const r of ["/sign-in", "/register", "/account/reset", "/account/reset/confirm#token=abc", "/films", `/showtimes/${sid}`]) {
    await g.page.goto(BASE + r);
    await g.page.waitForLoadState("networkidle").catch(() => null);
    await g.page.waitForTimeout(800);
    const mm = await unreachable(g.page);
    if (mm.length) misses[`guest ${r}`] = mm;
  }
  await g.ctx.close();
  assert.deepEqual(misses, {});
});

test("S-XCT-38: the seat map has exactly one tabindex=0 cell; Tab enters the map once and the next Tab leaves it", async () => {
  const { ctx, page } = await customer();
  await page.goto(`${BASE}/showtimes/${sid}`);
  await gridSeats(page).first().waitFor();
  await page.getByRole("button", { name: "2D map" }).click().catch(() => null);
  assert.equal(await page.locator('[role="grid"] [tabindex="0"]').count(), 1);
  // The element before the map in tab order: walk until focus is in the grid, remembering the previous stop.
  await page.evaluate(() => document.activeElement?.blur());
  let prev = null, inGrid = false;
  for (let i = 0; i < 80 && !inGrid; i++) {
    const was = await page.evaluate(() => document.activeElement?.outerHTML.slice(0, 80) ?? null);
    await page.keyboard.press("Tab");
    inGrid = await page.evaluate(() => !!document.activeElement?.closest('[role="grid"]'));
    if (inGrid) prev = was;
  }
  assert.ok(inGrid && prev, "Tab never entered the seat map");
  await page.keyboard.press("Tab");
  assert.equal(await page.evaluate(() => !!document.activeElement?.closest('[role="grid"]')), false, "the second Tab stayed in the map");
  await page.keyboard.press("Shift+Tab");
  assert.equal(await page.evaluate(() => !!document.activeElement?.closest('[role="grid"]')), true, "Shift+Tab did not re-enter the map");
  await shot(page, "acc_seatmap_focus");
  await ctx.close();
});

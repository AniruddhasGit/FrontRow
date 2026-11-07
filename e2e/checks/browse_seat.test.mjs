// Real-browser checks for the open clauses of the browse and seat-map stories (ledger StatusNotes, 2026-11-07).
// Run: cd e2e && node --test checks/browse_seat.test.mjs   (local stack + Vite on :5173; local data only)
// Fixture payloads are the real seatmap response with fields changed in flight (page.route), so a clause that needs an
// inactive seat, a sold-out hall or a held seat is reached without reseeding. Holds by "another customer" are real
// (POST /api/showtimes/{id}/holds from a second account) and are released before each test ends.
import { test, before, after } from "node:test";
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { launch, signedIn, gridSeats, BASE } from "../lib.mjs";

const EV = new URL("../evidence/", import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, "$1");
let browser;
let ST; // the 220-seat hall's latest open showtime
let MAP; // its real seatmap at start

const api = async (path) => (await fetch(BASE + path)).json();

before(async () => {
  browser = await launch();
  const films = (await api("/api/movies")).movies;
  const found = [];
  for (const f of films) {
    const st = (await api(`/api/showtimes?movie_id=${f.id}`)).showtimes ?? [];
    for (const s of st.filter((s) => !s.sales_closed)) {
      const m = await api(`/api/showtimes/${s.id}/seatmap`);
      if (m.seats?.length === 220) found.push({ s, m });
    }
  }
  found.sort((a, b) => b.s.starts_at.localeCompare(a.s.starts_at));
  assert.ok(found.length, "an open showtime in the 220-seat hall");
  ST = found[0].s.id;
  MAP = found[0].m;
});
after(() => browser?.close());

// ---- helpers ------------------------------------------------------------------------------------------------------
const seatSel = (s) => `[role="grid"] [data-seat-id="${s.id}"]`;
const avail = () => MAP.seats.filter((s) => s.state === "available" && s.is_active);

/** Serve the seatmap through `mutate(json)`; `.set(fn)` swaps the mutation for the following polls. */
async function fixture(page, mutate = (m) => m) {
  let fn = mutate;
  let calls = 0;
  await page.route(/\/api\/showtimes\/\d+\/seatmap$/, async (route) => {
    const r = await route.fetch();
    const m = await r.json();
    calls++;
    await route.fulfill({ response: r, json: fn(m) ?? m });
  });
  return { set: (f) => (fn = f), calls: () => calls };
}

/** The computed value of `prop` for an element styled `prop: var(token)` - the token's resolved value in this theme. */
const resolve = (page, token, prop = "backgroundColor") =>
  page.evaluate(([t, p]) => {
    const d = document.createElement("div");
    d.style[p] = `var(${t})`;
    document.body.append(d);
    const v = getComputedStyle(d)[p];
    d.remove();
    return v;
  }, [token, prop]);

const style = (page, sel, props) =>
  page.$eval(sel, (el, ps) => Object.fromEntries(ps.map((p) => [p, getComputedStyle(el)[p]])), props);

/** /api requests other than the seatmap poll, from now on. */
function spy(page) {
  const list = [];
  page.on("request", (r) => {
    const u = new URL(r.url());
    if (u.pathname.startsWith("/api/") && !/\/seatmap$/.test(u.pathname)) list.push(`${r.method()} ${u.pathname}`);
  });
  return list;
}

async function guest(viewport = { width: 1440, height: 900 }, opts = {}) {
  const ctx = await browser.newContext({ viewport, ...opts });
  // Diagnosis only: FR_PROBE_UNZOOM=1 cancels immersive.css's `zoom: 0.72` on the grid, to show it is the one cause
  // of the desktop failures. Never set in a real run.
  if (process.env.FR_PROBE_UNZOOM) await ctx.addInitScript(() => document.addEventListener("DOMContentLoaded", () =>
    document.head.append(Object.assign(document.createElement("style"), { textContent: ".fr-grid { zoom: 1 !important; }" }))));
  return { ctx, page: await ctx.newPage() };
}

const ss = (page) => page.evaluate(() => ({
  sel: sessionStorage.getItem("fr.selection"), pending: sessionStorage.getItem("fr.pending_selection"),
  hold: sessionStorage.getItem("fr.hold"), ls: localStorage.length,
}));
const selIds = async (page) => JSON.parse((await ss(page)).sel ?? '{"seat_ids":[]}').seat_ids;
const redis = (...args) => execFileSync("docker", ["exec", "frontrow-redis-1", "redis-cli", ...args], { encoding: "utf8" }).trim();
const open = async (page) => {
  await page.goto(`${BASE}/showtimes/${ST}`);
  await gridSeats(page).first().waitFor();
};

// ---- S-BRW-02 -----------------------------------------------------------------------------------------------------
test("S-BRW-02 synopsis clamp 3 / none, 900 chars in full, a missing poster draws the title and no img", async () => {
  const { ctx, page } = await guest();
  const long = "x".repeat(899) + "Z";
  const films = (await api("/api/movies")).movies;
  const missing = films[0];
  await page.route(/\/api\/movies(\?.*)?$/, async (route) => {
    const r = await route.fetch();
    const j = await r.json();
    j.movies[0].synopsis = long;
    await route.fulfill({ response: r, json: j });
  });
  await page.route(new RegExp(`/api/movies/${missing.id}$`), async (route) => {
    const r = await route.fetch();
    await route.fulfill({ response: r, json: { ...(await r.json()), synopsis: long } });
  });
  await page.route(new RegExp(`/api/movies/${missing.id}/poster$`), (route) => route.fulfill({ status: 404, body: "" }));
  await page.goto(BASE + "/films");
  const card = page.locator(".fr-card").filter({ has: page.locator(".fr-card-title", { hasText: missing.title }) });
  await card.locator(".fr-poster[data-empty]").waitFor();
  const syn = card.locator(".fr-card-synopsis");
  assert.equal(await syn.textContent(), long, "the 900-character synopsis arrives in full");
  assert.equal(await syn.evaluate((e) => getComputedStyle(e).webkitLineClamp), "3");
  assert.equal(await card.locator("img").count(), 0, "no img in the missing-poster card");
  assert.equal(await card.locator(".fr-poster").textContent(), missing.title, "the box says the title and nothing else");
  assert.equal(await card.locator(".fr-poster-title").evaluate((e) => getComputedStyle(e).color), await resolve(page, "--fr-ink-muted", "color"));
  const text = await page.locator("body").innerText();
  for (const w of ["No poster", "Image unavailable", "not found"]) assert.ok(!text.includes(w), w);
  await page.screenshot({ path: EV + "brw_02_films_missing_poster.png" });
  await page.goto(`${BASE}/movies/${missing.id}`);
  const ms = page.locator(".fr-movie-synopsis");
  await ms.waitFor();
  assert.equal(await ms.textContent(), long);
  assert.equal(await ms.evaluate((e) => getComputedStyle(e).webkitLineClamp), "none");
  await ctx.close();
});

// ---- S-BRW-11 -----------------------------------------------------------------------------------------------------
test("S-BRW-11 all 220 seats out of service: none activates on Enter or Space", async () => {
  const { ctx, page } = await guest();
  await fixture(page, (m) => ({ ...m, seats: m.seats.map((s) => ({ ...s, is_active: false })) }));
  await open(page);
  const cells = gridSeats(page);
  assert.equal(await cells.count(), 220);
  const names = await cells.evaluateAll((els) => els.map((e) => e.getAttribute("aria-label")));
  assert.ok(names.every((n) => n.endsWith("out of service")));
  const calls = spy(page);
  for (let i = 0; i < 220; i++) {
    await cells.nth(i).focus();
    await page.keyboard.press("Enter");
    await page.keyboard.press(" ");
  }
  assert.equal((await ss(page)).sel, null, "fr.selection never written");
  assert.equal(await page.locator(".fr-summary-heading").textContent(), "0 seats chosen");
  assert.deepEqual(calls, []);
  assert.ok((await page.locator(".fr-banners").innerText()).includes("None of the seats in this hall are available."));
  await page.screenshot({ path: EV + "sea_brw11_all_out_of_service.png" });
  await ctx.close();
});

// ---- S-BRW-12 -----------------------------------------------------------------------------------------------------
test("S-BRW-12 inactive cell style, ArrowRight, no selection; glyphs survive one colour; change ring on fake timer", async (t) => {
  // C-12 (the AC's seat) made inactive and Premium; the cell at the gc to its left in the same row
  const c12 = MAP.seats.find((s) => s.row === "C" && s.num === 12);
  const left = MAP.seats.filter((s) => s.gr === c12.gr && s.gc < c12.gc).sort((a, b) => b.gc - a.gc)[0];
  const premium = MAP.categories.find((c) => c.name === "Premium");
  for (const width of [375, 1440]) for (const state of ["available", "held", "sold"]) await t.test(`inactive C-12, wire state ${state}, ${width}px`, async () => {
    const { ctx, page } = await guest({ width, height: 900 });
    await fixture(page, (m) => ({ ...m, seats: m.seats.map((s) => (s.id === c12.id ? { ...s, is_active: false, state, cat: premium.id, price_paise: premium.price_paise } : s)) }));
    await open(page);
    const st = await style(page, seatSel(c12), ["borderTopStyle", "borderTopWidth", "backgroundColor"]);
    assert.deepEqual(st, { borderTopStyle: "dashed", borderTopWidth: "1px", backgroundColor: "rgba(0, 0, 0, 0)" }, state);
    assert.equal(await page.locator(seatSel(c12)).textContent(), "12", "renders its seat number");
    assert.equal(await page.locator(seatSel(c12)).getAttribute("aria-label"), "Row C seat 12, Premium, out of service");
    await page.locator(seatSel(left)).focus();
    await page.keyboard.press("ArrowRight");
    assert.equal(await page.evaluate(() => document.activeElement?.getAttribute("data-seat-id")), String(c12.id), "ArrowRight lands on it");
    await page.keyboard.press("Enter");
    await page.keyboard.press(" ");
    assert.equal((await ss(page)).sel, null, `no selection on Enter/Space (${state})`);
    if (state === "available") {
      assert.equal(await page.locator(".fr-legend-states .fr-swatch").count(), 5);
      assert.equal(await page.locator(".fr-legend-states li").nth(4).innerText(), "Out of service");
    }
    await ctx.close();
  });

  await t.test("four states, one colour: four distinct data-glyph values", async () => {
    const [a, b, c, d] = avail();
    const { ctx, page } = await guest();
    await fixture(page, (m) => ({ ...m, seats: m.seats.map((s) => (s.id === b.id ? { ...s, state: "held" } : s.id === c.id ? { ...s, state: "sold" } : s)) }));
    await open(page);
    await page.locator(seatSel(d)).click(); // held_by_me through the selection
    await page.addStyleTag({ content: ":root, :root[data-theme] { --fr-seat-available: red; --fr-seat-sold: red; --fr-seat-held-other: red; --fr-seat-mine: red; --fr-seat-ink: red; --fr-seat-ink-mine: red; --fr-seat-edge-available: red; --fr-seat-edge-mine: red; }" });
    const glyphs = await Promise.all([a, b, c, d].map((s) => page.locator(seatSel(s)).getAttribute("data-glyph")));
    assert.deepEqual(new Set(glyphs), new Set(["outline", "bar", "hatch", "check"]));
    await page.screenshot({ path: EV + "sea_brw12_one_colour.png" });
    await ctx.close();
  });

  await t.test("every seat sold: 220 cells, the banner, no 'Nothing'", async () => {
    const { ctx, page } = await guest();
    await fixture(page, (m) => ({ ...m, seats: m.seats.map((s) => ({ ...s, state: "sold" })) }));
    await open(page);
    assert.equal(await gridSeats(page).count(), 220);
    const text = await page.locator("body").innerText();
    assert.ok(text.includes("Every seat for this showtime is sold."));
    assert.ok(!text.includes("Nothing"));
    await ctx.close();
  });

  // the change ring, on Playwright's fake clock; then again under prefers-reduced-motion
  for (const width of [375, 1440]) for (const reducedMotion of ["no-preference", "reduce"]) await t.test(`change ring, reduced motion ${reducedMotion}, ${width}px`, async () => {
    const seat = avail()[0];
    const { ctx, page } = await guest({ width, height: 900 }, { reducedMotion });
    await page.clock.install();
    const fx = await fixture(page);
    await open(page);
    await page.clock.pauseAt(await page.evaluate(() => Date.now() + 100));
    fx.set((m) => ({ ...m, seats: m.seats.map((s) => (s.id === seat.id ? { ...s, state: "held" } : s)) }));
    // step the fake clock 100ms at a time until the changed poll has rendered (the clock stands still between steps,
    // so the ring's timer starts at the end of a step: at most 100ms of fake time has run on it when it is seen)
    const ringed = page.locator(`${seatSel(seat)}[data-changed]`);
    for (let i = 0; i < 150 && (await ringed.count()) === 0; i++) {
      await page.clock.runFor(100);
      await page.waitForTimeout(50);
    }
    await ringed.waitFor({ state: "attached", timeout: 2000 });
    const ring = await style(page, seatSel(seat), ["outlineWidth", "outlineStyle", "outlineColor", "animationName"]);
    assert.equal(ring.outlineWidth, "2px");
    assert.equal(ring.outlineStyle, "solid");
    assert.equal(ring.outlineColor, await resolve(page, "--fr-focus-ring", "color"));
    if (reducedMotion === "reduce") assert.equal(ring.animationName, "none");
    await page.clock.runFor(780);
    assert.equal(await ringed.count(), 1, `still ringed before --fr-motion-change has elapsed (${reducedMotion})`);
    await page.clock.runFor(140);
    await page.locator(`${seatSel(seat)}[data-changed]`).waitFor({ state: "detached" });
    await ctx.close();
  });
});

// ---- S-BRW-13 -----------------------------------------------------------------------------------------------------
test("S-BRW-13 the legend's price placeholder is a --fr-surface-inset block with no $", async () => {
  const { ctx, page } = await guest();
  let release;
  const gate = new Promise((r) => (release = r));
  await page.route(/\/api\/showtimes\/\d+\/seatmap$/, async (route) => {
    await gate;
    await route.continue();
  });
  await page.goto(`${BASE}/showtimes/${ST}`);
  const block = page.locator(".fr-legend-categories .fr-inset-block");
  await block.waitFor();
  assert.equal(await block.evaluate((e) => getComputedStyle(e).backgroundColor), await resolve(page, "--fr-surface-inset"));
  assert.ok(!(await page.locator(".fr-legend-categories").innerText()).includes("$"));
  assert.ok(!(await page.locator("body").innerText()).includes("$0.00"), "no $0.00 while the price is unknown");
  await page.screenshot({ path: EV + "sea_brw13_price_placeholder.png" });
  release();
  await gridSeats(page).first().waitFor();
  await ctx.close();
});

// ---- S-BRW-17 -----------------------------------------------------------------------------------------------------
test("S-BRW-17 field, screen bar and row gutters keep their rects across the seat-map response", async (t) => {
  const { ctx, page } = await guest();
  let release;
  const gate = new Promise((r) => (release = r));
  await page.route(/\/api\/showtimes\/\d+\/seatmap$/, async (route) => {
    await gate;
    await route.continue();
  });
  await page.goto(`${BASE}/showtimes/${ST}`);
  await page.locator(".fr-field").waitFor();
  await page.waitForTimeout(300);
  const rects = () => page.evaluate(() => ({
    field: document.querySelector(".fr-field")?.getBoundingClientRect().toJSON(),
    bar: document.querySelector(".fr-screen-bar")?.getBoundingClientRect().toJSON(),
    gutters: [...document.querySelectorAll(".fr-gutter")].map((g) => g.getBoundingClientRect().toJSON()),
    loading: document.querySelectorAll('[role="progressbar"], [aria-label*="Loading"]').length,
  }));
  const a = await rects();
  await page.screenshot({ path: EV + "sea_brw17_before.png" });
  release();
  await gridSeats(page).first().waitFor();
  const b = await rects();
  await page.screenshot({ path: EV + "sea_brw17_after.png" });
  await ctx.close();
  await t.test("no progressbar and no 'Loading' name at either point", () => {
    assert.equal(a.loading, 0);
    assert.equal(b.loading, 0);
  });
  await t.test("screen bar rect equal", () => assert.deepEqual(a.bar, b.bar));
  await t.test("field x, y and width equal", () => {
    assert.deepEqual([a.field.x, a.field.y, a.field.width], [b.field.x, b.field.y, b.field.width]);
  });
  // The hall's row count arrives only in the seatmap response (GET /api/showtimes/{id} carries no rows/cols), so
  // the field's height and the gutters cannot exist before it: kept as written, expected red (doc conflict).
  await t.test("field height and row gutter rects equal (AC as written)", () => {
    assert.equal(a.field.height, b.field.height, "field height");
    assert.deepEqual(a.gutters, b.gutters, "row gutter rects");
  });
});

// ---- S-SCP-09 + S-XCT-39 (geometry) ------------------------------------------------------------------------------
test("S-SCP-09 the map scrolls in its own box at 375px; the cell is 24px at 375 and at 1280", async () => {
  const out = {};
  for (const width of [375, 1280]) {
    const { ctx, page } = await guest({ width, height: 900 });
    await open(page);
    out[width] = await page.evaluate(() => {
      const sc = document.querySelector(".fr-grid-scroll");
      const cell = document.querySelector('[role="grid"] .fr-seat');
      return { sw: sc.scrollWidth, cw: sc.clientWidth, bsw: document.body.scrollWidth, bcw: document.body.clientWidth,
               width: getComputedStyle(cell).width, drawn: cell.getBoundingClientRect().width };
    });
    await page.screenshot({ path: EV + `sea_scp09_${width}.png` });
    await ctx.close();
  }
  assert.ok(out[375].sw > out[375].cw, "the map container scrolls at 375");
  assert.equal(out[375].bsw, out[375].bcw, "the body does not");
  assert.equal(out[375].width, "24px");
  assert.equal(out[1280].width, "24px", `computed width at 1280 (drawn ${out[1280].drawn}px)`);
  assert.equal(out[1280].drawn, 24, "drawn width at 1280 - never shrunk");
});

test("S-XCT-39 375px: 24/4 tokens, body never wider on any route, strip geometry, minimum scroll, scroll-padding, poll keeps scrollLeft, poster 2/3", async (t) => {
  const { ctx, page } = await guest({ width: 375, height: 800 }, { hasTouch: true, isMobile: true });
  // every route at 375
  const movie = (await api("/api/movies")).movies[0].id;
  for (const r of ["/", "/films", "/browse", `/movies/${movie}`, `/showtimes/${ST}`, `/showtimes/${ST}/checkout`, "/sign-in", "/register", "/account/reset", "/account/reset/confirm", "/bookings"]) {
    await page.goto(BASE + r);
    await page.waitForTimeout(800);
    const bsw = await page.evaluate(() => document.body.scrollWidth);
    assert.ok(bsw <= 375, `${r}: body.scrollWidth ${bsw}`);
  }
  // poster slots 2/3, height unchanged by the image load
  // the images are held back until the boxes are measured, so "before" is truly before the load
  let letImages;
  const imagesHeld = new Promise((r) => (letImages = r));
  await page.route(/\/api\/movies\/\d+\/poster$/, async (route) => { await imagesHeld; await route.continue(); });
  await page.goto(BASE + "/films");
  const real = ".fr-card:not(.fr-card-loading) .fr-poster";
  await page.locator(real).first().waitFor();
  const posters = await page.$$eval(real, (els) => els.map((e) => [getComputedStyle(e).aspectRatio, e.offsetHeight]));
  letImages();
  await page.waitForLoadState("networkidle");
  await page.waitForTimeout(300);
  const postersAfter = await page.$$eval(real, (els) => els.map((e) => [getComputedStyle(e).aspectRatio, e.offsetHeight]));
  await page.unroute(/\/api\/movies\/\d+\/poster$/);
  for (const [ar] of posters) assert.equal(ar, "2 / 3");
  assert.deepEqual(posters, postersAfter, "poster box heights before and after the image settles");

  // the seat map
  const fx = await fixture(page);
  await open(page);
  const g = await page.evaluate(() => {
    const sc = document.querySelector(".fr-grid-scroll");
    const root = getComputedStyle(document.documentElement);
    const cell = getComputedStyle(document.querySelector('[role="grid"] .fr-seat'));
    const row = document.querySelector(".fr-grid-row");
    return { size: cell.width, gap: getComputedStyle(row).columnGap, tokSize: root.getPropertyValue("--fr-seat-size").trim(),
      tokGap: root.getPropertyValue("--fr-seat-gap").trim(), scrollLeft: sc.scrollLeft, client: sc.clientWidth, scroll: sc.scrollWidth,
      spi: getComputedStyle(sc).scrollPaddingInlineStart, gutter: root.getPropertyValue("--fr-seat-gutter").trim(),
      cols: getComputedStyle(document.querySelector('[role="grid"]')).getPropertyValue("--fr-grid-cols") };
  });
  assert.equal(g.size, "24px");
  assert.equal(g.gap, "4px");
  assert.equal(g.scrollLeft, 0, "first paint: scrollLeft 0");
  assert.equal(g.spi, g.gutter, "scroll-padding-inline-start = --fr-seat-gutter");
  const strip = g.client - 28;
  const cols = Number(g.cols);
  const rowWidth = cols * 28 - 4;
  await page.screenshot({ path: EV + "sea_xct39_375.png", fullPage: true });
  // The AC's literal geometry assumes a 20-column hall in a 375 - 32 - 32 - 28 = 283px strip.
  const geometry = { strip, visible: Math.floor((strip + 4) / 28), cols, rowWidth, hidden: rowWidth - strip };
  // minimum movement: in a row with seats at gc 1..n, ArrowRight from the last fully visible seat to the next
  const row = MAP.seats.filter((s) => s.gr === MAP.seats[0].gr).sort((a, b) => a.gc - b.gc);
  await page.locator(seatSel(row[0])).focus();
  let moved = null;
  for (let i = 1; i < row.length; i++) {
    const before = await page.$eval(".fr-grid-scroll", (e) => e.scrollLeft);
    await page.keyboard.press("ArrowRight");
    await page.waitForTimeout(250);
    const after = await page.$eval(".fr-grid-scroll", (e) => e.scrollLeft);
    if (after !== before) {
      const r = await page.evaluate((sel) => {
        const sc = document.querySelector(".fr-grid-scroll").getBoundingClientRect();
        const c = document.querySelector(sel).getBoundingClientRect();
        return { cellRight: c.right, boxRight: sc.right, bodyLeft: document.body.scrollLeft, transition: getComputedStyle(document.querySelector(".fr-grid-scroll")).scrollBehavior };
      }, seatSel(row[i]));
      moved = { delta: after - before, ...r };
      break;
    }
  }
  assert.ok(moved, "focus leaving the strip scrolls the container");
  assert.ok(Math.abs(moved.cellRight - moved.boxRight) <= 1, `minimum movement: the cell's right edge rests on the box's (${JSON.stringify(moved)})`);
  assert.equal(moved.bodyLeft, 0);
  // a poll leaves scrollLeft alone
  const sl = await page.$eval(".fr-grid-scroll", (e) => e.scrollLeft);
  const n = fx.calls();
  await page.waitForFunction(() => true);
  while (fx.calls() === n) await page.waitForTimeout(200);
  await page.waitForTimeout(200);
  assert.equal(await page.$eval(".fr-grid-scroll", (e) => e.scrollLeft), sl, "poll keeps scrollLeft");
  // the literal numbers, last: they are the AC's 20-column / 283px assumption
  await ctx.close();

  // a restored selection, and a 409's first named seat, scroll the map's own box by the minimum movement
  const far = avail().sort((x, y) => y.gc - x.gc)[0]; // the right-most free seat: off the 375px strip
  const rests = (pg, seat) => pg.evaluate((sel) => {
    const sc = document.querySelector(".fr-grid-scroll");
    const b = sc.getBoundingClientRect();
    const c = document.querySelector(sel).getBoundingClientRect();
    return { scrollLeft: sc.scrollLeft, gap: Math.abs(c.right - (b.left + sc.clientLeft + sc.clientWidth)), bodyLeft: document.scrollingElement.scrollLeft };
  }, seatSel(seat));
  await t.test("a restored selection scrolls to the first restored seat (minimum movement)", async () => {
    const { ctx: c2, page: p2 } = await guest({ width: 375, height: 800 }, { hasTouch: true, isMobile: true });
    await p2.goto(BASE + "/films");
    await p2.evaluate(([st, id]) => sessionStorage.setItem("fr.selection", JSON.stringify({ showtime_id: st, seat_ids: [id] })), [ST, far.id]);
    await open(p2);
    await p2.waitForTimeout(300);
    const r = await rests(p2, far);
    await c2.close();
    assert.ok(r.scrollLeft > 0, JSON.stringify(r));
    assert.ok(r.gap <= 1, `the restored seat's right edge rests on the box's: ${JSON.stringify(r)}`);
    assert.equal(r.bodyLeft, 0);
  });
  await t.test("a 409 carrying details.unavailable_seats scrolls to the first named seat (minimum movement)", async () => {
    const me = await signedIn(browser, "e2e-brw-1@example.com", undefined, { width: 375, height: 800 });
    await me.page.route(/\/api\/showtimes\/\d+\/holds$/, (route) => route.fulfill({ status: 409, json: { error: {
      code: "SEAT_UNAVAILABLE", message: `${far.row}${far.num} was taken by another customer. No seats were held. Choose a different seat and press Hold these seats again.`,
      details: { unavailable_seats: [`${far.row}${far.num}`] }, request_id: "e2e" } } }));
    await open(me.page);
    const first = avail().sort((x, y) => x.gc - y.gc)[0];
    await me.page.locator(seatSel(first)).click();
    await me.page.locator(".fr-grid-scroll").evaluate((e) => (e.scrollLeft = 0));
    await me.page.getByRole("button", { name: /^Hold/ }).click();
    await me.page.locator('.fr-banners [role="alert"]').waitFor();
    await me.page.waitForTimeout(300);
    const r = await rests(me.page, far);
    await me.ctx.close();
    assert.ok(r.scrollLeft > 0, JSON.stringify(r));
    assert.ok(r.gap <= 1, `the named seat's right edge rests on the box's: ${JSON.stringify(r)}`);
    assert.equal(r.bodyLeft, 0);
  });
  await t.test(`AC literal geometry (rendered: ${JSON.stringify(geometry)})`, () =>
    assert.deepEqual(geometry, { strip: 283, visible: 10, cols: 20, rowWidth: 556, hidden: 273 }));
  await t.test(`the AC's +21 scroll (rendered: +${moved.delta})`, () => assert.equal(moved.delta, 21));
});

// ---- S-SEA-01 -----------------------------------------------------------------------------------------------------
test("S-SEA-01 computed fill/border per state, the inactive treatment, the arrow grid and one tab stop", async (t) => {
  for (const width of [375, 1440]) await t.test(`${width}px`, async () => {
  const [a, h, m] = avail();
  const sold = MAP.seats.find((s) => s.state === "sold");
  const inactive = avail().find((s, i) => i > 2 && MAP.seats.some((o) => o.gr === s.gr && o.gc < s.gc)); // has a seat to its left
  const { ctx, page } = await guest({ width, height: 900 });
  await fixture(page, (mp) => ({ ...mp, seats: mp.seats.map((s) => (s.id === h.id ? { ...s, state: "held" } : s.id === inactive.id ? { ...s, is_active: false } : s)) }));
  await open(page);
  await page.locator(seatSel(m)).click();
  await page.waitForTimeout(400); // the background-color transition (--fr-motion-base) settles
  const props = ["backgroundColor", "borderTopStyle", "borderTopWidth", "borderTopColor"];
  const got = {
    available: await style(page, seatSel(a), props), sold: await style(page, seatSel(sold), props),
    held_by_other: await style(page, seatSel(h), props), held_by_me: await style(page, seatSel(m), props),
  };
  assert.equal(got.available.backgroundColor, await resolve(page, "--fr-seat-available"));
  assert.equal(got.sold.backgroundColor, await resolve(page, "--fr-seat-sold"));
  assert.equal(got.held_by_other.backgroundColor, await resolve(page, "--fr-seat-held-other"));
  assert.equal(got.held_by_other.borderTopStyle, "none", "held by someone else: no border");
  assert.equal(got.held_by_me.backgroundColor, await resolve(page, "--fr-seat-mine"));
  assert.equal(got.held_by_me.borderTopWidth, "2px");
  assert.equal(got.held_by_me.borderTopStyle, "solid");
  assert.equal(got.held_by_me.borderTopColor, await resolve(page, "--fr-seat-edge-mine", "color"));
  assert.equal(new Set(Object.values(got).map((g) => g.backgroundColor)).size, 4, "four distinct fills");
  assert.equal(await page.locator(seatSel(h)).getAttribute("aria-label").then((n) => n.endsWith("held by someone else")), true);
  // the held seat is not tappable
  await page.locator(seatSel(h)).click({ force: true });
  assert.deepEqual(await selIds(page), [m.id]);
  // inactive: no fill, 1px dashed --fr-rule, --fr-ink-muted number
  const off = await style(page, seatSel(inactive), [...props, "color"]);
  assert.equal(off.backgroundColor, "rgba(0, 0, 0, 0)");
  assert.equal(off.borderTopStyle, "dashed");
  assert.equal(off.borderTopWidth, "1px");
  assert.equal(off.borderTopColor, await resolve(page, "--fr-rule", "color"));
  assert.equal(off.color, await resolve(page, "--fr-ink-muted", "color"));
  // keeps its place in the arrow grid, and Enter/Space do nothing on it
  const rowSeats = MAP.seats.filter((s) => s.gr === inactive.gr).sort((x, y) => x.gc - y.gc);
  const leftOf = rowSeats[rowSeats.indexOf(rowSeats.find((s) => s.id === inactive.id)) - 1];
  await page.locator(seatSel(leftOf)).focus();
  await page.keyboard.press("ArrowRight");
  assert.equal(await page.evaluate(() => document.activeElement?.getAttribute("data-seat-id")), String(inactive.id));
  await page.keyboard.press("Enter");
  await page.keyboard.press(" ");
  assert.deepEqual(await selIds(page), [m.id]);
  // one tab stop in the map
  const tabbable = await page.$$eval('[role="grid"] [tabindex]:not([tabindex="-1"]), [role="grid"] button, [role="grid"] a[href]', (els) => els.length);
  assert.equal(tabbable, 1);
  await page.screenshot({ path: EV + `sea_01_states_${width}.png` });
  await ctx.close();
  });
});

// ---- S-SEA-02 -----------------------------------------------------------------------------------------------------
test("S-SEA-02 taps write fr.selection and send nothing; refusals change nothing; the cap; reload re-check; close sends nothing", async () => {
  const pool = avail();
  const held = pool[0], off = pool[1], chosen = pool.slice(2, 13);
  const sold = MAP.seats.find((s) => s.state === "sold");
  const { ctx, page } = await guest();
  await page.addInitScript(() => {
    window.__unloadListeners = 0;
    const add = EventTarget.prototype.addEventListener;
    EventTarget.prototype.addEventListener = function (type, ...rest) {
      // the Vite dev client's own beforeunload (/@vite/client, dev server only, not in the built app) is not ours
      if ((type === "unload" || type === "beforeunload" || type === "pagehide") && !/@vite\/client/.test(new Error().stack)) window.__unloadListeners++;
      return add.call(this, type, ...rest);
    };
  });
  const fx = await fixture(page, (m) => ({ ...m, seats: m.seats.map((s) => (s.id === held.id ? { ...s, state: "held" } : s.id === off.id ? { ...s, is_active: false } : s)) }));
  await open(page);
  const calls = spy(page);
  const c = chosen[0];
  await page.locator(seatSel(c)).click();
  assert.deepEqual(await selIds(page), [c.id]);
  assert.equal((await ss(page)).pending, null);
  await page.locator(seatSel(c)).click();
  assert.equal((await ss(page)).sel, null, "emptied: fr.selection deleted");
  assert.equal((await ss(page)).pending, null);
  for (const s of [sold, held, off]) {
    await page.locator(seatSel(s)).click({ force: true });
    assert.equal((await ss(page)).sel, null, `tap on ${s.id} changes nothing`);
    assert.equal((await ss(page)).pending, null);
  }
  for (const s of chosen.slice(0, 10)) await page.locator(seatSel(s)).click();
  const ten = await selIds(page);
  const drawn = () => gridSeats(page).evaluateAll((els) => els.map((e) => [e.dataset.visual, e.dataset.glyph, e.getAttribute("aria-label")].join("|")).join(";"));
  const html = await drawn();
  await page.locator(seatSel(chosen[10])).click();
  assert.deepEqual(await selIds(page), ten, "eleventh refused");
  assert.equal(await drawn(), html, "the map does not change");
  assert.equal(await page.locator(".fr-cap-note").textContent(), `Up to ${MAP.max_seats_per_booking} seats.`);
  assert.equal((await ss(page)).pending, null);
  assert.deepEqual(calls, [], "taps send nothing");
  // reload: restored, then re-checked against the fresh map (one chosen seat has been sold meanwhile)
  fx.set((m) => ({ ...m, seats: m.seats.map((s) => (s.id === chosen[0].id ? { ...s, state: "sold" } : s)) }));
  await page.reload();
  await gridSeats(page).first().waitFor();
  await page.locator(".fr-banner").first().waitFor();
  assert.deepEqual(await selIds(page), ten.filter((id) => id !== chosen[0].id), "restored and re-checked");
  assert.equal(await page.locator(`${seatSel(chosen[1])}[data-visual="held_by_me"]`).count(), 1);
  assert.equal((await ss(page)).pending, null);
  // closing the tab with a selection and no hold
  assert.equal(await page.evaluate(() => window.__unloadListeners), 0, "no unload/beforeunload/pagehide listener");
  const late = [];
  ctx.on("request", (r) => late.push(r.url()));
  await page.close({ runBeforeUnload: true });
  await new Promise((r) => setTimeout(r, 500));
  assert.deepEqual(late, [], "closing sends nothing");
  for (const s of chosen) assert.equal(redis("EXISTS", `lock:seat:${ST}:${s.id}`), "0", `no lock for ${s.id}`);
  await ctx.close();

  // a selection becoming a hold deletes fr.selection (signed in, a real seat, released afterwards)
  const me = await signedIn(browser, "e2e-brw-1@example.com");
  await me.page.goto(`${BASE}/showtimes/${ST}`);
  await gridSeats(me.page).first().waitFor();
  const free = (await api(`/api/showtimes/${ST}/seatmap`)).seats.filter((s) => s.state === "available").at(-1);
  await me.page.locator(seatSel(free)).click();
  assert.deepEqual(await selIds(me.page), [free.id]);
  await me.page.getByRole("button", { name: /^Hold/ }).click();
  await me.page.locator(".fr-countdown").waitFor();
  assert.equal((await ss(me.page)).sel, null, "became a hold: fr.selection deleted");
  assert.equal((await ss(me.page)).pending, null);
  await me.page.getByRole("button", { name: "Give up these seats" }).click();
  await me.page.locator(".fr-countdown").waitFor({ state: "detached" });
  await me.ctx.close();
});

// ---- S-SEA-03 -----------------------------------------------------------------------------------------------------
test("S-SEA-03 the total renders in computed --fr-font-mono", async () => {
  const { ctx, page } = await guest();
  await open(page);
  const [a, b] = avail();
  await page.locator(seatSel(a)).click();
  await page.locator(seatSel(b)).click();
  const total = page.locator(".fr-total");
  const want = a.price_paise + b.price_paise;
  assert.equal(await total.textContent(), "$" + (want / 100).toLocaleString("en-US", { minimumFractionDigits: 2 }));
  assert.equal(await total.evaluate((e) => getComputedStyle(e).fontFamily), await resolve(page, "--fr-font-mono", "fontFamily"));
  await ctx.close();
});

// ---- S-SEA-04 -----------------------------------------------------------------------------------------------------
test("S-SEA-04 a chosen seat gone on a poll: one assertive insertion, Dismiss removes it, total drops, no request, focus stays visible", async () => {
  const [x, y, z] = avail();
  const { ctx, page } = await guest({ width: 375, height: 800 }, { hasTouch: true, isMobile: true });
  const fx = await fixture(page);
  await open(page);
  for (const s of [x, y, z]) await page.locator(seatSel(s)).click();
  const totalBefore = await page.locator(".fr-total").textContent();
  await page.evaluate(() => {
    window.__assertive = 0;
    new MutationObserver((recs) => {
      for (const r of recs) for (const n of r.addedNodes) {
        const host = n.nodeType === 1 ? n : n.parentElement;
        if (host?.closest?.('[aria-live="assertive"]') || host?.querySelector?.('[aria-live="assertive"]')) if (n.textContent) window.__assertive++;
      }
      for (const r of recs) if (r.type === "characterData" && r.target.parentElement?.closest('[aria-live="assertive"]')) window.__assertive++;
    }).observe(document.querySelector(".fr-banners"), { childList: true, subtree: true, characterData: true });
  });
  await page.locator(seatSel(z)).focus();
  const calls = spy(page);
  fx.set((m) => ({ ...m, seats: m.seats.map((s) => (s.id === x.id ? { ...s, state: "sold" } : s)) }));
  const banner = page.locator('.fr-banners [role="alert"]');
  await banner.waitFor();
  const label = `${x.row}${x.num}`;
  assert.equal(await banner.locator("p").textContent(), `${label} is no longer available. It has been removed from your choices.`);
  // let a further poll arrive: still one insertion
  const n = fx.calls();
  while (fx.calls() === n) await page.waitForTimeout(200);
  await page.waitForTimeout(200);
  assert.equal(await page.evaluate(() => window.__assertive), 1, "exactly one insertion into the assertive region");
  assert.deepEqual(await selIds(page), [y.id, z.id], "the seat left the selection");
  assert.equal(await page.locator(".fr-summary-line:not(.fr-summary-total)").count(), 2);
  const after = await page.locator(".fr-total").textContent();
  const cents = (t) => Math.round(Number(t.replace(/[$,]/g, "")) * 100);
  assert.equal(cents(totalBefore) - cents(after), x.price_paise, "total drops by that seat's price");
  assert.deepEqual(calls, [], "no request beyond the map fetch");
  // focused seat fully inside the viewport with the banner live
  await page.locator(seatSel(z)).focus();
  const inView = await page.$eval(seatSel(z), (e) => { const r = e.getBoundingClientRect(); return r.top >= 0 && r.left >= 0 && r.bottom <= innerHeight && r.right <= innerWidth; });
  await page.screenshot({ path: EV + "sea_04_gone_banner.png" });
  assert.ok(inView, "a focused seat cell is fully in the viewport with the banner live");
  const controls = banner.locator("button, a, [role=button]");
  assert.equal(await controls.count(), 1);
  assert.equal(await controls.getAttribute("aria-label"), "Dismiss this message");
  assert.equal(await controls.textContent(), "Dismiss");
  assert.equal(await banner.count(), 1);
  await controls.click();
  assert.equal(await banner.count(), 0, "Dismiss removes the banner");
  // two gone in one re-check: one banner
  fx.set((m) => ({ ...m, seats: m.seats.map((s) => (s.id === y.id || s.id === z.id || s.id === x.id ? { ...s, state: "sold" } : s)) }));
  await banner.waitFor();
  await page.waitForTimeout(300);
  assert.equal(await banner.count(), 1, "one banner for two seats");
  await ctx.close();
});

// ---- S-SEA-12 + the SEAT_UNAVAILABLE half of S-SEA-04 --------------------------------------------------------------
test("S-SEA-12 a seat lost at hold time repaints in computed --fr-seat-held-other with the bar; S-SEA-04 SEAT_UNAVAILABLE has no control", async () => {
  const me = await signedIn(browser, "e2e-brw-1@example.com");
  const other = await signedIn(browser, "e2e-brw-2@example.com");
  await me.page.clock.install();
  await me.page.goto(`${BASE}/showtimes/${ST}`);
  await gridSeats(me.page).first().waitFor();
  await me.page.clock.pauseAt(Date.now() + 500); // no poll until the 409 has been painted
  const live = (await api(`/api/showtimes/${ST}/seatmap`)).seats.filter((s) => s.state === "available");
  const [lost, kept, next] = live.slice(-3);
  await me.page.locator(seatSel(lost)).click();
  await me.page.locator(seatSel(kept)).click();
  const theirs = await other.page.evaluate(async ([st, id]) => {
    const r = await fetch(`/api/showtimes/${st}/holds`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ seat_ids: [id] }) });
    return { status: r.status, body: await r.json() };
  }, [ST, lost.id]);
  assert.equal(theirs.status, 201, JSON.stringify(theirs));
  try {
    await me.page.getByRole("button", { name: /^Hold/ }).click();
    const banner = me.page.locator('.fr-banners [role="alert"]');
    await banner.waitFor();
    assert.match(await banner.innerText(), new RegExp(`${lost.row}${lost.num} was taken by another customer`));
    const cell = me.page.locator(seatSel(lost));
    await me.page.waitForTimeout(400); // the background-color transition (--fr-motion-base) settles
    assert.equal(await cell.getAttribute("data-visual"), "held_by_other");
    assert.equal(await cell.getAttribute("data-glyph"), "bar");
    assert.ok((await cell.getAttribute("aria-label")).endsWith("held by someone else"));
    assert.equal(await cell.evaluate((e) => getComputedStyle(e).backgroundColor), await resolve(me.page, "--fr-seat-held-other"));
    assert.notEqual(await cell.evaluate((e) => getComputedStyle(e).backgroundColor), await resolve(me.page, "--fr-seat-sold"));
    assert.deepEqual(await selIds(me.page), [kept.id], "the other choice is still in fr.selection");
    await me.page.screenshot({ path: EV + "sea_12_taken.png" });
    // S-SEA-04: SEAT_UNAVAILABLE carries zero controls and clears on the next selection change
    assert.equal(await banner.locator("button, a, [role=button]").count(), 0);
    await me.page.locator(seatSel(next)).click();
    assert.equal(await banner.count(), 0, "cleared by the next selection change");
  } finally {
    await other.page.evaluate((t) => fetch(`/api/holds/${t}`, { method: "DELETE" }), theirs.body.hold_token);
    await me.ctx.close();
    await other.ctx.close();
  }
});

// ---- S-SEA-14 -----------------------------------------------------------------------------------------------------
test("S-SEA-14 one polite insertion at 1:00, urgent colours, sessionStorage only, resume after reload, close sends nothing", async () => {
  const me = await signedIn(browser, "e2e-brw-1@example.com");
  const { page, ctx } = me;
  await page.clock.install();
  await page.goto(`${BASE}/showtimes/${ST}`);
  await gridSeats(page).first().waitFor();
  const seat = (await api(`/api/showtimes/${ST}/seatmap`)).seats.filter((s) => s.state === "available").at(-4);
  await page.locator(seatSel(seat)).click();
  await page.getByRole("button", { name: /^Hold/ }).click();
  await page.locator(".fr-countdown").waitFor();
  const hold = JSON.parse((await ss(page)).hold);
  try {
    assert.equal(await page.evaluate(() => localStorage.length), 0, "localStorage.length 0");
    assert.equal(await page.locator(".fr-countdown-label").textContent(), "TIME LEFT");
    assert.equal(await page.$eval(".fr-countdown-digits", (e) => Boolean(e.closest("[aria-live]"))), false, "digits not in a live region");
    // reload: the server answers the same expires_at and the countdown resumes at the right remaining time
    await page.reload();
    await page.locator(".fr-countdown").waitFor();
    const again = await page.evaluate(async (t) => (await (await fetch(`/api/holds/${t}`)).json()).expires_at, hold.hold_token);
    assert.equal(again, hold.expires_at);
    await page.waitForTimeout(600);
    const shown = await page.locator(".fr-countdown-digits").textContent();
    const left = await page.evaluate((e) => Math.max(0, Math.ceil((Date.parse(e) - Date.now()) / 1000)), hold.expires_at);
    const secs = (t) => Number(t.split(":")[0]) * 60 + Number(t.split(":")[1]);
    assert.ok(Math.abs(secs(shown) - left) <= 1, `resumed at ${shown}, expected ~${left}s`);
    // jump the page's clock to 60.5s before expiry: one polite insertion, urgent colours
    await page.evaluate(() => {
      window.__polite = 0;
      const el = document.querySelector(".fr-countdown-line");
      new MutationObserver(() => { if (el.textContent) window.__polite++; }).observe(el, { childList: true, subtree: true, characterData: true });
    });
    const now = await page.evaluate(() => Date.now());
    await page.clock.fastForward(Date.parse(hold.expires_at) - 60_500 - now);
    await page.locator(".fr-countdown[data-urgent]").waitFor();
    await page.clock.fastForward(3000); // more ticks: still one insertion
    await page.waitForTimeout(300);
    assert.equal(await page.evaluate(() => window.__polite), 1, "exactly one insertion into the polite region");
    assert.equal(await page.locator(".fr-countdown-line").textContent(), "Less than a minute left. At 0:00 your seats are released and you will need to choose them again.");
    const urgent = await resolve(page, "--fr-countdown-urgent", "color");
    assert.equal(await page.$eval(".fr-countdown-digits", (e) => getComputedStyle(e).color), urgent);
    assert.equal(await page.$eval(".fr-countdown-bar", (e) => getComputedStyle(e).backgroundColor), urgent);
    await page.screenshot({ path: EV + "sea_14_urgent.png" });
    // closing the tab: no request, keys still there
    const keys = hold.seats.map((s) => `lock:seat:${ST}:${s.seat_id}`);
    const late = [];
    ctx.on("request", (r) => late.push(r.url()));
    await page.close({ runBeforeUnload: true });
    await new Promise((r) => setTimeout(r, 500));
    assert.deepEqual(late, [], "closing sends nothing");
    for (const k of keys) assert.equal(redis("EXISTS", k), "1", k);
  } finally {
    const p2 = await ctx.newPage();
    await p2.goto(BASE + "/films");
    await p2.evaluate((t) => fetch(`/api/holds/${t}`, { method: "DELETE" }), hold.hold_token);
    await ctx.close();
  }
});

// ---- S-SEA-21 -----------------------------------------------------------------------------------------------------
test("S-SEA-21 a sold seat renders computed --fr-seat-sold with the hatch and no border, and no banner", async () => {
  const { ctx, page } = await guest();
  await open(page);
  const sold = MAP.seats.find((s) => s.state === "sold");
  const st = await style(page, seatSel(sold), ["backgroundColor", "borderTopStyle", "borderTopWidth", "backgroundImage"]);
  assert.equal(st.backgroundColor, await resolve(page, "--fr-seat-sold"));
  assert.equal(st.borderTopStyle, "none");
  assert.match(st.backgroundImage, /repeating-linear-gradient/, "the hatch");
  assert.equal(await page.locator(seatSel(sold)).getAttribute("data-glyph"), "hatch");
  assert.ok((await page.locator(seatSel(sold)).getAttribute("aria-label")).endsWith("sold"));
  assert.equal(await page.locator('.fr-banners [role="alert"]').count(), 0);
  await ctx.close();
});

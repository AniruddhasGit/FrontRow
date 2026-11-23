// CR-011 F1-F7: a browser walkthrough of the browse-to-door flow, with screenshots (evidence/cr011/). Local stack + Vite.
//   node walk_cr011.mjs browse         - F1 sidebar, F2 filters (+ reload), F3 film page at 360/768/1440, an empty film
//   node walk_cr011.mjs door           - F5 door (mouse hover, keyboard), F6 walk-in to that exact showtime, reduced motion
//   node walk_cr011.mjs book           - F7 seat -> hold -> pay -> confirmation -> My bookings / All films, header Back
//   node walk_cr011.mjs review <film>  - F4 a verified viewer reviews; a second account marks it helpful once
// Local data only; the e2e accounts are the ones lib.mjs registers locally (never the demo logins).
import assert from "node:assert/strict";
import { BASE, launch, signedIn } from "./lib.mjs";

const EV = new URL("./evidence/cr011/", import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, "$1");
const [mode, arg] = process.argv.slice(2);
const browser = await launch();
const shot = (page, name, full = false) => page.screenshot({ path: EV + name, fullPage: full });
const say = (...a) => console.log("-", ...a);
const api = (page, path) => page.evaluate(async (p) => (await fetch(p)).json(), path);

/** A showing film with an open show on some date, and that date's first open show. */
async function filmWithShow(page) {
  for (const f of (await api(page, "/api/movies")).movies.filter((m) => !m.coming_soon)) {
    let day = (await api(page, `/api/showtimes?movie_id=${f.id}`));
    if (!day.showtimes.some((s) => !s.sales_closed) && day.next_date_with_showtimes) {
      day = await api(page, `/api/showtimes?movie_id=${f.id}&date=${day.next_date_with_showtimes}`);
    }
    const open = day.showtimes.find((s) => !s.sales_closed);
    if (open) return { film: f, date: day.date, show: open };
  }
  throw new Error("no open showtime in the local data");
}

if (mode === "browse") {
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  await page.goto(BASE + "/");
  await page.locator(".fr-rail-film").first().waitFor();
  const rail = await page.locator(".fr-rail-title").allInnerTexts();
  const films = (await api(page, "/api/movies")).movies.filter((m) => !m.coming_soon);
  const avg = (m) => (m.rating.count ? m.rating.average_tenths : -1);
  const want = films.sort((a, b) => avg(b) - avg(a) || b.rating.count - a.rating.count || a.title.localeCompare(b.title))
    .slice(0, 10).map((m) => m.title);
  assert.deepEqual(rail, want);
  say("F1 sidebar:", rail.length, "films in rating order; first", rail[0]);
  await shot(page, "f1-landing-sidebar-1440.png");
  await page.getByRole("button", { name: "All films" }).click();
  await page.waitForURL(/\/films/);
  await page.locator(".fr-card").first().waitFor();
  await page.waitForTimeout(1500);
  const total = await page.locator(".fr-card").count();
  say("F1 All films opened /films with", total, "cards");

  // F2: each filter narrows, combined they narrow further, the URL keeps them, a reload keeps them
  const cards = () => page.locator(".fr-card").count();
  await page.getByRole("searchbox", { name: "Title" }).fill("the");
  const byTitle = await cards();
  await page.getByRole("group", { name: "Genre" }).getByRole("button", { name: "Adventure" }).click();
  const byBoth = await cards();
  assert.ok(byTitle < total && byBoth <= byTitle && byBoth > 0, `${total} -> ${byTitle} -> ${byBoth}`);
  await page.getByRole("group", { name: "Language" }).count();
  say("F2 title 'the':", byTitle, "; + Adventure:", byBoth);
  await shot(page, "f2-films-filters-1440.png", true);
  await page.getByRole("group", { name: "Rating" }).getByRole("button", { name: "★ 7+" }).click();
  const rated = await cards();
  say("F2 + 7+ stars:", rated, "(only rated films can pass)");
  const url = page.url();
  assert.match(url, /q=the/);
  assert.match(url, /genre_id=\d+/);
  assert.match(url, /min_rating=7/);
  await page.reload();
  await page.locator(".fr-listing").waitFor();
  await page.waitForTimeout(800);
  assert.equal(await page.getByRole("searchbox", { name: "Title" }).inputValue(), "the");
  assert.equal(await cards(), rated);
  say("F2 reload kept", url.split("?")[1]);
  await page.getByRole("button", { name: "Clear filters" }).click();
  await page.waitForTimeout(500);
  assert.equal(await cards(), total);
  await page.setViewportSize({ width: 360, height: 800 });
  await shot(page, "f2-films-360-folded.png");
  await page.getByRole("button", { name: /^Filters/ }).click();
  await shot(page, "f2-films-360-open.png");
  say("F2 phone: filters fold behind the Filters button");

  // F3: the film page with shows, at three widths
  const { film, date } = await filmWithShow(page);
  for (const w of [360, 768, 1440]) {
    await page.setViewportSize({ width: w, height: 900 });
    await page.goto(`${BASE}/movies/${film.id}?date=${date}`);
    await page.locator(".fr-screen-card").first().waitFor();
    await page.getByRole("heading", { name: "Top reviews" }).waitFor();
    await page.waitForTimeout(600);
    await shot(page, `f3-film-${w}.png`, true);
  }
  const sections = await page.locator("main h2").allInnerTexts();
  say("F3 sections:", sections.filter((s) => !s.startsWith("Your show")).join(" | "));
  const soon = (await api(page, "/api/movies")).movies.find((m) => m.coming_soon);
  await page.goto(`${BASE}/movies/${soon.id}`);
  await page.getByRole("heading", { name: "Before it opens" }).waitFor();
  await shot(page, "f3-film-coming-soon-1440.png", true);
  say("F3 a film without shows:", soon.title, "-", (await page.locator(".fr-state").first().innerText()).split("\n")[0]);
}

if (mode === "door") {
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await ctx.newPage();
  await page.goto(BASE + "/films");
  const { film, date, show } = await filmWithShow(page);
  await page.goto(`${BASE}/movies/${film.id}?date=${date}`);
  await page.locator(".fr-screen-card").first().waitFor();
  await page.locator(`a.fr-time[href="/showtimes/${show.id}"]`).click();
  const door = page.getByRole("button", { name: new RegExp(`^Enter ${show.screen.name} for `) });
  await door.waitFor();
  assert.ok(await door.evaluate((b) => b === document.activeElement), "focus moved to the door");
  await page.waitForTimeout(700);
  await page.locator(".fr-movie-door").screenshot({ path: EV + "f5-door-focus.png" });
  await page.mouse.move(0, 0);
  await door.evaluate((b) => b.blur());
  await page.waitForTimeout(600);
  await page.locator(".fr-movie-door").screenshot({ path: EV + "f5-door.png" });
  await door.hover();
  await page.waitForTimeout(600);
  await page.locator(".fr-movie-door").screenshot({ path: EV + "f5-door-hover.png" });
  say("F5 door:", await door.getAttribute("aria-label"));
  await door.focus();
  await page.keyboard.press("Enter"); // keyboard opens it
  await page.waitForTimeout(450);
  await shot(page, "f6-door-opening.png");
  await page.waitForURL(new RegExp(`/showtimes/${show.id}$`), { timeout: 8000 });
  await page.locator(".fr-hall3d canvas").waitFor({ timeout: 10000 });
  for (const [ms, name] of [[300, "f6-walk-in-1.png"], [1400, "f6-walk-in-2.png"], [1400, "f6-walk-in-3.png"]]) {
    await page.waitForTimeout(ms);
    await shot(page, name);
  }
  await page.waitForTimeout(4000);
  await shot(page, "f6-walk-in-seats.png");
  assert.match(await page.locator("h1").first().innerText(), new RegExp(film.title.replace(/[()]/g, ".")));
  say("F6 walked in to /showtimes/" + show.id, "(", show.screen.name, show.starts_at.slice(11, 16), ")");
  await page.getByRole("button", { name: "Back", exact: true }).click();
  await page.waitForURL(new RegExp(`/movies/${film.id}`));
  await page.locator(".fr-door").waitFor();
  say("F7 header Back from the seats returned to the film page with the door still open:", page.url().split(BASE)[1]);
  await ctx.close();

  const reduced = await browser.newContext({ viewport: { width: 1440, height: 900 }, reducedMotion: "reduce" });
  const rp = await reduced.newPage();
  await rp.goto(`${BASE}/movies/${film.id}?date=${date}&show=${show.id}`);
  const t0 = Date.now();
  await rp.locator(".fr-door").click();
  await rp.waitForURL(new RegExp(`/showtimes/${show.id}$`), { timeout: 3000 });
  await rp.waitForTimeout(1500);
  await shot(rp, "f6-reduced-motion-seats.png");
  say("F6 reduced motion: straight to the seats in", Date.now() - t0, "ms");
  await reduced.close();
}

if (mode === "book") {
  const { page } = await signedIn(browser, "e2e-sweep-1@example.com");
  const { film, date, show } = await filmWithShow(page);
  await page.goto(`${BASE}/movies/${film.id}?date=${date}`);
  await page.locator(`a.fr-time[href="/showtimes/${show.id}"]`).click();
  await page.locator(".fr-door").click();
  await page.waitForURL(new RegExp(`/showtimes/${show.id}$`));
  const free = page.locator('[role="grid"] .fr-seat[aria-label$=", available"]');
  await free.first().waitFor();
  await free.last().click();
  await page.getByRole("button", { name: /^Hold (these seats|\d+ more seats?)$/ }).click();
  await page.getByRole("button", { name: "Continue to payment" }).click();
  await page.waitForURL(/\/checkout$/);
  await page.locator(".fr-checkout").waitFor();
  await shot(page, "f7-checkout.png");
  await page.getByRole("button", { name: "Back", exact: true }).click();
  await page.waitForURL(new RegExp(`/showtimes/${show.id}$`));
  say("F7 header Back from checkout -> seat map");
  await page.getByRole("button", { name: "Continue to payment" }).click();
  await page.waitForURL(/\/checkout$/);
  await page.locator(".fr-checkout .fr-action").click();
  await page.waitForURL(/\/bookings\/FR-/, { timeout: 20000 });
  await page.getByText("Your booking is confirmed.").waitFor();
  await page.waitForTimeout(1500); // the page transition settles
  await shot(page, "f7-confirmation.png", true);
  const ref = decodeURIComponent(page.url().split("/bookings/")[1]);
  say("F7 paid:", ref);
  await page.getByRole("link", { name: "My bookings" }).last().click();
  await page.waitForURL(/\/bookings$/);
  await page.getByText(ref).first().waitFor();
  await shot(page, "f7-my-bookings.png");
  say("F7 My bookings lists", ref);
  await page.goBack();
  await page.waitForURL(/\/bookings\/FR-/);
  await page.getByRole("link", { name: "Browse all films" }).click();
  await page.waitForURL(/\/films$/);
  say("F7 Browse all films -> /films");
}

if (mode === "ticket") { // re-shoot one confirmation: node walk_cr011.mjs ticket <reference>
  const { page } = await signedIn(browser, "e2e-sweep-1@example.com");
  await page.goto(`${BASE}/bookings/${arg}`);
  await page.getByText("Your booking is confirmed.").waitFor();
  await page.waitForTimeout(1500);
  await shot(page, "f7-confirmation.png", true);
}

if (mode === "review") {
  const film = Number(arg);
  const a = await signedIn(browser, "e2e-sweep-1@example.com");
  await a.page.goto(`${BASE}/movies/${film}`);
  await a.page.getByRole("button", { name: /Write a review|Edit your review/ }).click();
  await a.page.getByLabel(/^Your review/).fill("Sharp, tense and beautifully shot. The sound in the hall made the finale.");
  await a.page.getByRole("button", { name: "Post review" }).click();
  await a.page.locator(".fr-review-card").first().waitFor();
  assert.equal(await a.page.locator(".fr-review-card .fr-helpful").count(), 0, "no Helpful button on your own review");
  say("F4 review posted; the author sees no Helpful button on it");
  const b = await signedIn(browser, "e2e-sweep-2@example.com");
  await b.page.goto(`${BASE}/movies/${film}`);
  const helpful = b.page.locator(".fr-review-card .fr-helpful").first();
  await helpful.click();
  await b.page.getByRole("button", { name: /Helpful \(you\)/ }).first().waitFor();
  const twice = await b.page.evaluate(async (id) => (await fetch(`/api/me/reviews/${id}/helpful`, { method: "POST" })).json(),
    (await api(b.page, `/api/movies/${film}/reviews`)).items[0].id);
  assert.equal(twice.helpful, 1, "a second vote changes nothing");
  await b.page.locator(".fr-reviews").scrollIntoViewIfNeeded();
  await b.page.locator(".fr-reviews").screenshot({ path: EV + "f4-reviews.png" });
  say("F4 second account voted once; a repeat POST still counts", twice.helpful);
  const stranger = await b.page.evaluate(async (f) => (await fetch(`/api/me/reviews/${f}`, { method: "PUT",
    headers: { "content-type": "application/json" }, body: JSON.stringify({ score: 9, text: "Never saw it." }) })).status, film);
  assert.equal(stranger, 403);
  say("F4 a non-viewer posting a review gets", stranger);
}

await browser.close();

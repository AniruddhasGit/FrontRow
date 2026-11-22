// CR-008 T9-T13, T16: a browser walkthrough with screenshots (evidence/cr008/). Local stack + Vite on :5173.
//   node walk_cr008_discovery.mjs book <showtime_id>   - search, film page, like, seat map fit/zoom, a booking, calendar, share
//   node walk_cr008_discovery.mjs ticket <reference>   - the confirmation's calendar and share only
//   node walk_cr008_discovery.mjs rate <movie_id>      - after that show has started: rate it and see the count change
// Local data only. The booking is confirmed through the product's own API from the page (the checkout is not in scope).
import assert from "node:assert/strict";
import { launch, signedIn, BASE } from "./lib.mjs";

const EV = new URL("./evidence/cr008/", import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, "$1");
const CUSTOMER = "e2e-sweep-1@example.com";
const [mode, arg] = process.argv.slice(2);
const browser = await launch();
const shot = (page, name, full = false) => page.screenshot({ path: EV + name, fullPage: full });
const say = (...a) => console.log("-", ...a);

if (mode === "book") {
  // guest: search as you type, keyboard, Enter opens the film
  const guest = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  await guest.goto(BASE + "/films");
  const box = guest.getByRole("combobox", { name: "Search films by title or genre" });
  await box.fill("thri");
  await guest.getByRole("option").first().waitFor();
  const options = await guest.getByRole("option").allInnerTexts();
  say("search 'thri':", options.length, "options;", options[0].split("\n")[0]);
  await box.press("ArrowDown");
  await box.press("ArrowDown");
  assert.equal(await guest.getByRole("option", { selected: true }).count(), 1);
  await shot(guest, "t9-search-open.png");
  const chosen = (await guest.getByRole("option", { selected: true }).innerText()).split("\n")[0];
  await box.press("Enter");
  await guest.waitForURL(/\/movies\/\d+/);
  await guest.getByRole("heading", { name: "About the film" }).waitFor();
  assert.equal(await guest.getByRole("heading", { level: 1 }).innerText(), chosen);
  say("Enter opened", chosen, guest.url());
  await box.fill("zzqx");
  await guest.getByText('No films match "zzqx".').waitFor();
  say("no-results state shown");
  await box.press("Escape");
  await shot(guest, "t12-film-page-guest.png", true);
  // /films and the film page: the week grid at 360
  await guest.setViewportSize({ width: 360, height: 800 });
  await guest.goto(BASE + "/films");
  await guest.locator(".fr-card").first().waitFor();
  await shot(guest, "t16-films-360.png");
  await guest.goto(BASE + "/");
  await guest.locator(".fr-discover").waitFor();
  await shot(guest, "t10-landing-360.png", true);
  await guest.close();

  const { ctx, page } = await signedIn(browser, CUSTOMER);
  // like a coming-soon film
  const films = (await (await fetch(BASE + "/api/movies")).json()).movies;
  const soon = films.find((f) => f.coming_soon);
  await page.goto(BASE + `/movies/${soon.id}`);
  const like = page.getByRole("button", { name: /^(Like|Liked)$/ });
  await like.waitFor();
  if ((await like.getAttribute("aria-pressed")) === "true") await like.click();
  const before = Number(await page.locator(".fr-ratings-big").innerText());
  await like.click();
  await page.getByRole("button", { name: "Liked" }).waitFor();
  const after = Number(await page.locator(".fr-ratings-big").innerText());
  say(`like ${soon.title}: ${before} -> ${after}`);
  assert.equal(after, before + 1);
  await shot(page, "t12-like-coming-soon.png", true);

  // the seat map fits: desktop panel, then a phone's overview and a zoomed block
  const st = Number(arg);
  await page.goto(BASE + `/showtimes/${st}`);
  await page.locator('[role="grid"] .fr-seat').first().waitFor();
  await page.waitForTimeout(1500);
  await shot(page, "t16-seatmap-1440.png");
  const phone = await ctx.newPage();
  await phone.setViewportSize({ width: 360, height: 800 });
  const touch = await browser.newContext({ viewport: { width: 360, height: 800 }, hasTouch: true, isMobile: true,
                                           storageState: await ctx.storageState() });
  const tp = await touch.newPage();
  await phone.close();
  await tp.goto(BASE + `/showtimes/${st}`);
  await tp.locator(".fr-grid-box").waitFor();
  await tp.waitForTimeout(1500);
  const fit = await tp.locator(".fr-grid-box").getAttribute("data-fit");
  say("phone map:", fit);
  await tp.locator(".fr-grid-box").scrollIntoViewIfNeeded();
  await shot(tp, "t16-seatmap-360-overview.png");
  if (fit === "overview") await tp.getByRole("group", { name: "Choose a block of seats" }).getByRole("button").nth(1).tap();
  await tp.locator('[role="grid"] .fr-seat').first().waitFor();
  const size = await tp.locator('[role="grid"] .fr-seat').first().boundingBox();
  say("zoomed seat size", Math.round(size.width), "px");
  await shot(tp, "t16-seatmap-360-zoomed.png");
  // tap an available seat in the zoomed block, hold it through the page, then confirm through the API
  await tp.locator('[role="grid"] .fr-seat[data-visual="available"]').first().tap();
  await tp.getByRole("button", { name: /^Hold/ }).tap();
  await tp.getByText(/held by you/).waitFor();
  const hold = await tp.evaluate(() => JSON.parse(sessionStorage.getItem("fr.hold")));
  const ref = await tp.evaluate(async (h) => {
    const r = await fetch("/api/bookings", { method: "POST", headers: { "content-type": "application/json", "Idempotency-Key": crypto.randomUUID() },
      body: JSON.stringify({ hold_token: h.hold_token, showtime_id: h.showtime_id }) });
    return (await r.json()).booking_reference;
  }, hold);
  say("booked", ref);
  await touch.close();
  await ticket(page, ctx, ref);
  await ctx.close();
}

/** T13b/c on the confirmation: the calendar file's times, then Share's copy path. */
async function ticket(page, ctx, ref) {
  await page.goto(BASE + `/bookings/${ref}`);
  const cal = page.getByRole("link", { name: /Add to calendar/ });
  await cal.waitFor();
  const ics = decodeURIComponent((await cal.getAttribute("href")).split(",").slice(1).join(","));
  say("calendar:", ics.split("\r\n").filter((l) => /^(DTSTART|DTEND|SUMMARY)/.test(l)).join(" | "));
  // headless Chromium has a share sheet that never answers: take the copy path the way a browser without Web Share does
  await page.evaluate(() => { Object.defineProperty(navigator, "share", { value: undefined }); });
  await ctx.grantPermissions(["clipboard-read", "clipboard-write"], { origin: BASE });
  await page.getByRole("button", { name: "Share" }).click();
  await page.getByRole("status").filter({ hasText: /Link copied|Copy this link/ }).waitFor();
  say("share:", await page.getByRole("status").filter({ hasText: /Link copied|Copy this link/ }).innerText());
  await shot(page, "t13-confirmation-calendar-share.png", true);
}

if (mode === "ticket") {
  const { ctx, page } = await signedIn(browser, CUSTOMER);
  await ticket(page, ctx, arg);
  await ctx.close();
}

if (mode === "rate") {
  const { ctx, page } = await signedIn(browser, CUSTOMER);
  await page.goto(BASE + `/movies/${arg}`);
  await page.getByRole("group", { name: "Rate this film from 1 to 10" }).waitFor();
  const count = async () => (await (await fetch(BASE + `/api/movies/${arg}`)).json()).rating.count;
  const before = await count();
  await page.getByRole("button", { name: "8 out of 10" }).click();
  await page.getByText("You gave it 8.").waitFor();
  const after = await count();
  say(`rating count ${before} -> ${after}`);
  await shot(page, "t12-rated.png", true);
  // a non-viewer is refused by the server
  const { ctx: c2, page: p2 } = await signedIn(browser, "e2e-sweep-2@example.com");
  const status = await p2.evaluate(async (id) => (await fetch(`/api/me/ratings/${id}`, { method: "PUT", headers: { "content-type": "application/json" },
    body: JSON.stringify({ score: 3 }) })).status, arg);
  say("non-viewer rating:", status);
  await p2.goto(BASE + `/movies/${arg}`);
  await p2.getByText("You can rate this film once a show of it that you booked has started.").waitFor();
  await c2.close();
  await page.goto(BASE + "/films");
  await page.locator(".fr-card").first().waitFor();
  await shot(page, "t12-films-stars.png");
  await page.goto(BASE + "/");
  await page.locator("#top-rated").waitFor();
  await page.locator("#top-rated").scrollIntoViewIfNeeded();
  await shot(page, "t10-top-rated.png");
  await ctx.close();
}
await browser.close();

// CR-008 T16 (owner, 2026-11-22: "no horizontal scroll through out the entire app"): every route, as a guest, a
// customer and an admin, at 360, 768 and 1440 px. A page fails when the document is wider than the window, or when any
// element that can scroll sideways (overflow-x auto or scroll) has more content than width. The open search list and the
// account sidebar are checked too. Run: cd e2e && node --test checks/no_sideways.test.mjs   (local stack + Vite :5173)
import { test, before, after } from "node:test";
import assert from "node:assert/strict";
import { execSync } from "node:child_process";
import { launch, signedIn, openShowtime, BASE } from "../lib.mjs";

const WIDTHS = [360, 768, 1440];
const CUSTOMER = "e2e-sweep-1@example.com";
const ADMIN = "e2e-adm-1@example.com";
const sql = (q) => execSync(`docker exec frontrow-postgres-1 psql -U frontrow -d frontrow -At -c "${q}"`).toString().trim();
let browser, ids;

/** Every sideways overflow on the page: the document itself, then each element allowed to scroll sideways. */
const sideways = (page) => page.evaluate(() => {
  const out = [];
  const doc = document.documentElement;
  if (doc.scrollWidth > window.innerWidth) out.push(`document ${doc.scrollWidth} > ${window.innerWidth}`);
  for (const el of document.querySelectorAll("body *")) {
    const x = getComputedStyle(el).overflowX;
    if ((x === "auto" || x === "scroll") && el.scrollWidth > el.clientWidth + 1) {
      const name = el.tagName.toLowerCase() + (el.id ? `#${el.id}` : "") + (el.className && typeof el.className === "string" ? `.${el.className.trim().split(/\s+/).join(".")}` : "");
      out.push(`${name} ${el.scrollWidth} > ${el.clientWidth}`);
    }
  }
  return out;
});

async function sweep(ctx, paths, who) {
  const found = [];
  const page = await ctx.newPage();
  for (const width of WIDTHS) {
    await page.setViewportSize({ width, height: 900 });
    for (const p of paths) {
      await page.goto(BASE + p, { waitUntil: "load" });
      await page.waitForTimeout(1200); // the page's first reads and layout settle (a fixed wait in a check, not the app)
      for (const f of await sideways(page)) found.push(`${who} ${width}px ${p}: ${f}`);
    }
    // the open search list, over the listing
    await page.goto(BASE + "/films", { waitUntil: "load" });
    await page.getByRole("combobox", { name: "Search films by title or genre" }).fill("th");
    await page.waitForTimeout(800);
    for (const f of await sideways(page)) found.push(`${who} ${width}px search open: ${f}`);
    // the account sidebar, open
    await page.keyboard.press("Escape");
    const menu = page.locator(".fr-menu-button, button[aria-haspopup='dialog']").first();
    if (await menu.count()) {
      await menu.click();
      await page.waitForTimeout(400);
      for (const f of await sideways(page)) found.push(`${who} ${width}px sidebar open: ${f}`);
    }
  }
  await page.close();
  return found;
}

before(async () => {
  browser = await launch();
  ids = await (await fetch(BASE + "/api/movies")).json().then((b) => ({
    film: b.movies.find((m) => !m.coming_soon)?.id, soon: b.movies.find((m) => m.coming_soon)?.id ?? b.movies[0].id,
  }));
});
after(() => browser?.close());

const PUBLIC = () => ["/", "/films", "/films#coming-soon", `/movies/${ids.film}`, `/movies/${ids.soon}`, "/sign-in", "/register",
  "/account/reset", "/help", "/no-such-page"];

test("guest: no route scrolls sideways at 360, 768 or 1440 px", async () => {
  const ctx = await browser.newContext();
  const page = await ctx.newPage();
  await page.goto(BASE + "/films");
  const st = await openShowtime(page);
  await page.close();
  const found = await sweep(ctx, [...PUBLIC(), `/showtimes/${st}`], "guest");
  await ctx.close();
  assert.deepEqual(found, []);
});

test("customer: no route scrolls sideways at 360, 768 or 1440 px", async () => {
  const { ctx, page } = await signedIn(browser, CUSTOMER);
  const st = await openShowtime(page);
  const ref = await page.evaluate(async () => (await (await fetch("/api/me/bookings")).json()).items?.[0]?.reference ?? null);
  await page.close();
  const paths = [...PUBLIC(), `/showtimes/${st}`, `/showtimes/${st}/checkout`, "/bookings", "/account/rewards", "/account/wishlist",
    "/account/notifications", "/account/profile", ...(ref ? [`/bookings/${ref}`] : [])];
  const found = await sweep(ctx, paths, "customer");
  await ctx.close();
  assert.deepEqual(found, []);
});

test("admin: no route scrolls sideways at 360, 768 or 1440 px", async () => {
  sql(`UPDATE users SET role='admin' WHERE email='${ADMIN}'`); // local data only (dashboard_admin.test.mjs makes the same account)
  const { ctx, page } = await signedIn(browser, ADMIN);
  assert.equal(await page.evaluate(async () => (await (await fetch("/api/auth/me")).json()).role), "admin");
  await page.close();
  const paths = ["/admin", "/admin/movies", "/admin/movies/new", `/admin/movies/${ids.film}`, "/admin/lookups", "/admin/venue",
    "/admin/halls", "/admin/seat-categories", "/admin/showtimes", "/admin/managers", "/admin/access", "/dashboard", "/dashboard/audit"];
  const found = await sweep(ctx, paths, "admin");
  await ctx.close();
  assert.deepEqual(found, []);
});

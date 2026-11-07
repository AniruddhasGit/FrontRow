// Shared helpers for the real-browser checks (e2e/checks/*.test.mjs). Run: cd e2e && npm run check
// Needs the local stack: docker compose (api, worker, postgres, redis, elasticmq) and Vite on :5173.
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { chromium } from "playwright";

export const BASE = process.env.FR_BASE ?? "http://localhost:5173";

/** The Chromium build already on this machine (ms-playwright); FR_CHROME overrides it. */
export function launch() {
  const exe = process.env.FR_CHROME ?? path.join(process.env.LOCALAPPDATA ?? "", "ms-playwright/chromium-1248/chrome-win64/chrome.exe");
  return chromium.launch({ executablePath: exe });
}

/** A signed-in page. The session is kept per address (OS temp), so a run signs in once per account and never trips
 *  the product's own sign-in limits (10 per account, 30 per address in 15 minutes); it registers on first use. */
export async function signedIn(browser, email, password = "e2e-check-password-123", viewport = { width: 1440, height: 900 }) {
  const file = path.join(os.tmpdir(), `frontrow-e2e-${email}.json`);
  let ctx = await browser.newContext({ viewport, storageState: fs.existsSync(file) ? file : undefined });
  let page = await ctx.newPage();
  await page.goto(BASE + "/films");
  const ok = await page.evaluate(async () => (await fetch("/api/auth/me", { credentials: "same-origin" })).ok);
  if (!ok) {
    const status = await page.evaluate(async ([e, p]) => {
      const body = JSON.stringify({ email: e, password: p });
      const h = { "content-type": "application/json" };
      const l = await fetch("/api/auth/login", { method: "POST", headers: h, body, credentials: "same-origin" });
      if (l.ok) return l.status;
      return (await fetch("/api/auth/register", { method: "POST", headers: h, body, credentials: "same-origin" })).status;
    }, [email, password]);
    if (status >= 400) throw new Error(`could not sign in ${email}: ${status} (a product rate limit? wait or clear rl:* in the LOCAL redis)`);
    await ctx.storageState({ path: file });
  }
  return { ctx, page };
}

/** Seat cells of the 2D map only (the legend swatches share the .fr-seat class). */
export const gridSeats = (page) => page.locator('[role="grid"] .fr-seat[aria-label]');

/** The first open showtime's id, from the public read path. */
export async function openShowtime(page) {
  return page.evaluate(async () => {
    const films = (await (await fetch("/api/movies")).json()).movies;
    for (const f of films) {
      const st = (await (await fetch(`/api/showtimes?movie_id=${f.id}`)).json()).showtimes ?? [];
      const open = st.find((s) => !s.sales_closed);
      if (open) return open.id;
    }
    return null;
  });
}

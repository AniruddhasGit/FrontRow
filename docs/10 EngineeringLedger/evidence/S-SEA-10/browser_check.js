// S-SEA-10, REAL mode: run through the Playwright MCP's browser_run_code against `npx vite --port 5199` (this branch's
// frontend, /api proxied to the local compose API on :8000), while redis_keys.sh polls KEYS lock:seat:367:* once a
// second. The running API was main's, built before CR-002 C-1, so the seat-map response is patched with
// max_seats_per_booking = 10 (this branch's API adds it; tests/sea/test_s_sea_09.py). Nothing else is mocked.
async (page) => {
  const ctx = await page.context().browser().newContext();
  const p = await ctx.newPage();
  const log = [];
  const t = () => new Date().toISOString().slice(11, 19);
  const marks = [];
  p.on("request", (r) => { if (r.url().includes("/api/")) log.push(`${t()} ${r.method()} ${new URL(r.url()).pathname}`); });
  await p.route("**/api/showtimes/367/seatmap", async (route) => {
    const resp = await route.fetch();
    const body = await resp.json();
    body.max_seats_per_booking = 10;
    await route.fulfill({ response: resp, json: body });
  });
  await p.goto("http://localhost:5199/showtimes/367");
  await p.locator('[role="gridcell"]').first().waitFor();
  const cells = await p.$$eval('[role="gridcell"]', (cs) => cs.map((c) => [c.dataset.seatId, c.dataset.visual, c.getAttribute("aria-disabled")]));
  const free = cells.filter((c) => c[1] === "available" && c[2] === "false").slice(-2).map((c) => c[0]);
  for (const id of free) await p.locator(`[role="gridcell"][data-seat-id="${id}"]`).click();
  marks.push(`${t()} guest pressing "${await p.locator(".fr-summary .fr-action").first().textContent()}"`);
  await p.locator(".fr-summary .fr-action").first().click();
  await p.waitForURL(/\/sign-in/);
  await p.getByRole("tab", { name: "Register" }).click();
  await p.fill("#fr-email", `sea10-${Date.now()}@example.com`);
  await p.fill("#fr-password", "a long enough password");
  await p.locator("form button[type=submit]").click();
  await p.waitForURL((u) => u.pathname === "/showtimes/367", { timeout: 15000 });
  marks.push(`${t()} returned from register`);
  await p.waitForTimeout(15000);
  const mine = await p.$$eval('[role="gridcell"][data-visual="held_by_me"]', (cs) => cs.map((c) => c.dataset.seatId));
  const label = await p.locator(".fr-summary .fr-action").first().textContent();
  marks.push(`${t()} restored ${mine}; pressing "${label}"`);
  await p.locator(".fr-summary .fr-action").first().click();
  await p.getByRole("button", { name: "Give up these seats" }).waitFor({ timeout: 10000 });
  marks.push(`${t()} hold granted`);
  await p.waitForTimeout(8000);
  await p.getByRole("button", { name: "Give up these seats" }).click();
  await p.waitForTimeout(3000);
  marks.push(`${t()} gave the seats back`);
  await ctx.close();
  return JSON.stringify({ free, marks, holds: log.filter((l) => l.includes("/holds")) }, null, 1);
}
// Result (2026-11-06 UTC = 2026-11-07 IST):
// marks: 21:39:54 guest pressing "Sign in to hold these seats" | 21:39:56 returned from register |
//        21:40:11 restored 89,90; pressing "Hold these seats" | 21:40:12 hold granted | 21:40:23 gave the seats back
// holds: 21:40:11 POST /api/showtimes/367/holds | 21:40:20 DELETE /api/holds/<token>   (no other /holds request)
// redis_keys_2026-11-06.log: [ ] on every poll 21:39:43..21:40:11, then lock:seat:367:89 and :90 from 21:40:12, [ ] from 21:40:20.

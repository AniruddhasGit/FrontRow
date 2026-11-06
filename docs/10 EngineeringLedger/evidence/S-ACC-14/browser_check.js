// S-ACC-14, MOCK mode (handoffs/round4/browser_checks.md S-ACC-14): run through the Playwright MCP's browser_run_code
// against `npx vite --port 5199` on this branch. Every /api call is fulfilled by page.route; the browser clock is fixed
// at 2026-08-14T10:00:00Z before load (10:30:01Z at sign-in for the stale case). Result 2026-11-07: 32/32 PASS.
// (A first run read 30/32: the stale and throwing-storage probes counted the legend's held_by_me swatch; the probe was
// narrowed to [role=gridcell]; no product code changed between the two runs.)
async (page) => {
  const BASE = "http://localhost:5199";
  const browser = page.context().browser();
  const out = [];
  const ok = (cond, what) => { out.push(`${cond ? "PASS" : "FAIL"} ${what}`); };

  const seat = (id, num, state = "available") => ({ id, row: "C", num, gr: 3, gc: num, cat: 1, price_paise: 28124, state, is_active: true });
  const map = (states = {}) => ({
    showtime: { id: 412, starts_at: "2026-08-14T19:30:00+05:30", sales_close_at: "2026-08-14T19:45:00+05:30", sales_closed: false },
    screen: { id: 1, name: "Hall 1", rows: 3, cols: 16 }, categories: [{ id: 1, name: "Premium", price_paise: 28124 }],
    seats: [10, 11, 12, 13, 14, 15].map((n) => seat(1175 + n, n, states[n] ?? "available")),
    generated_at: "2026-08-14T15:30:00+05:30", poll_interval_seconds: 3, max_seats_per_booking: 10,
  });

  async function scenario({ seats, exit, after = {}, clockAtSignIn = null, throwing = false, gone404 = false }) {
    const ctx = await browser.newContext();
    const p = await ctx.newPage();
    await p.clock.setFixedTime(new Date("2026-08-14T10:00:00Z"));
    await p.addInitScript((throwing) => {
      window.__seq = [];
      const set = Storage.prototype.setItem;
      Storage.prototype.setItem = function (k, v) { window.__seq.push(["set", k]); return set.call(this, k, v); };
      const push = history.pushState;
      history.pushState = function (s, t, u) { window.__seq.push(["push", String(u)]); return push.call(this, s, t, u); };
      const f = window.fetch;
      window.fetch = function (u, o) { window.__seq.push(["fetch", (o && o.method) || "GET", String(u)]); return f.call(this, u, o); };
      if (throwing) {
        Storage.prototype.getItem = function () { throw new Error("denied"); };
        Storage.prototype.setItem = function () { throw new Error("denied"); };
      }
    }, throwing);
    let signedIn = false, holds = 0, maps = 0;
    await p.route("**/api/**", async (route) => {
      const u = new URL(route.request().url()), m = route.request().method();
      const json = (status, body) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
      if (u.pathname === "/api/auth/me") return signedIn ? json(200, { email: "a@example.test", role: "customer" }) : json(401, { error: { code: "AUTH_REQUIRED", message: "", details: {} } });
      if (u.pathname === "/api/auth/login" && m === "POST") { signedIn = true; return json(200, {}); }
      if (u.pathname === "/api/showtimes/412/holds") { holds++; return json(500, {}); }
      if (u.pathname === "/api/showtimes/412/seatmap") {
        maps++;
        if (signedIn && gone404) return json(404, { error: { code: "NOT_FOUND", message: "", details: {} } });
        return json(200, signedIn ? map(after) : map());
      }
      if (u.pathname === "/api/showtimes/412") return json(200, { id: 412, movie: { id: 1, title: "The Long Night" }, screen: { name: "Hall 1" }, starts_at: "2026-08-14T19:30:00+05:30" });
      if (u.pathname === "/api/movies") return json(200, { count: 0, movies: [] });
      return json(404, { error: { code: "NOT_FOUND", message: "", details: {} } });
    });
    await p.goto(`${BASE}/showtimes/412`);
    await p.locator('[data-seat-id="1187"]').waitFor();
    for (const id of seats) await p.locator(`[data-seat-id="${id}"]`).click();
    const r = { p, ctx, holds: () => holds };
    if (!throwing) r.selection = await p.evaluate(() => sessionStorage.getItem("fr.selection"));
    if (exit === "primary") await p.getByRole("button", { name: "Sign in to hold these seats" }).click();
    else await p.locator("a.fr-signin").click();
    await p.waitForURL(/\/sign-in/);
    r.seq = await p.evaluate(() => window.__seq.slice());
    if (!throwing) {
      r.pending = await p.evaluate(() => sessionStorage.getItem("fr.pending_selection"));
      r.keys = await p.evaluate(() => Object.keys(sessionStorage));
    }
    r.note = await p.getByText("Your seats are still selected. Sign in to hold them.").count();
    if (clockAtSignIn) await p.clock.setFixedTime(new Date(clockAtSignIn));
    const mark = (await p.evaluate(() => window.__seq.length));
    await p.fill("#fr-email", "a@example.test");
    await p.fill("#fr-password", "correct horse battery");
    await p.locator("form button[type=submit]").click();
    await p.waitForURL((u) => u.pathname !== "/sign-in");
    if (gone404) {
      await p.waitForURL((u) => u.pathname === "/");
      await p.getByText("That showtime is no longer available.").waitFor({ timeout: 5000 }).catch(() => null);
      r.path = new URL(p.url()).pathname;
      r.goneText = await p.getByText("That showtime is no longer available.").count();
      return r;
    }
    await p.getByRole("button", { name: "Hold these seats" }).or(p.getByRole("button", { name: "Choose seats" })).waitFor();
    await p.waitForTimeout(500);
    r.path = new URL(p.url()).pathname;
    r.after = (await p.evaluate(() => window.__seq.slice())).slice(mark);
    r.names = await p.$$eval('[role="gridcell"]', (cs) => Object.fromEntries(cs.map((c) => [c.dataset.seatId, c.getAttribute("aria-label")])));
    r.banners = await p.$$eval(".fr-banner p", (ps) => ps.map((x) => x.textContent));
    if (!throwing) {
      r.pendingAfter = await p.evaluate(() => sessionStorage.getItem("fr.pending_selection"));
      r.selAfter = await p.evaluate(() => sessionStorage.getItem("fr.selection"));
    }
    r.primary = await p.locator(".fr-summary .fr-action").first().textContent();
    r.holdsAfterReturn = holds;
    return r;
  }

  const SEL = JSON.stringify({ showtime_id: 412, seat_ids: [1187, 1188], stored_at: "2026-08-14T10:00:00Z" });
  for (const exit of ["primary", "header"]) {
    // C12 sold, C13 held, C14 survives
    const a = await scenario({ seats: [1187, 1188, 1189], exit, after: { 12: "sold", 13: "held" } });
    const exact = await scenario({ seats: [1187, 1188], exit, after: { 12: "sold" } });
    const iSet = exact.seq.findIndex((e) => e[0] === "set" && e[1] === "fr.pending_selection");
    const iPush = exact.seq.findIndex((e) => e[0] === "push" && e[1].startsWith("/sign-in"));
    ok(iSet >= 0 && iSet < iPush, `${exit}: pending written (seq ${iSet}) before /sign-in pushed (seq ${iPush})`);
    ok(exact.pending === SEL, `${exit}: fr.pending_selection === ${exact.pending}`);
    ok(exact.keys.includes("fr.selection") && exact.keys.includes("fr.pending_selection"), `${exit}: both keys present: ${exact.keys.join(",")}`);
    ok(exact.note === 1, `${exit}: context note shown`);
    ok(a.path === "/showtimes/412", `${exit}: back on ${a.path}`);
    const iMap = a.after.findIndex((e) => e[0] === "fetch" && e[2].includes("/api/showtimes/412/seatmap"));
    const iSel = a.after.findIndex((e) => e[0] === "set" && e[1] === "fr.selection");
    ok(iMap >= 0 && iMap < iSel, `${exit}: GET seatmap (seq ${iMap}) before the restore's fr.selection write (seq ${iSel})`);
    ok(a.banners.includes("C12 and C13 were taken while you were signing in. Your other seats are still selected."), `${exit}: two-seat sentence: ${JSON.stringify(a.banners)}`);
    ok(a.names["1187"] === "Row C seat 12, Premium, sold" && a.names["1188"] === "Row C seat 13, Premium, held by someone else", `${exit}: names ${a.names["1187"]} / ${a.names["1188"]}`);
    ok(a.pendingAfter === null && a.selAfter === JSON.stringify({ showtime_id: 412, seat_ids: [1189] }), `${exit}: pending removed, fr.selection ${a.selAfter}`);
    ok(a.holdsAfterReturn === 0 && !a.after.some((e) => e[0] === "fetch" && e[2].includes("/holds")), `${exit}: zero POST holds after sign-in (${a.holdsAfterReturn})`);
    ok(a.primary === "Hold these seats", `${exit}: primary reads "${a.primary}"`);
    ok(a.seq.filter((e) => e[0] === "fetch" && e[2].includes("/holds")).length === 0, `${exit}: guest press sent no hold request`);
    ok(exact.banners.includes("C12 was taken while you were signing in. Your other seats are still selected."), `${exit}: one-seat sentence: ${JSON.stringify(exact.banners)}`);
    await a.ctx.close(); await exact.ctx.close();
  }
  const none = await scenario({ seats: [1187, 1188], exit: "primary", after: { 12: "sold", 13: "held" } });
  ok(none.banners.includes("The seats you chose were taken while you were signing in. Choose again from the map."), `none survive: ${JSON.stringify(none.banners)}`);
  ok(none.selAfter === null && none.pendingAfter === null, `none survive: no selection (${none.selAfter}), pending removed`);
  await none.ctx.close();
  const stale = await scenario({ seats: [1187, 1188], exit: "primary", clockAtSignIn: "2026-08-14T10:30:01Z" });
  const chosen = await stale.p.$$eval('[role="gridcell"][data-visual="held_by_me"]', (cs) => cs.length);
  ok(stale.path === "/showtimes/412" && chosen === 0 && stale.banners.length === 0 && stale.selAfter === null, `stale: map ${stale.path}, ${chosen} chosen, banners ${JSON.stringify(stale.banners)}`);
  await stale.ctx.close();
  const thr = await scenario({ seats: [1187, 1188], exit: "primary", throwing: true });
  const thrChosen = await thr.p.$$eval('[role="gridcell"][data-visual="held_by_me"]', (cs) => cs.length);
  ok(thr.path === "/showtimes/412" && thrChosen === 0 && thr.banners.length === 0 && thr.note === 0, `throwing storage: signed in, map ${thr.path}, ${thrChosen} chosen, no message, no note`);
  await thr.ctx.close();
  const gone = await scenario({ seats: [1187, 1188], exit: "primary", gone404: true });
  ok(gone.path === "/" && gone.goneText === 1, `missing showtime: ${gone.path}, sentence shown ${gone.goneText}`);
  // sign-out sweep
  const so = await scenario({ seats: [1187, 1188, 1189], exit: "header", after: {} });
  await so.p.route("**/api/auth/logout", (r) => r.fulfill({ status: 204, body: "" }));
  await so.p.getByRole("button", { name: "Sign out" }).click();
  await so.p.waitForURL((u) => u.pathname === "/");
  const left = await so.p.evaluate(() => Object.keys(sessionStorage).filter((k) => k.startsWith("fr.")).length);
  ok(left === 0, `sign-out: ${left} fr.* keys left`);
  await so.ctx.close();
  return out.join("\n");
}

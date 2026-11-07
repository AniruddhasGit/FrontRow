// Real-browser checks for the dashboard (SCR-RPT-01/02) and the admin edit forms (SCR-ADM-02..05, 08): the clauses
// the S-RPT-18..21, S-ADM-14, S-ADM-17 and S-ADM-19 StatusNotes list as open. Run: cd e2e && node --test checks/dashboard_admin.test.mjs
// Accounts are throwaway LOCAL ones (e2e-adm-<n>@example.com), promoted in the local Postgres. Fixtures the local data
// cannot produce (214 per-show rows, films_truncated, an audit period that drops an option) are served by page.route
// on top of the real API's own response shape; every other assertion runs against the live local API.
import { after, before, describe, test } from "node:test";
import assert from "node:assert/strict";
import { execSync } from "node:child_process";
import { existsSync, mkdirSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { BASE, launch } from "../lib.mjs";

const EVIDENCE = new URL("../evidence/", import.meta.url);
mkdirSync(EVIDENCE, { recursive: true });
const shot = (page, name) => page.screenshot({ path: new URL(name, EVIDENCE).pathname.replace(/^\/([A-Z]:)/, "$1"), fullPage: true });

const ADMIN = "e2e-adm-1@example.com";
const MANAGER = "e2e-adm-2@example.com"; // halls 3 and 5
const EMPTY = "e2e-adm-3@example.com"; // a manager with no hall: scope_empty
const sql = (q) => execSync(`docker exec frontrow-postgres-1 psql -U frontrow -d frontrow -At -c "${q}"`).toString().trim();

let browser;
const api = (page, method, path, body) => page.evaluate(async ([m, p, b]) => {
  const r = await fetch(p, { method: m, credentials: "same-origin", headers: b ? { "content-type": "application/json" } : {}, body: b ? JSON.stringify(b) : undefined });
  return { status: r.status, text: await r.text() };
}, [method, path, body]);
const json = async (page, method, path, body) => JSON.parse((await api(page, method, path, body)).text);

/** The computed value a token resolves to, read from a probe placed where the element sits (so scoped tokens apply). */
const tokenValue = (locator, token, prop) => locator.evaluate((el, [t, p]) => {
  const d = document.createElement("span");
  d.style.setProperty(p, `var(${t})`);
  el.parentElement.appendChild(d);
  const v = getComputedStyle(d).getPropertyValue(p);
  d.remove();
  return v;
}, [token, prop]);

// One sign-in per account per run: the login limit is 10 per account and 30 per IP in 15 minutes, shared with every
// other check on this machine, so each test opens a fresh context from the saved session instead of signing in again.
const sessions = {};
before(async () => {
  browser = await launch();
  const roles = () => {
    sql(`UPDATE users SET role='admin' WHERE email='${ADMIN}'`);
    sql(`UPDATE users SET role='manager' WHERE email IN ('${MANAGER}','${EMPTY}')`);
  };
  roles();
  for (const e of [ADMIN, MANAGER, EMPTY]) {
    const saved = path.join(tmpdir(), `frontrow-e2e-${e}.json`);
    const role = e === ADMIN ? "admin" : "manager";
    if (existsSync(saved)) {
      const ctx = await browser.newContext({ storageState: saved });
      const me = await ctx.request.get(BASE + "/api/auth/me");
      const ok = me.status() === 200 && (await me.json()).role === role;
      await ctx.close();
      if (ok) { sessions[e] = saved; continue; }
    }
    const ctx = await browser.newContext();
    const data = { email: e, password: "e2e-check-password-123" };
    let r = await ctx.request.post(BASE + "/api/auth/login", { data });
    if (r.status() === 401) { // first run on this database: create it (registration is rate limited per IP, so only now)
      const made = await ctx.request.post(BASE + "/api/auth/register", { data });
      assert.equal(made.status(), 201, `register ${e}: ${await made.text()}`);
      roles();
      r = await ctx.request.post(BASE + "/api/auth/login", { data });
    }
    assert.equal(r.status(), 200, `sign-in ${e}: ${r.status()} ${await r.text()}`);
    await ctx.storageState({ path: saved });
    sessions[e] = saved;
    await ctx.close();
  }
  const { ctx, page } = await open(ADMIN);
  const id = (e) => sql(`SELECT id FROM users WHERE email='${e}'`);
  assert.equal((await api(page, "PUT", `/api/admin/managers/${id(MANAGER)}/screens`, { screen_ids: [3, 5] })).status, 200);
  assert.equal((await api(page, "PUT", `/api/admin/managers/${id(EMPTY)}/screens`, { screen_ids: [] })).status, 200);
  await ctx.close();
});
after(() => browser?.close());

async function open(email, _path, viewport = { width: 1440, height: 900 }) {
  const ctx = await browser.newContext({ viewport, storageState: sessions[email], locale: "en-US" });
  const page = await ctx.newPage();
  await page.goto(BASE + "/films");
  return { ctx, page };
}
const figures = (page) => page.locator(".rpt-figures > .rpt-figure");
const valuesShown = (page) => page.locator(".rpt-figures .rpt-value").count();

// ---------------------------------------------------------------------------------------------------------------
describe("S-RPT-18 opening load, tabs and hall filter", () => {
  test("opening load: scope and dashboard in parallel with no date, showtimes only after the dashboard resolves", async () => {
    const { ctx, page } = await open(ADMIN, "/dashboard");
    const log = [];
    page.on("request", (r) => r.url().includes("/api/reports/") && log.push(["start", new URL(r.url()).pathname + new URL(r.url()).search]));
    page.on("requestfinished", (r) => r.url().includes("/api/reports/") && log.push(["end", new URL(r.url()).pathname + new URL(r.url()).search]));
    await page.goto(BASE + "/dashboard");
    await page.locator(".rpt-scroll[tabindex='0']").waitFor();
    // Distinct URLs: the dev server runs React StrictMode, which mounts every effect twice (dev only).
    const starts = [...new Set(log.filter(([k]) => k === "start").map(([, u]) => u))];
    assert.deepEqual(starts.slice(0, 2).sort(), ["/api/reports/dashboard?period=day", "/api/reports/scope"]);
    assert.deepEqual(starts.slice(2), ["/api/reports/showtimes?period=day&limit=50&offset=0"]);
    const i = (k, u) => log.findIndex(([a, b]) => a === k && b.startsWith(u));
    assert.ok(i("start", "/api/reports/scope") < i("end", "/api/reports/dashboard") && i("start", "/api/reports/dashboard") < i("end", "/api/reports/scope"), "both in flight together");
    assert.ok(i("start", "/api/reports/showtimes") > i("end", "/api/reports/dashboard"), "showtimes after the dashboard resolved");
    await ctx.close();
  });

  test("exactly one tab is aria-selected on arrival and after each of three dispatched activations", async () => {
    const { ctx, page } = await open(ADMIN);
    await page.goto(BASE + "/dashboard");
    const tabs = page.getByRole("tab");
    const selected = async () => page.locator('[role="tab"][aria-selected="true"]').allTextContents();
    await page.locator(".rpt-value").first().waitFor();
    assert.deepEqual(await selected(), ["Day"]);
    for (const name of ["Week", "Month", "Day"]) {
      const req = page.waitForRequest((r) => r.url().includes(`/api/reports/dashboard?period=${name.toLowerCase()}`));
      await tabs.filter({ hasText: name }).click();
      await req;
      assert.deepEqual(await selected(), [name], `after activating ${name}`);
    }
    await ctx.close();
  });

  test("manager: the hall filter applies &screen_id=3, the scope line follows, both options stay; All my halls drops it", async () => {
    const { ctx, page } = await open(MANAGER);
    const urls = [];
    page.on("request", (r) => r.url().includes("/api/reports/") && urls.push(r.url()));
    await page.goto(BASE + "/dashboard");
    const scope = await json(page, "GET", "/api/reports/scope");
    const name = (id) => scope.screens.find((s) => s.screen_id === id).screen_name;
    const hall = page.getByRole("combobox", { name: "Hall" });
    await page.locator(".rpt-scope").waitFor();
    assert.equal(await page.locator(".rpt-scope").textContent(), `Halls shown: ${name(3)}, ${name(5)}.`);
    assert.deepEqual(await hall.locator("option").allTextContents(), ["All my halls", name(3), name(5)]);
    await shot(page, "rpt_manager_day.png");

    urls.length = 0;
    const shows = page.waitForRequest((r) => r.url().includes("/api/reports/showtimes?") && r.url().includes("screen_id=3"));
    await hall.selectOption("3");
    await shows;
    assert.ok(urls.some((u) => u.includes("/api/reports/dashboard?period=day&screen_id=3")), urls.join("\n"));
    await page.waitForFunction((t) => document.querySelector(".rpt-scope")?.textContent === t, `Halls shown: ${name(3)}.`);
    assert.equal(await hall.locator("option").count(), 3, "the filter still offers both halls");
    await shot(page, "rpt_manager_hall3.png");

    urls.length = 0;
    const back = page.waitForRequest((r) => r.url().includes("/api/reports/showtimes?"));
    await hall.selectOption({ label: "All my halls" });
    await back;
    assert.ok(urls.length > 0 && urls.every((u) => !u.includes("screen_id")), urls.join("\n"));
    await page.waitForFunction((t) => document.querySelector(".rpt-scope")?.textContent === t, `Halls shown: ${name(3)}, ${name(5)}.`);
    await ctx.close();
  });
});

// ---------------------------------------------------------------------------------------------------------------
describe("S-RPT-19 figures, computed styles and pending states", () => {
  test("takings figure: --fr-font-mono and tabular-nums from the computed style", async () => {
    const { ctx, page } = await open(ADMIN);
    await page.goto(BASE + "/dashboard");
    const takings = page.locator(".rpt-figure").first().locator(".rpt-value");
    await takings.waitFor();
    const style = await takings.evaluate((el) => ({ family: getComputedStyle(el).fontFamily, numeric: getComputedStyle(el).fontVariantNumeric }));
    assert.equal(style.family, await tokenValue(takings, "--fr-font-mono", "font-family"));
    assert.match(style.numeric, /tabular-nums/);
    assert.match(await takings.textContent(), /^\$\d{1,3}(,\d{3})*\.\d{2}$/);
    await shot(page, "rpt_admin_day.png");
    await ctx.close();
  });

  test("scope_empty: the line is not an alert and not --fr-danger-ink; figures read the dash", async () => {
    const { ctx, page } = await open(EMPTY);
    await page.goto(BASE + "/dashboard");
    const line = page.getByText("No halls are assigned to this account. Ask an administrator to assign one.", { exact: true });
    await line.waitFor();
    assert.equal(await line.getAttribute("role"), null);
    assert.equal(await line.locator("xpath=ancestor-or-self::*[@role='alert']").count(), 0);
    const color = await line.evaluate((el) => getComputedStyle(el).color);
    assert.notEqual(color, await tokenValue(line, "--fr-danger-ink", "color"));
    assert.deepEqual(await page.locator(".rpt-figures .rpt-value").allTextContents(), ["—", "—", "—", "—"]);
    assert.equal(await page.locator(".rpt-bar, table").count(), 0);
    await shot(page, "rpt_scope_empty.png");
    await ctx.close();
  });

  test("films_truncated: the note is not an alert and not --fr-danger-ink; the figures match the untruncated ones", async () => {
    const { ctx, page } = await open(ADMIN);
    await page.goto(BASE + "/dashboard");
    await page.locator(".rpt-value").first().waitFor();
    const plain = await page.locator(".rpt-figures .rpt-value").allTextContents();
    await page.route(/\/api\/reports\/dashboard\?/, async (route) => {
      const r = await route.fetch();
      await route.fulfill({ response: r, json: { ...(await r.json()), films_truncated: true } });
    });
    await page.reload();
    const note = page.getByText("Showing the top 100 films by takings. The figures above cover every film in this period.", { exact: true });
    await note.waitFor();
    assert.equal(await note.locator("xpath=ancestor-or-self::*[@role='alert']").count(), 0);
    assert.notEqual(await note.evaluate((el) => getComputedStyle(el).color), await tokenValue(note, "--fr-danger-ink", "color"));
    assert.deepEqual(await page.locator(".rpt-figures .rpt-value").allTextContents(), plain);
    await shot(page, "rpt_films_truncated.png");
    await ctx.close();
  });

  test("while the dashboard request is pending: four loading blocks, then four values in one commit; a period change clears takings", async () => {
    const { ctx, page } = await open(ADMIN);
    let release;
    let gate = new Promise((r) => (release = r));
    await page.route(/\/api\/reports\/dashboard\?/, async (route) => { await gate; await route.continue(); });
    await page.goto(BASE + "/dashboard");
    await figures(page).nth(3).waitFor();
    assert.equal(await page.locator(".rpt-figures .rpt-loading").count(), 4);
    assert.equal(await valuesShown(page), 0);
    await page.evaluate(() => {
      window.__counts = [];
      new MutationObserver(() => window.__counts.push(document.querySelectorAll(".rpt-figures .rpt-value").length))
        .observe(document.querySelector(".rpt-panel"), { childList: true, subtree: true, characterData: true });
    });
    release();
    await page.waitForFunction(() => document.querySelectorAll(".rpt-figures .rpt-value").length === 4);
    const counts = await page.evaluate(() => window.__counts);
    assert.ok(!counts.some((n) => n > 0 && n < 4), `values appeared one by one: ${counts}`);
    const before = await page.locator(".rpt-figure").first().locator(".rpt-value").textContent();

    gate = new Promise((r) => (release = r));
    await page.getByRole("tab", { name: "Week" }).click();
    const takings = page.locator(".rpt-figure").first();
    await takings.locator(".rpt-loading").waitFor();
    assert.equal(await takings.locator(".rpt-value").count(), 0);
    assert.ok(!(await takings.textContent()).includes(before), "the previous period's takings are not left on screen");
    release();
    await page.waitForFunction(() => document.querySelectorAll(".rpt-figures .rpt-value").length === 4);
    await ctx.close();
  });
});

// ---------------------------------------------------------------------------------------------------------------
describe("S-RPT-20 keyboard, focus ring and narrow layout", () => {
  /** Tab from the top of the document; record every stop inside the panel until focus leaves it. */
  async function tabStops(page) {
    await page.evaluate(() => { document.activeElement?.blur(); window.scrollTo(0, 0); });
    const stops = [];
    for (let i = 0; i < 150; i++) {
      await page.keyboard.press("Tab");
      const s = await page.evaluate(() => {
        const a = document.activeElement;
        const panel = document.querySelector(".rpt-panel");
        const regions = {
          tablist: panel.querySelector('[role="tablist"]'), stepper: panel.querySelector(".rpt-stepper"), hall: panel.querySelector(".rpt-field"),
          link: panel.querySelector("a.rpt-link"), films: panel.querySelectorAll(".rpt-scroll")[0], shows: panel.querySelector('.rpt-scroll[tabindex="0"]'),
          pager: panel.querySelector(".rpt-pager"),
        };
        const probe = document.createElement("span");
        probe.style.outlineColor = "var(--fr-focus-ring)";
        a.parentElement?.appendChild(probe);
        const ring = getComputedStyle(probe).outlineColor;
        probe.remove();
        const label = a.tagName === "SELECT" ? a.closest("label")?.firstChild?.textContent?.trim() : null;
        return {
          inPanel: panel.contains(a) && a !== panel, region: Object.entries(regions).find(([, el]) => el && el.contains(a))?.[0] ?? null,
          name: a.getAttribute("aria-label") ?? label ?? a.textContent.trim(), selected: a.getAttribute("aria-selected"),
          outline: getComputedStyle(a).outlineColor, outlineStyle: getComputedStyle(a).outlineStyle, ring, holdsShows: !!a.querySelector?.("table caption") && a.getAttribute("tabindex") === "0",
        };
      });
      if (s.inPanel) stops.push(s);
      else if (stops.length) break;
    }
    return stops;
  }
  const regionsOf = (stops) => stops.map((s) => s.region).filter((r, i, a) => r !== a[i - 1]);
  const FILM_HEADERS = ["Film, sort by this column", "Shows, sort by this column", "Seats sold, sort by this column", "Capacity, sort by this column",
    "Occupancy, sort by this column", "Takings, sorted highest first. Activate to sort lowest first"];
  // The first page of 214 per-show rows: the local data has fewer shows today, so the listing's total is raised.
  const page214 = (page) => page.route(/\/api\/reports\/showtimes\?/, async (route) => {
    const r = await route.fetch();
    await route.fulfill({ response: r, json: { ...(await r.json()), total: 214 } });
  });

  for (const [who, email, expected] of [
    ["administrator", ADMIN, ["tablist", "stepper", "hall", "link", "films", "shows", "pager"]],
    ["manager", MANAGER, ["tablist", "stepper", "hall", "films", "shows", "pager"]],
  ]) {
    test(`${who}: Tab visits ${expected.length} contiguous regions in order, named stops, focus ring = --fr-focus-ring`, async () => {
      const { ctx, page } = await open(email);
      await page214(page);
      await page.goto(BASE + "/dashboard");
      await page.getByRole("button", { name: "Later shows" }).waitFor();
      const stops = await tabStops(page);
      assert.ok(stops.every((s) => s.region), `a stop outside the seven regions: ${JSON.stringify(stops.filter((s) => !s.region))}`);
      assert.deepEqual(regionsOf(stops), expected);
      const names = stops.map((s) => s.name);
      const want = ["Day", "Previous day", "Next day", "Hall", ...(who === "administrator" ? ["Change log"] : []), ...FILM_HEADERS];
      assert.deepEqual(names.slice(0, want.length), want);
      assert.equal(stops[0].selected, "true");
      const showsStops = stops.filter((s) => s.region === "shows");
      assert.equal(showsStops.length, 1);
      assert.ok(showsStops[0].holdsShows, "the per-show stop is the tabindex=0 scroll container holding the table");
      assert.deepEqual(stops.filter((s) => s.region === "pager").map((s) => s.name), ["Later shows"]);
      assert.equal(await page.getByRole("button", { name: "Earlier shows" }).count(), 0);
      for (const s of stops) {
        assert.notEqual(s.outlineStyle, "none", `no ring drawn at ${s.name}`);
        assert.equal(s.outline, s.ring, `outline at ${s.name}`);
      }
      await ctx.close();
    });
  }

  test("each table's scroll container is overflow-x auto, and at 320 px the body does not scroll sideways", async () => {
    const { ctx, page } = await open(ADMIN, "/dashboard", { width: 320, height: 800 });
    await page.goto(BASE + "/dashboard");
    await page.locator(".rpt-scroll[tabindex='0'] tbody tr").first().waitFor();
    assert.deepEqual(await page.locator(".rpt-scroll").evaluateAll((els) => els.map((e) => getComputedStyle(e).overflowX)), ["auto", "auto"]);
    const w = await page.evaluate(() => [document.body.scrollWidth, document.body.clientWidth]);
    await shot(page, "rpt_admin_320.png");
    assert.equal(w[0], w[1], `body scrollWidth ${w[0]} vs clientWidth ${w[1]}`);
    await ctx.close();
  });
});

// ---------------------------------------------------------------------------------------------------------------
describe("S-RPT-21 change log: no auto-submit, cleared filters announced, only audit requests", () => {
  /** Type a date with key events into an empty native date field, in the segment order this Chromium build uses
   *  (it follows the OS locale, not the context's), learned once from a scratch field. */
  const typeDate = async (input, iso) => {
    const [y, m, d] = iso.split("-");
    const probe = await input.page().context().newPage();
    await probe.setContent('<input type="date">');
    await probe.locator("input").focus();
    await probe.keyboard.type("11052026");
    const monthFirst = (await probe.locator("input").inputValue()) === "2026-11-05";
    await probe.close();
    await input.focus();
    await input.pressSequentially(monthFirst ? m + d + y : d + m + y);
    assert.equal(await input.inputValue(), iso);
  };

  test("whole lifecycle against the live API: typing from > to fires nothing; every request the screen makes is GET /api/reports/audit", async () => {
    const { ctx, page } = await open(ADMIN);
    await page.goto(BASE + "/dashboard");
    const link = page.locator(".rpt-panel").getByRole("link", { name: "Change log" });
    await page.locator(".rpt-scroll[tabindex='0']").waitFor(); // the dashboard's own requests have all settled
    await page.waitForLoadState("networkidle");
    const calls = [];
    page.on("request", (r) => r.url().includes("/api/") && calls.push(`${r.method()} ${new URL(r.url()).pathname}`));
    await link.click();
    await page.locator(".rpt-count").filter({ hasText: /changes?\./ }).waitFor();
    const spill = await page.locator(".rpt-filters").evaluate((f) => {
      const edge = f.getBoundingClientRect().right;
      return [...f.querySelectorAll("input, select")].filter((c) => c.getBoundingClientRect().right > edge + 0.5).length;
    });
    assert.equal(spill, 0, "a filter control spills past the filter row");
    const n = calls.length;
    const from = page.getByLabel("From", { exact: true }), to = page.getByLabel("To", { exact: true });
    await typeDate(to, "2026-11-01");
    await typeDate(from, "2026-11-05");
    assert.equal(await from.inputValue(), "2026-11-05");
    assert.equal(await to.inputValue(), "2026-11-01");
    await page.getByRole("combobox", { name: "Action" }).selectOption("");
    await page.waitForTimeout(400);
    assert.equal(calls.length, n, `requests fired without Apply: ${calls.slice(n)}`);
    const applied = page.waitForResponse((r) => r.url().includes("/api/reports/audit?from=2026-11-05&to=2026-11-01"));
    await page.getByRole("button", { name: "Apply" }).click();
    await applied;
    await page.waitForTimeout(300);
    // /api/auth/me is the Shell's identity read on every route change (Shell.tsx), not this screen's.
    const screens = calls.filter((c) => c !== "GET /api/auth/me");
    assert.ok(screens.length >= 2 && screens.every((c) => c === "GET /api/reports/audit"), screens.join("\n"));
    await ctx.close();
  });

  test("a date change that drops the selected action and administrator clears both and says so in the count region", async () => {
    const { ctx, page } = await open(ADMIN);
    const row = (id, action, actor) => ({ id, occurred_at: "2026-11-02T15:40:00+05:30", actor_user_id: actor.actor_user_id, actor_email: actor.actor_email,
      actor_role: "admin", action, entity_type: "showtime", entity_id: 7, before: { base_price_paise: 25000 }, after: { base_price_paise: 30000 } });
    const A = { actor_user_id: 501, actor_email: "first-admin@example.com" }, B = { actor_user_id: 502, actor_email: "second-admin@example.com" };
    const urls = [];
    await page.route(/\/api\/reports\/audit/, (route) => {
      const u = new URL(route.request().url());
      urls.push(u.search);
      const late = u.searchParams.get("from") === "2026-11-05";
      const rows = late ? [row(2, "kind.two", B)] : [row(1, "kind.one", A), row(2, "kind.two", B)];
      return route.fulfill({ json: { window_start_utc: "", window_end_utc: "", timezone: "Asia/Kolkata", rows, next_cursor: null,
        available_actions: late ? ["kind.two"] : ["kind.one", "kind.two"], available_actors: late ? [B] : [A, B] } });
    });
    await page.goto(BASE + "/dashboard/audit");
    const action = page.getByRole("combobox", { name: "Action" }), actor = page.getByRole("combobox", { name: "Administrator" });
    await page.locator(".rpt-count").filter({ hasText: "2 changes." }).waitFor();
    const actorValues = await actor.locator("option").evaluateAll((o) => o.map((x) => x.value));
    await action.selectOption("kind.one");
    assert.deepEqual(await actor.locator("option").evaluateAll((o) => o.map((x) => x.value)), actorValues, "selecting an action leaves the actors alone");
    const actionValues = await action.locator("option").evaluateAll((o) => o.map((x) => x.value));
    await actor.selectOption("501");
    assert.deepEqual(await action.locator("option").evaluateAll((o) => o.map((x) => x.value)), actionValues, "and vice versa");
    await typeDate(page.getByLabel("From", { exact: true }), "2026-11-05");
    await page.getByRole("button", { name: "Apply" }).click();
    const live = page.locator('[aria-live="polite"]');
    await live.filter({ hasText: "cleared" }).waitFor({ timeout: 5000 }).catch(async () => {
      throw new Error(`live=${await live.textContent()} from=${await page.getByLabel("From", { exact: true }).inputValue()} urls=${urls}`);
    });
    assert.equal(await live.textContent(), "The action filter was cleared. No change of that kind was recorded in this period. "
      + "The administrator filter was cleared. That account made no changes in this period. 1 change.");
    assert.equal(await action.inputValue(), "");
    assert.equal(await actor.inputValue(), "");
    assert.ok(!urls.at(-1).includes("action=") && !urls.at(-1).includes("actor_user_id="), urls.at(-1));
    await shot(page, "rpt_audit_cleared.png");
    await ctx.close();
  });
});

// ---------------------------------------------------------------------------------------------------------------
describe("S-ADM-14 the five edit forms submitted unchanged carry the GET's version", () => {
  /** Serve the write back as the row it was read as (the stored row is not touched); return the captured body. */
  async function captureWrite(page, pattern, reply) {
    let body;
    await page.route(pattern, (route) => {
      if (route.request().method() !== "PATCH") return route.fallback();
      body = route.request().postDataJSON();
      return route.fulfill({ json: reply() });
    });
    return () => body;
  }
  const isVersion = (body, version) => {
    assert.ok(body, "no PATCH was sent");
    assert.ok(Number.isInteger(body.version), `version ${JSON.stringify(body.version)} is not an integer`);
    assert.equal(body.version, version);
  };

  test("SCR-ADM-02 film editor", async () => {
    const { ctx, page } = await open(ADMIN);
    const read = page.waitForResponse((r) => /\/api\/admin\/movies\/4$/.test(r.url()) && r.request().method() === "GET");
    let film;
    const sent = await captureWrite(page, /\/api\/admin\/movies\/4$/, () => film);
    await page.goto(BASE + "/admin/movies/4");
    film = await (await read).json();
    await page.locator("select").nth(1).locator(`option[value="${film.language_id}"]`).waitFor({ state: "attached" });
    await page.getByRole("button", { name: "Save" }).click();
    await page.waitForTimeout(300);
    isVersion(sent(), film.version);
    await shot(page, "adm_film_editor.png");
    await ctx.close();
  });

  test("SCR-ADM-03 showtimes", async () => {
    const { ctx, page } = await open(ADMIN);
    await page.goto(BASE + "/admin/showtimes");
    await page.getByRole("combobox", { name: "Hall" }).locator("option[value='1']").waitFor({ state: "attached" });
    const read = page.waitForResponse((r) => r.url().includes("/api/admin/showtimes?") && r.url().includes("date=2026-11-08"));
    await page.getByRole("combobox", { name: "Hall" }).selectOption("1");
    await page.getByLabel("Date").fill("2026-11-08");
    const listing = await (await read).json();
    const first = listing.items[0];
    const sent = await captureWrite(page, new RegExp(`/api/admin/showtimes/${first.id}$`), () => first);
    await page.locator(".admin-list button").first().click();
    await page.getByRole("button", { name: "Save changes" }).click();
    await page.waitForTimeout(300);
    isVersion(sent(), first.version);
    await shot(page, "adm_showtimes.png");
    await ctx.close();
  });

  test("SCR-ADM-04 seat categories", async () => {
    const { ctx, page } = await open(ADMIN);
    const read = page.waitForResponse((r) => r.url().endsWith("/api/admin/seat-categories") && r.request().method() === "GET");
    await page.goto(BASE + "/admin/seat-categories");
    const listing = await (await read).json();
    const first = listing.items[0];
    const sent = await captureWrite(page, new RegExp(`/api/admin/seat-categories/${first.id}$`), () => first);
    let dialog = false;
    page.on("dialog", (d) => { dialog = true; d.dismiss(); });
    await page.getByRole("button", { name: "Save pricing" }).first().click();
    await page.waitForTimeout(300);
    assert.equal(dialog, false, "an unchanged uplift asks no confirmation");
    isVersion(sent(), first.version);
    await shot(page, "adm_seat_categories.png");
    await ctx.close();
  });

  test("SCR-ADM-05 hall configuration", async () => {
    const { ctx, page } = await open(ADMIN);
    const read = page.waitForResponse((r) => r.url().endsWith("/api/admin/screens") && r.request().method() === "GET");
    await page.goto(BASE + "/admin/halls");
    const hall = (await (await read).json()).items[0];
    const sent = await captureWrite(page, new RegExp(`/api/admin/screens/${hall.id}$`), () => hall);
    await page.getByRole("button", { name: hall.name, exact: true }).click();
    await page.getByRole("button", { name: "Save hall" }).click();
    await page.waitForTimeout(300);
    isVersion(sent(), hall.version);
    await shot(page, "adm_hall_config.png");
    await ctx.close();
  });

  test("SCR-ADM-08 venue", async () => {
    const { ctx, page } = await open(ADMIN);
    const read = page.waitForResponse((r) => r.url().endsWith("/api/admin/cinemas") && r.request().method() === "GET");
    await page.goto(BASE + "/admin/venue");
    const venue = (await (await read).json()).items[0];
    const sent = await captureWrite(page, new RegExp(`/api/admin/cinemas/${venue.id}$`), () => venue);
    await page.getByRole("button", { name: "Save venue" }).click();
    await page.waitForTimeout(300);
    isVersion(sent(), venue.version);
    await shot(page, "adm_venue.png");
    await ctx.close();
  });
});

// ---------------------------------------------------------------------------------------------------------------
describe("S-ADM-17 SCR-ADM-05 withdrawal confirmation", () => {
  test("the confirmation text is byte-for-byte the published one, and dismissing it writes nothing", async () => {
    const { ctx, page } = await open(ADMIN);
    await page.goto(BASE + "/admin/halls");
    const writes = [];
    page.on("request", (r) => r.method() !== "GET" && r.url().includes("/api/") && writes.push(r.url()));
    const first = page.locator(".admin-list > li > button.admin-link").first();
    await first.click();
    let message = null;
    page.once("dialog", (d) => { message = d.message(); d.dismiss(); });
    await page.getByRole("button", { name: "Take hall out of service" }).click();
    await page.waitForTimeout(300);
    assert.equal(message, "This hall will accept no new showtimes. Showtimes that already exist are not changed, bookings are not cancelled, "
      + "and nothing is refunded. The hall is not deleted and you can bring it back into service.");
    assert.deepEqual(writes, []);
    await shot(page, "adm_hall_withdraw.png");
    await ctx.close();
  });
});

// ---------------------------------------------------------------------------------------------------------------
describe("S-ADM-19 a booking reads the same bytes after its film, hall and seat are withdrawn", () => {
  test("GET /api/me/bookings/{reference} before and after the three withdrawals, compared as bytes (all three restored after)", async () => {
    // Any signed-in account may hold and book (holds.signed_in); the admin books, so no customer is registered
    // (registration is rate limited per IP and shared with the other checks on this machine).
    const cust = await open(ADMIN);
    const adm = await open(ADMIN);
    const c = cust.page, a = adm.page;
    const MOVIE = 4;
    const booked = await c.evaluate(async (movie) => {
      const j = async (u, init) => { const r = await fetch(u, { credentials: "same-origin", ...init }); return { s: r.status, b: await r.json().catch(() => null) }; };
      let day = (await j(`/api/showtimes?movie_id=${movie}`)).b;
      for (let i = 0; i < 5 && !day.showtimes.some((s) => !s.sales_closed); i++) day = (await j(`/api/showtimes?movie_id=${movie}&date=${day.next_date_with_showtimes}`)).b;
      const st = day.showtimes.find((s) => !s.sales_closed);
      const map = (await j(`/api/showtimes/${st.id}/seatmap`)).b;
      const seat = map.seats.find((s) => s.state === "available" && s.is_active);
      const hold = await j(`/api/showtimes/${st.id}/holds`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ seat_ids: [seat.id] }) });
      const bk = await j("/api/bookings", { method: "POST", headers: { "content-type": "application/json", "Idempotency-Key": crypto.randomUUID() },
        body: JSON.stringify({ hold_token: hold.b.hold_token, showtime_id: st.id }) });
      return { screenId: map.screen.id, seatId: seat.id, status: bk.s, reference: bk.b?.booking_reference };
    }, MOVIE);
    assert.equal(booked.status, 201, JSON.stringify(booked));
    const read = () => api(c, "GET", `/api/me/bookings/${encodeURIComponent(booked.reference)}`);
    const before = await read();
    assert.equal(before.status, 200);
    const version = async (path) => (await json(a, "GET", path)).version;
    const hallVersion = async () => (await json(a, "GET", "/api/admin/screens")).items.find((h) => h.id === booked.screenId).version;
    try {
      assert.equal((await api(a, "POST", `/api/admin/movies/${MOVIE}/unpublish`, { version: await version(`/api/admin/movies/${MOVIE}`) })).status, 200);
      assert.equal((await api(a, "PATCH", `/api/admin/screens/${booked.screenId}`, { version: await hallVersion(), is_active: false })).status, 200);
      assert.equal((await api(a, "PATCH", `/api/admin/seats/${booked.seatId}`, { is_active: false })).status, 200);
      const afterAll = await read();
      assert.equal(afterAll.status, 200);
      assert.equal(afterAll.text, before.text, "the booking reads differently after the withdrawals");
    } finally {
      await api(a, "PATCH", `/api/admin/seats/${booked.seatId}`, { is_active: true });
      await api(a, "PATCH", `/api/admin/screens/${booked.screenId}`, { version: await hallVersion(), is_active: true });
      const film = await json(a, "GET", `/api/admin/movies/${MOVIE}`);
      if (!film.published) await api(a, "POST", `/api/admin/movies/${MOVIE}/publish`, { version: film.version });
    }
    assert.equal((await json(a, "GET", `/api/admin/movies/${MOVIE}`)).published, true, "film restored");
    assert.equal((await json(a, "GET", "/api/admin/screens")).items.find((h) => h.id === booked.screenId).is_active, true, "hall restored");
    await cust.ctx.close();
    await adm.ctx.close();
  });
});

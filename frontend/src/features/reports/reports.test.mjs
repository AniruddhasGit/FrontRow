// SCR-RPT-01 / SCR-RPT-02 as rendered (frontend/src/test/render.mjs) plus their pure rules.
// Run: node --test "frontend/src/features/reports/*.test.mjs"
// Not asserted here (needs a real browser): computed styles and colours, focus movement and the Tab walk, key and
// click events, viewport width, axe-core. The render harness runs no effect; the opening load is asserted through
// the loader the screen's effect calls (openingLoad), with a recording fetch.
import assert from "node:assert/strict";
import { test } from "node:test";
import { all, atUrl, load, name, render, role, tabbable, text } from "../../test/render.mjs";

atUrl("/dashboard");
const { DashboardScreen } = await load("/src/features/reports/dashboard/DashboardScreen.tsx");
const { AuditScreen } = await load("/src/features/reports/audit/AuditScreen.tsx");
const L = await load("/src/features/reports/dashboard/logic.ts");
const A = await load("/src/features/reports/audit/logic.ts");
const F = await load("/src/features/reports/format.ts");
const { getJson } = await load("/src/features/reports/api.ts");

const SCREENS = [{ screen_id: 3, screen_name: "Hall 3", is_active: true }, { screen_id: 5, screen_name: "Hall 5", is_active: true }];
const MANAGER = { role: "manager", scope_empty: false, all_halls: false, screens: SCREENS, timezone: "Asia/Kolkata", today: "2026-08-14" };
const ADMIN = { ...MANAGER, role: "admin", all_halls: true, screens: [1, 2, 3, 4, 5, 6].map((i) => ({ screen_id: i, screen_name: `Hall ${i}`, is_active: i !== 6 })) };
const FILM = { movie_id: 1, title: "DEMO MOVIE 01", shows: 2, seats_sold: 109, capacity: 370, occupancy_pct: 29.5, takings_paise: 2783331 };
const DASH = { period: "day", scope_empty: false, screen_ids: [3, 5], takings_paise: 2783331, seats_sold: 109, capacity: 370,
  occupancy_pct: 29.5, shows: 2, films: [FILM], films_truncated: false };
const ROW = (id, starts, started = false) => ({ showtime_id: id, starts_at: starts, screen_id: 3, screen_name: "Hall 3", movie_id: 1,
  title: "DEMO MOVIE 01", seats_sold: 97, capacity: 150, occupancy_pct: 64.7, takings_paise: 2483331, has_started: started });
const SHOWS = { total: 2, limit: 50, offset: 0, rows: [ROW(101, "2026-08-14T19:30:00+05:30"), ROW(102, "2026-08-14T23:45:00+05:30")] };
const Q = { period: "day", anchor: null, screenId: "", offset: 0 };
const dash = (seed) => render(DashboardScreen, { seed: { query: Q, scope: MANAGER, dash: DASH, shows: SHOWS, ...seed } });
const byClass = (doc, cls) => all(doc, (e) => (e.attrs.class ?? "").split(/\s+/).includes(cls));
const figures = (doc) => byClass(doc, "rpt-figure").map((f) => byClass(f, "rpt-value").map(text).join(""));
const BARE_UTC = /\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z/;
const textNodes = (n) => (n.text !== undefined ? [n.text] : (n.children ?? []).flatMap(textNodes));

// ---- S-RPT-06 / S-RPT-19: figures formatted at the edge ----------------------------------------------------------
test("S-RPT-06/19: takings render ₹27,833.31 with Indian grouping; the four figures render together", () => {
  const doc = dash({});
  assert.deepEqual(figures(doc), ["₹27,833.31", "29.5 %", "109", "2"]);
  assert.equal(F.formatPaise(1234567890), "₹1,23,45,678.90");
});

test("S-RPT-19: loading - all four figures show the loading block and none a value; a period change clears them", () => {
  const pending = dash({ dash: null });
  assert.equal(byClass(pending, "rpt-figure").length, 4);
  assert.deepEqual(figures(pending), ["", "", "", ""]);
  assert.equal(byClass(pending, "rpt-loading").length, 4);
  const week = dash({ dash: null, query: { ...Q, period: "week" } });
  assert.ok(!text(week).includes("₹27,833.31"));
});

test("S-RPT-19: the period line, from the local anchor by calendar arithmetic", () => {
  assert.equal(L.periodLine("2026-08-14", "day"), "Friday 14 August 2026");
  assert.equal(L.periodLine("2026-08-14", "week"), "Monday 10 August to Sunday 16 August 2026");
  assert.equal(L.periodLine("2026-01-01", "week"), "Monday 29 December 2025 to Sunday 4 January 2026");
  assert.equal(L.periodLine("2026-09-03", "week"), "Monday 31 August to Sunday 6 September 2026");
  assert.equal(L.periodLine("2026-08-14", "month"), "August 2026");
  assert.ok(text(dash({})).includes("Friday 14 August 2026"));
  assert.deepEqual([L.shift("2026-08-14", "day", 1), L.shift("2026-08-14", "week", -1), L.shift("2026-12-14", "month", 1)],
    ["2026-08-15", "2026-08-03", "2027-01-01"]);
});

test("S-RPT-19: the three zero states render three different ways", () => {
  const none = dash({ dash: { ...DASH, scope_empty: true, screen_ids: [], takings_paise: 0, seats_sold: 0, capacity: 0, occupancy_pct: null, shows: 0, films: [] },
    scope: { ...MANAGER, scope_empty: true, screens: [] }, shows: null });
  assert.deepEqual(figures(none), ["—", "—", "—", "—"]);
  assert.equal(byClass(none, "rpt-bar").length, 0);
  assert.equal(all(none, (e) => e.tag === "table").length, 0);
  const line = all(none, (e) => text(e) === "No halls are assigned to this account. Ask an administrator to assign one.");
  assert.equal(line.length, 1);
  assert.equal(line[0].attrs.role, undefined);

  const unscheduled = dash({ dash: { ...DASH, takings_paise: 0, seats_sold: 0, capacity: 0, occupancy_pct: null, shows: 0, films: [] } });
  assert.deepEqual(figures(unscheduled).slice(0, 2), ["₹0.00", "—"]);
  assert.equal(byClass(unscheduled, "rpt-bar").length, 0);
  assert.ok(text(unscheduled).includes("No shows were scheduled in this period."));

  const unsold = dash({ dash: { ...DASH, takings_paise: 0, seats_sold: 0, occupancy_pct: 0, films: [] } });
  assert.deepEqual(figures(unsold).slice(0, 2), ["₹0.00", "0.0 %"]);
  assert.equal(byClass(unsold, "rpt-bar-fill")[0].attrs.style, "width:0%");
  assert.ok(text(unsold).includes("No seats were sold in this period."));
});

test("S-RPT-19: truncation line, captions, live-figures note, no change-log link for a manager, Still selling", () => {
  const cut = dash({ dash: { ...DASH, films_truncated: true } });
  const line = all(cut, (e) => text(e) === "Showing the top 100 films by takings. The figures above cover every film in this period.");
  assert.equal(line.length, 1);
  assert.equal(line[0].attrs.role, undefined);
  assert.deepEqual(figures(cut), figures(dash({})));
  const m = dash({});
  assert.deepEqual(all(m, (e) => e.tag === "caption").map(text), ["Per film, in your halls", "Every show in this period"]);
  assert.ok(text(m).includes("These figures are recomputed from current records each time this page loads. If a figure has changed, ask an administrator to check the change log."));
  assert.equal(all(m, (e) => role(e) === "link" && /change log/i.test(name(e, m))).length, 0);
  const a = dash({ scope: ADMIN, dash: { ...DASH, screen_ids: [1, 2, 3, 4, 5, 6] } });
  assert.equal(all(a, (e) => e.tag === "caption").map(text)[0], "Per film");
  assert.ok(text(a).includes("These figures are recomputed from current records each time this page loads.")
    && !text(a).includes("If a figure has changed"));
  assert.equal(all(a, (e) => role(e) === "link" && name(e, a) === "Change log").length, 1);
  assert.equal(all(m, (e) => text(e) === "Still selling").length, 2);
});

// ---- S-RPT-18: opening load, scope line, hall filter ---------------------------------------------------------------
function recorder(bodies) {
  const calls = [];
  const gates = {};
  const get = (url) => {
    calls.push({ url, at: calls.length });
    const key = url.split("?")[0].split("/").pop();
    return new Promise((resolve) => {
      gates[key] = () => resolve({ status: 200, headers: { get: () => null }, json: async () => bodies[key] });
    });
  };
  return { calls, gates, get };
}

test("S-RPT-18: two requests at once, the listing only after the dashboard resolves, no date sent", async () => {
  const r = recorder({ scope: MANAGER, dashboard: DASH, showtimes: SHOWS });
  const parts = [];
  const done = L.openingLoad(r.get, Q, (p) => parts.push(Object.keys(p)[0]));
  assert.deepEqual(r.calls.map((c) => c.url), ["/api/reports/scope", "/api/reports/dashboard?period=day"]);
  assert.ok(!r.calls[1].url.includes("date="));
  r.gates.dashboard();
  await new Promise((res) => setImmediate(res));
  assert.deepEqual(r.calls.map((c) => c.url).slice(2), ["/api/reports/showtimes?period=day&limit=50&offset=0"]);
  r.gates.scope();
  r.gates.showtimes();
  await done;
  assert.deepEqual(parts.sort(), ["dash", "scope", "shows"]);
});

test("S-RPT-18: exactly one tab selected, Day on arrival", () => {
  for (const period of ["day", "week", "month"]) {
    const doc = dash({ query: { ...Q, period } });
    const selected = all(doc, (e) => role(e) === "tab" && e.attrs["aria-selected"] === "true").map(text);
    assert.deepEqual(selected, [{ day: "Day", week: "Week", month: "Month" }[period]]);
  }
  const arrival = render(DashboardScreen, { seed: { scope: MANAGER } });
  assert.deepEqual(all(arrival, (e) => e.attrs["aria-selected"] === "true").map(text), ["Day"]);
});

test("S-RPT-18: scope line from EP-RPT-03 names, hall filter options", () => {
  const m = dash({});
  assert.ok(textNodes(m).includes("Halls shown: Hall 3, Hall 5."));
  assert.ok(!text(m).includes("Halls shown: 3, 5."));
  const narrowed = dash({ dash: { ...DASH, screen_ids: [3] }, query: { ...Q, screenId: "3" } });
  assert.ok(textNodes(narrowed).includes("Halls shown: Hall 3."));
  const select = all(narrowed, (e) => role(e) === "combobox" && name(e, narrowed) === "Hall");
  assert.equal(select.length, 1);
  assert.deepEqual(all(select[0], (e) => e.tag === "option").map(text), ["All my halls", "Hall 3", "Hall 5"]);
  assert.equal(L.query({ ...Q, screenId: "" }).includes("screen_id"), false);
  const a = dash({ scope: ADMIN, dash: { ...DASH, screen_ids: [1, 2, 3, 4, 5, 6] } });
  assert.ok(textNodes(a).includes("Halls shown: every hall."));
  const options = all(a, (e) => e.tag === "option");
  assert.deepEqual(options.map(text), ["All halls", "Hall 1", "Hall 2", "Hall 3", "Hall 4", "Hall 5", "Hall 6 — out of service"]);
  assert.ok(options.every((o) => !("disabled" in o.attrs)));
});

test("S-RPT-18/20: an empty scope renders no scope line, no hall filter, no table, no pager, nothing disabled", () => {
  const doc = dash({ dash: { ...DASH, scope_empty: true, screen_ids: [], takings_paise: 0, seats_sold: 0, capacity: 0, occupancy_pct: null, shows: 0, films: [] },
    scope: { ...MANAGER, scope_empty: true, screens: [] }, shows: null });
  assert.equal(all(doc, (e) => role(e) === "combobox").length, 0);
  assert.equal(all(doc, (e) => ["All my halls", "All halls"].includes(name(e, doc)) && e.tag !== "#root").length, 0);
  assert.equal(textNodes(doc).filter((t) => /^Halls shown:/.test(t)).length, 0);
  assert.equal(all(doc, (e) => e.tag === "table").length, 0);
  assert.equal(all(doc, (e) => ["Earlier shows", "Later shows"].includes(text(e))).length, 0);
  assert.equal(all(doc, (e) => "disabled" in e.attrs).length, 0);
  assert.equal(all(doc, (e) => e.attrs.role === "alert").length, 0);
});

// ---- S-RPT-20: names, headers, sorting, pager ----------------------------------------------------------------------
test("S-RPT-20: stepper names follow the period type; figures carry spoken names", () => {
  for (const [period, unit] of [["day", "day"], ["week", "week"], ["month", "month"]]) {
    const doc = dash({ query: { ...Q, period } });
    const names = all(doc, (e) => role(e) === "button").map((b) => name(b, doc));
    assert.ok(names.includes(`Previous ${unit}`) && names.includes(`Next ${unit}`), names.join(" | "));
  }
  const doc = dash({});
  const named = byClass(doc, "rpt-figure").map((f) => name(f, doc));
  assert.equal(named[0], "Takings, twenty-seven thousand eight hundred and thirty-three rupees and thirty-one paise");
  assert.equal(named[1], "Occupancy, twenty-nine point five per cent");
  const bar = byClass(doc, "rpt-bar")[0];
  assert.equal(bar.attrs["aria-hidden"], "true");
});

test("S-RPT-20: six sortable per-film headers, seven plain per-show headers", () => {
  const doc = dash({});
  const [films, shows] = all(doc, (e) => e.tag === "table");
  const fh = all(films, (e) => e.tag === "th");
  assert.equal(fh.length, 6);
  assert.ok(fh.every((h) => all(h, (e) => e.tag === "button").length === 1 && "aria-sort" in h.attrs));
  assert.deepEqual(fh.map((h) => name(all(h, (e) => e.tag === "button")[0], doc)), [
    "Film, sort by this column", "Shows, sort by this column", "Seats sold, sort by this column", "Capacity, sort by this column",
    "Occupancy, sort by this column", "Takings, sorted highest first. Activate to sort lowest first"]);
  const sh = all(shows, (e) => e.tag === "th");
  assert.deepEqual(sh.map(text), ["Start", "Hall", "Film", "Seats sold", "Capacity", "Occupancy", "Takings"]);
  assert.ok(sh.every((h) => !("aria-sort" in h.attrs) && all(h, (e) => e.tag === "button").length === 0));
  const container = all(doc, (e) => e.attrs.tabindex === "0" && all(e, (t) => t === shows).length === 1);
  assert.equal(container.length, 1);
});

test("S-RPT-20: toggling a column and back restores the order; ties fall back to title then movie_id", () => {
  const films = [
    { ...FILM, movie_id: 4, title: "B", shows: 1, takings_paise: 10 }, { ...FILM, movie_id: 2, title: "A", shows: 1, takings_paise: 10 },
    { ...FILM, movie_id: 3, title: "A", shows: 2, takings_paise: 30 }, { ...FILM, movie_id: 1, title: "A", shows: 1, takings_paise: 10 }];
  const first = L.sortFilms(films, L.DEFAULT_SORT).map((f) => f.movie_id);
  assert.deepEqual(first, [3, 1, 2, 4]);
  let sort = L.toggle(L.DEFAULT_SORT, "shows");
  assert.deepEqual(L.sortFilms(films, sort).map((f) => f.movie_id), [3, 1, 2, 4]);
  sort = L.toggle(sort, "shows");
  assert.deepEqual(L.sortFilms(films, sort).map((f) => f.movie_id), [1, 2, 4, 3]);
  sort = L.toggle(sort, "takings_paise");
  assert.deepEqual(L.sortFilms(films, sort).map((f) => f.movie_id), first);
});

test("S-RPT-20: pager - Later only at the start, position line forms, the only show", () => {
  const big = { total: 214, limit: 50, offset: 0, rows: Array.from({ length: 50 }, (_, i) => ROW(1000 + i, "2026-08-14T19:30:00+05:30")) };
  const doc = dash({ shows: big });
  const buttons = all(doc, (e) => role(e) === "button").map((b) => name(b, doc));
  assert.ok(buttons.includes("Later shows") && !buttons.includes("Earlier shows"));
  assert.equal(L.positionLine({ ...big, offset: 50 }), "Shows 51 to 100 of 214");
  assert.equal(L.positionLine({ total: 1, limit: 50, offset: 0, rows: [ROW(1, "2026-08-14T19:30:00+05:30")] }), "Showing the only show in this period");
  const live = all(dash({ live: `Day, ${L.periodLine("2026-08-14", "day")}. ${L.figuresSentence(DASH)}` }), (e) => e.attrs["aria-live"] === "polite");
  assert.equal(text(live[0]), "Day, Friday 14 August 2026. Takings twenty-seven thousand eight hundred and thirty-three rupees and thirty-one paise. Occupancy twenty-nine point five per cent.");
});

// ---- S-RPT-17: the 429 wait is computed from Retry-After ----------------------------------------------------------
test("S-RPT-17: Retry-After 1 renders the singular and 2 the plural", async () => {
  const limited = (n) => async () => ({ status: 429, headers: { get: (h) => (h === "Retry-After" ? String(n) : null) }, json: async () => ({}) });
  await assert.rejects(getJson(limited(1), "/api/reports/dashboard?period=day"), { message: "Too many requests. Try again in 1 second." });
  await assert.rejects(getJson(limited(2), "/api/reports/dashboard?period=day"), { message: "Too many requests. Try again in 2 seconds." });
  const doc = dash({ error: "Too many requests. Try again in 2 seconds.", dash: null });
  assert.ok(text(doc).includes("Too many requests. Try again in 2 seconds."));
  assert.equal(figures(doc).length, 0); // the figures belong to the refused request and are cleared
});

// ---- S-RPT-02: nothing bare-UTC on screen --------------------------------------------------------------------------
test("S-RPT-02: no text node on /dashboard or /dashboard/audit is a bare UTC instant", () => {
  const audit = render(AuditScreen, { seed: { page: PAGE, rows: PAGE.rows } });
  for (const doc of [dash({}), audit]) assert.deepEqual(textNodes(doc).filter((t) => BARE_UTC.test(t)), []);
});

// ---- S-RPT-21: the change log ----------------------------------------------------------------------------------------
const ACTIONS = ["hall.renamed", "screen.deactivated"]; // any strings: the screen types no vocabulary of its own
const PAGE = {
  rows: [{ id: 31, occurred_at: "2026-08-12T15:40:00+05:30", actor_user_id: 1, actor_email: "admin-a@example.invalid", actor_role: "admin",
    action: "hall.renamed", entity_type: "showtime", entity_id: 101, before: { base_price_paise: 25000 }, after: { base_price_paise: 30000 } }],
  next_cursor: null, available_actions: ACTIONS,
  available_actors: [{ actor_user_id: 1, actor_email: "admin-a@example.invalid" }, { actor_user_id: 4, actor_email: "admin-b@example.invalid" }],
};

test("S-RPT-21: both selects come from the response, any-options first, six column headers, values verbatim", () => {
  const doc = render(AuditScreen, { seed: { page: PAGE, rows: PAGE.rows, live: A.countLine(1) } });
  const [action, actor] = all(doc, (e) => role(e) === "combobox");
  assert.deepEqual([name(action, doc), name(actor, doc)], ["Action", "Administrator"]);
  assert.deepEqual(all(action, (e) => e.tag === "option").map((o) => o.attrs.value), ["", ...ACTIONS]);
  assert.deepEqual(all(actor, (e) => e.tag === "option").map((o) => o.attrs.value), ["", "1", "4"]);
  assert.deepEqual([text(all(action, (e) => e.tag === "option")[0]), text(all(actor, (e) => e.tag === "option")[0])], ["Any action", "Any administrator"]);
  assert.deepEqual(all(doc, (e) => e.tag === "th").map(text), ["When", "Who", "Action", "Record", "Before", "After"]);
  const t = text(doc);
  assert.ok(t.includes("base_price_paise") && t.includes("25000") && t.includes("30000"));
  assert.ok(!t.includes("₹250.00") && !t.includes("₹300.00"));
  const rowText = text(all(doc, (e) => e.tag === "tbody")[0]);
  assert.ok(rowText.includes("12 Aug 2026, 3:40 pm") && !rowText.includes("15:40") && !rowText.includes("+05:30"));
  assert.equal(textNodes(doc).filter((n) => n === "All dates and times are Asia/Kolkata.").length, 1);
  assert.ok(t.includes("That is the oldest change in this period."));
  assert.equal(text(all(doc, (e) => e.attrs["aria-live"] === "polite")[0]), "1 change.");
});

test("S-RPT-21: an empty option set renders the any option alone with the help lines, nothing disabled", () => {
  const empty = { rows: [], next_cursor: null, available_actions: [], available_actors: [] };
  const doc = render(AuditScreen, { seed: { page: empty, rows: [] } });
  const selects = all(doc, (e) => role(e) === "combobox");
  assert.deepEqual(selects.map((s) => all(s, (e) => e.tag === "option").length), [1, 1]);
  assert.ok(selects.every((s) => !("disabled" in s.attrs)));
  assert.ok(text(doc).includes("Nothing was changed in this period.") && text(doc).includes("Nobody changed anything in this period."));
});

test("S-RPT-21: the request, the drop-and-announce rule and the count line", async () => {
  assert.equal(A.auditUrl(A.NO_FILTERS), "/api/reports/audit");
  assert.equal(A.auditUrl({ ...A.NO_FILTERS, from: "2026-08-12", to: "2026-08-12" }), "/api/reports/audit?from=2026-08-12&to=2026-08-12");
  const chosen = { ...A.NO_FILTERS, action: "hall.renamed", actor: "4" };
  const narrowed = { ...PAGE, available_actions: ["screen.deactivated"], available_actors: [PAGE.available_actors[0]] };
  const { filters, notes } = A.reconcile(chosen, narrowed);
  assert.deepEqual([filters.action, filters.actor], ["", ""]);
  assert.deepEqual(notes, ["The action filter was cleared. No change of that kind was recorded in this period.",
    "The administrator filter was cleared. That account made no changes in this period."]);
  assert.deepEqual(A.reconcile(chosen, PAGE).notes, []);
  assert.deepEqual([A.countLine(0), A.countLine(1), A.countLine(12)], ["0 changes.", "1 change.", "12 changes."]);
  const calls = [];
  const get = async (url) => { calls.push(url); return { status: 200, headers: { get: () => null }, json: async () => PAGE }; };
  await A.load(get, A.NO_FILTERS);
  await A.load(get, chosen, 30);
  assert.ok(calls.length === 2 && calls.every((u) => u.startsWith("/api/reports/audit")));
});

test("S-RPT-21: a manager reaching the route sees the refusal alone", () => {
  const doc = render(AuditScreen, { seed: { forbidden: true } });
  assert.equal(text(doc), "This page is for administrators.");
  assert.equal(all(doc, (e) => role(e) === "combobox" || e.tag === "table").length, 0);
});

test("S-RPT-20 (attribute half): the dashboard's tab stops, in document order", () => {
  const doc = dash({ scope: ADMIN, dash: { ...DASH, screen_ids: [1, 2, 3, 4, 5, 6] } });
  const stops = tabbable(doc).map((e) => (e.attrs.tabindex === "0" && e.tag === "div" ? "[per-show scroll]" : name(e, doc)));
  assert.deepEqual(stops.slice(0, 5), ["Day", "Previous day", "Next day", "Hall", "Change log"]);
  assert.deepEqual(stops.slice(5, 11).map((n) => n.split(",")[0]), ["Film", "Shows", "Seats sold", "Capacity", "Occupancy", "Takings"]);
  assert.deepEqual(stops.slice(11), ["[per-show scroll]"]);
});

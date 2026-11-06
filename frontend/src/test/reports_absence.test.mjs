// The reporting screens' ABSENCE clauses (S-RPT-02, -13, -17, -18, -21, S-SCP-16): sweeps over the source and over the
// rendered screens. Kept outside frontend/src/features/reports on purpose: a test that names the forbidden words would
// otherwise be the one hit in the very directory it sweeps.
// Run: node --test "frontend/src/test/*.test.mjs"
import assert from "node:assert/strict";
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { test } from "node:test";
import { fileURLToPath } from "node:url";
import { CONTROL_ROLES, all, atUrl, load, name, render, role } from "./render.mjs";

const SRC = fileURLToPath(new URL("..", import.meta.url));

/** rg -n PATTERN DIR: every matching line under DIR (fails if DIR is missing, as rg exits 2). */
function rg(pattern, dir) {
  const root = join(SRC, dir);
  assert.ok(statSync(root).isDirectory(), `${dir} does not exist - the sweep would check nothing`);
  const hits = [];
  const walk = (d) => {
    for (const f of readdirSync(d)) {
      const p = join(d, f);
      if (statSync(p).isDirectory()) walk(p);
      else readFileSync(p, "utf8").split("\n").forEach((line, i) => pattern.test(line) && hits.push(`${p}:${i + 1}: ${line.trim()}`));
    }
  };
  walk(root);
  return hits;
}

test("source sweeps: no export path, no bare-UTC field, no typed wait, no client clock, no typed vocabulary", () => {
  assert.deepEqual(rg(/download|Blob|createObjectURL|Content-Disposition|text\/csv|xlsx/, "features/reports"), []); // S-RPT-13
  assert.deepEqual(rg(/@media print/, "features/reports"), []); // S-RPT-13
  assert.deepEqual(rg(/_utc/, "features/reports"), []); // S-RPT-02
  assert.deepEqual(rg(/30 seconds/, "features/reports"), []); // S-RPT-17
  assert.deepEqual(rg(/getTimezoneOffset|toISOString|Date\.now\(/, "features/reports/dashboard"), []); // S-RPT-18
  assert.deepEqual(rg(/showtime\.base_price_changed|movie\.published/, "."), []); // S-RPT-21
  assert.deepEqual(rg(/download|Blob|createObjectURL|text\/csv|xlsx/, "features/reports/audit"), []); // S-RPT-21
});

atUrl("/dashboard");
const { App } = await load("/src/App.tsx");
const { DashboardScreen } = await load("/src/features/reports/dashboard/DashboardScreen.tsx");
const { AuditScreen } = await load("/src/features/reports/audit/AuditScreen.tsx");

const SCOPE = { role: "admin", scope_empty: false, all_halls: true, today: "2026-08-14",
  screens: [{ screen_id: 3, screen_name: "Hall 3", is_active: true }] };
const DASH = { period: "day", scope_empty: false, screen_ids: [3], takings_paise: 2783331, seats_sold: 109, capacity: 370,
  occupancy_pct: 29.5, shows: 2, films: [{ movie_id: 1, title: "DEMO MOVIE 01", shows: 2, seats_sold: 109, capacity: 370,
    occupancy_pct: 29.5, takings_paise: 2783331 }], films_truncated: true };
const SHOWS = { total: 120, limit: 50, offset: 50, rows: [{ showtime_id: 101, starts_at: "2026-08-14T19:30:00+05:30", screen_id: 3,
  screen_name: "Hall 3", movie_id: 1, title: "DEMO MOVIE 01", seats_sold: 97, capacity: 150, occupancy_pct: 64.7, takings_paise: 2483331,
  has_started: false }] };
const PAGE = { rows: [{ id: 31, occurred_at: "2026-08-12T15:40:00+05:30", actor_user_id: 1, actor_email: "admin-a@example.invalid",
  actor_role: "admin", action: "hall.renamed", entity_type: "showtime", entity_id: 101, before: { base_price_paise: 25000 },
  after: { base_price_paise: 30000 } }], next_cursor: 30, available_actions: ["hall.renamed"],
  available_actors: [{ actor_user_id: 1, actor_email: "admin-a@example.invalid" }] };

function screens() {
  const out = [];
  for (const path of ["/dashboard", "/dashboard/audit"]) {
    atUrl(path);
    out.push([`${path} (route table)`, render(App)]);
  }
  out.push(["/dashboard (every control rendered)", render(DashboardScreen, {
    seed: { query: { period: "day", anchor: null, screenId: "", offset: 50 }, scope: SCOPE, dash: DASH, shows: SHOWS } })]);
  out.push(["/dashboard/audit (every control rendered)", render(AuditScreen, { seed: { page: PAGE, rows: PAGE.rows } })]);
  return out;
}

test("S-SCP-16 / S-RPT-21: no control on a dashboard route is named for an export, and no a[download]", () => {
  const banned = /export|download|csv|excel|spreadsheet|pdf|save as|copy all/i;
  for (const [label, doc] of screens()) {
    const controls = all(doc, (e) => CONTROL_ROLES.has(role(e)));
    assert.ok(controls.length >= 2, `${label}: not vacuous`);
    assert.deepEqual(controls.map((c) => name(c, doc)).filter((n) => banned.test(n)), [], label);
    assert.equal(all(doc, (e) => e.tag === "a" && "download" in e.attrs).length, 0, label);
  }
});

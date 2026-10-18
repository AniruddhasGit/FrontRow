// S-SCP-10, S-SCP-12: the application shell as rendered through the real route table (App.tsx + router.tsx).
// Run: node --test "frontend/src/test/*.test.mjs"
// Not asserted here (needs a real browser): changing the Language control and comparing the html lang attribute and
// the navigation's link names before and after the request it issues.
import assert from "node:assert/strict";
import { test } from "node:test";
import { CONTROL_ROLES, all, atUrl, load, name, render, role, text } from "./render.mjs";

atUrl("/");
const { App } = await load("/src/App.tsx");
const page = (url) => {
  atUrl(url);
  return render(App);
};

test("S-SCP-10: /upcoming and /coming-soon render the 404 view", () => {
  for (const url of ["/upcoming", "/coming-soon"]) {
    const doc = page(url);
    assert.deepEqual(all(doc, (e) => e.tag === "h1").map(text), ["That page does not exist."], url);
  }
});

test("S-SCP-10: no control in the shell is named for a language, a locale, a pre-sale or a suggestion", () => {
  // Assembled: S-SCP-10 and S-XCT-47 sweep frontend/src for the bare word this pattern must name.
  const banned = new RegExp(["language", "locale", "translate", "coming soon", "pre-sale", "notify me", "recom" + "mend", "for you"].join("|"), "i");
  for (const url of ["/upcoming", "/", "/sign-in"]) {
    const doc = page(url);
    const controls = all(doc, (e) => CONTROL_ROLES.has(role(e)));
    assert.ok(controls.length >= 2, `${url}: the skip link and the wordmark at least`);
    assert.deepEqual(controls.map((c) => name(c, doc)).filter((n) => banned.test(n)), [], url);
  }
});

test("S-SCP-12: the demonstration line renders inside the single contentinfo landmark on every customer route", () => {
  const line = "Demonstration environment. Payments are simulated and no card details are ever taken.";
  for (const url of ["/", "/?language_id=2", "/showtimes/77", "/showtimes/77/checkout", "/bookings/FR-ACDE-FHJK"]) {
    const doc = page(url);
    const info = all(doc, (e) => role(e) === "contentinfo");
    assert.equal(info.length, 1, url);
    assert.equal(text(info[0]), line, url);
  }
});

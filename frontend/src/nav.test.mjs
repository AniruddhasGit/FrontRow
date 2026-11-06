// SCR-XCT-05: each role sees exactly its links, in order; nothing for a guest; the current area; the address truncation.
// Run: node --test frontend/src/nav.test.mjs
import assert from "node:assert/strict";
import { test } from "node:test";
import { currentTo, navFor, shortEmail } from "./nav.ts";

const labels = (role) => navFor(role).map((l) => l.label);

test("each role sees exactly its links, in order, and a guest sees none", () => {
  assert.deepEqual(labels(null), []);
  assert.deepEqual(labels("customer"), ["My bookings"]);
  assert.deepEqual(labels("manager"), ["Dashboard", "My bookings"]);
  assert.deepEqual(labels("admin"), ["Dashboard", "Change log", "Films", "Showtimes", "Pricing", "Halls", "Managers", "Lists", "My bookings"]);
  assert.ok(!labels("manager").includes("Change log"), "the change log is the admin's alone");
  assert.deepEqual(labels("staff"), []);
});

test("the current area is the longest matching link, and none off the nav", () => {
  const admin = navFor("admin");
  assert.equal(currentTo(admin, "/dashboard/audit"), "/dashboard/audit");
  assert.equal(currentTo(admin, "/dashboard"), "/dashboard");
  assert.equal(currentTo(admin, "/admin/movies/12"), "/admin/movies");
  assert.equal(currentTo(admin, "/"), null);
});

test("the address truncates past 24 characters", () => {
  assert.equal(shortEmail("asha@example.com"), "asha@example.com");
  assert.equal(shortEmail("customer-12@demo.frontrow.invalid"), "customer-12@demo.frontr…");
});

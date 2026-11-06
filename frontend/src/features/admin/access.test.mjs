// S-ADM-30: the Admin access list offers Remove on every granted email but the signed-in admin's own, compared the
// way the server compares (trimmed, case-insensitive); the add form's field has a label.
// Run: node --test "frontend/src/features/admin/*.test.mjs"
import assert from "node:assert/strict";
import { test } from "node:test";
import { CONTROL_ROLES, all, atUrl, load, name, render, role } from "../../test/render.mjs";

atUrl("/admin/access");
const { AccessScreen, sameEmail } = await load("/src/features/admin/AccessScreen.tsx");

test("own email shows no Remove; every other one does; the email field is labelled", () => {
  const doc = render(AccessScreen, { seed: { me: "Me@Example.com", grants: [{ id: 1, email: "ada@example.com" }, { id: 2, email: "me@example.com" }] } });
  const names = all(doc, (e) => CONTROL_ROLES.has(role(e))).map((e) => name(e, doc));
  assert.ok(names.includes("Remove ada@example.com"), names.join(" | "));
  assert.ok(!names.some((n) => n.includes("me@example.com")), names.join(" | "));
  assert.ok(names.includes("Email address") && names.includes("Give admin access"), names.join(" | "));
});

test("addresses compare trimmed and case-insensitively", () => {
  assert.equal(sameEmail(" Ada@Example.COM ", "ada@example.com"), true);
  assert.equal(sameEmail("ada@example.com", "bea@example.com"), false);
});

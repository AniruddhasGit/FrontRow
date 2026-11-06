// SCR-ACC-02 / SCR-ACC-03 (S-ACC-07, S-ACC-08): the reset screens' RENDERED markup (frontend/src/test/render.mjs).
// Run: node --test "frontend/src/features/account/*.test.mjs"
// Not asserted here (needs a real browser): the submit itself, focus movement, the URL replace after success.
import assert from "node:assert/strict";
import { test } from "node:test";
import { all, atUrl, load, markup, name, render, role, text } from "../../test/render.mjs";

atUrl("/account/reset/confirm");
const { ResetConfirmScreen, ResetRequestScreen, tokenFrom } = await load("/src/features/account/ResetScreens.tsx");

const TOKEN = "Q".repeat(21) + "-_" + "z".repeat(20);

test("the token is read from the URL fragment, never the query string", () => {
  assert.equal(tokenFrom(`#token=${TOKEN}`), TOKEN);
  assert.equal(tokenFrom(""), null);
  assert.equal(tokenFrom("#other=1"), null);
});

test("SCR-ACC-03: one password field, the help text, the action, and the token rendered nowhere", () => {
  const doc = render(ResetConfirmScreen, { token: TOKEN });
  const page = text(doc);
  assert.match(page, /Set a new password/);
  assert.equal(all(doc, (e) => e.tag === "input").length, 1);
  assert.ok(all(doc, (e) => role(e) === "button").some((b) => name(b, doc) === "Set new password"));
  assert.match(page, /At least 12 characters\. No numbers or symbols required\. Maximum 72 bytes\./);
  assert.ok(!markup(ResetConfirmScreen, { token: TOKEN }).includes(TOKEN), "not in text, not in an attribute");
});

test("SCR-ACC-03 token error: the server's sentence, the request-again link, and no password field", () => {
  const sentence = "That reset link has already been used. Request a new one.";
  const doc = render(ResetConfirmScreen, { token: TOKEN, seed: { tokenError: sentence } });
  assert.match(text(doc), new RegExp(sentence.replace(/\./g, "\\.")));
  assert.equal(all(doc, (e) => e.tag === "input").length, 0);
  assert.ok(all(doc, (e) => e.tag === "a").some((a) => name(a, doc) === "Request a new link"));
});

test("SCR-ACC-02: the confirmation panel renders the 202 body's sentence, so its minutes are the server's", () => {
  const ten = "If that email address has an account, a reset link is on its way to it. The link works once and expires in 10 minutes.";
  const doc = render(ResetRequestScreen, { seed: { sent: ten } });
  assert.match(text(doc), /expires in 10 minutes\./);
  assert.equal(all(doc, (e) => e.tag === "input").length, 0); // the form is replaced: no second send control
  const form = render(ResetRequestScreen, {});
  assert.ok(all(form, (e) => role(e) === "button").some((b) => name(b, form) === "Send a reset link"));
});

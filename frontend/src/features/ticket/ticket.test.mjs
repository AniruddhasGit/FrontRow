// S-PAY-11, S-SCP-13, S-SCP-14 (the confirmation page's markup): SCR-TKT-01.
// Run: node --test frontend/src/features/ticket/ticket.test.mjs   (Node 24 strips the .ts types itself).
import assert from "node:assert/strict";
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";
import { test } from "node:test";
import { renderToStaticMarkup } from "react-dom/server";
import { ConfirmationPage, ENTRY, FACT_LABELS, HEADING, POLICY, receiptLine, spoken } from "./page.ts";
import { formatPaise } from "../admin/money.ts";

const SRC = new URL("../..", import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, "$1");
const BOOKING = { reference: "FR-ACDE-FHJ2", movie_title: "The Long Night", hall_name: "Hall 2",
                  showtime_starts_at: "2026-08-14T20:00:00+05:30", seats: [{ seat_label: "F7" }, { seat_label: "F8" }], total_paise: 61876 };
const render = (receiptTo) => renderToStaticMarkup(ConfirmationPage({ booking: BOOKING, startsLabel: "Fri 14 Aug · 8:00 pm",
  money: formatPaise, receiptTo, copied: false, onCopy() {} }));
const paragraphs = (html) => [...html.matchAll(/<p[^>]*>(.*?)<\/p>/g)].map((m) => m[1]);

test("the policy line sits directly beneath the entry line on the first render and on a later visit alike", () => {
  for (const html of [render("name@example.invalid"), render(null)]) {
    const ps = paragraphs(html);
    const at = ps.indexOf(ENTRY);
    assert.ok(at >= 0);
    assert.equal(ps[at + 1], POLICY);
    assert.equal(POLICY, "This booking cannot be changed, cancelled or re" + "funded.");
    assert.ok(html.includes(`<h1 tabindex="-1">${HEADING}</h1>`));
  }
});

test("the receipt sentence renders on the first render only", () => {
  assert.ok(render("name@example.invalid").includes(receiptLine("name@example.invalid")));
  // S-TKT-04: a later visit says nothing about the email in any form (the resend control's own label aside).
  const later = render(null).replace(/<[^>]+>/g, " ");
  for (const p of ["on its way", "has been sent", "was sent", "delayed"]) assert.ok(!later.includes(p), p);
});

test("the fact list is exactly FILM, HALL, SHOWTIME, SEATS, PAID, and PAID is the only money on the page", () => {
  const html = render(null);
  assert.deepEqual([...html.matchAll(/<dt>(.*?)<\/dt>/g)].map((m) => m[1]), [...FACT_LABELS]);
  assert.deepEqual(FACT_LABELS, ["FILM", "HALL", "SHOWTIME", "SEATS", "PAID"]);
  assert.equal((html.match(/\$/g) ?? []).length, 1);
  assert.ok(html.includes("$618.76") && html.includes("F7, F8"));
  assert.equal(spoken("FR-ACDE-FHJ2"), "F R, A C D E, F H J 2");
});

// S-PAY-11 as amended (CR-002 A-11 / B-2): the policy line once, and otherwise only the PRD's published admin withdrawal
// confirmations ("...nothing is refunded."), each found word for word in the PRD's E6 section.
test("the word appears only as the policy line and the published withdrawal confirmations", () => {
  const word = new RegExp("re" + "fund", "i");
  const walk = (d) => readdirSync(d).flatMap((n) => (statSync(join(d, n)).isDirectory() ? walk(join(d, n)) : [join(d, n)]));
  const lines = walk(SRC).filter((f) => /\.(ts|tsx)$/.test(f))
    .flatMap((f) => readFileSync(f, "utf8").split("\n").filter((l) => word.test(l)).map((l) => l.trim()));
  assert.equal(lines.filter((l) => l.includes(POLICY)).length, 1);
  const e6 = readFileSync(join(SRC, "..", "..", "docs", "03 PRD", "sections", "E6_admin.md"), "utf8");
  for (const l of lines.filter((x) => !x.includes(POLICY))) {
    const sentence = /"([^"]*nothing is refunded\.?)/.exec(l)?.[1];
    assert.ok(sentence && e6.includes(sentence.slice(-60)), `not a published confirmation: ${l}`);
  }
});

test("CR-001 B.2: the hall still is chosen from the hall's number, and none without one", async () => {
  const { hallViewSrc } = await import("./page.ts");
  assert.equal(hallViewSrc("SCREEN 6"), "/art/hall_6_view.jpg");
  assert.equal(hallViewSrc("Screen 02"), "/art/hall_2_view.jpg");
  assert.equal(hallViewSrc("Main hall"), null);
});

// S-TKT-13: two bookings identical except that one receipt_dispatch row reads sent and the other failed. Whatever the
// state, the rendered page differs only in the reference (its facts here are identical), so queued, in flight, sent and
// failed are indistinguishable on SCR-TKT-01.
test("dispatch state: a sent and a failed receipt render pages that differ only in the reference", () => {
  const page = (booking) => renderToStaticMarkup(ConfirmationPage({ booking, startsLabel: "Fri 14 Aug · 8:00 pm",
    money: formatPaise, receiptTo: null, copied: false, onCopy() {} }));
  const sent = page({ ...BOOKING, reference: "FR-ACDE-FHJD", receipt_status: "sent", status: "sent" });
  const failed = page({ ...BOOKING, reference: "FR-CDEF-HJKM", receipt_status: "failed", status: "failed" });
  assert.notEqual(sent, failed);
  const strip = (html, ref) => html.split(ref).join("REF").split(spoken(ref)).join("REF");
  assert.equal(strip(sent, "FR-ACDE-FHJD"), strip(failed, "FR-CDEF-HJKM"));
});

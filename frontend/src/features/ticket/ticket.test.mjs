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
  assert.ok(!/receipt/i.test(render(null).replace(/<[^>]+>/g, " ")));
});

test("the fact list is exactly FILM, HALL, SHOWTIME, SEATS, PAID, and PAID is the only money on the page", () => {
  const html = render(null);
  assert.deepEqual([...html.matchAll(/<dt>(.*?)<\/dt>/g)].map((m) => m[1]), [...FACT_LABELS]);
  assert.deepEqual(FACT_LABELS, ["FILM", "HALL", "SHOWTIME", "SEATS", "PAID"]);
  assert.equal((html.match(/\$/g) ?? []).length, 1);
  assert.ok(html.includes("$618.76") && html.includes("F7, F8"));
  assert.equal(spoken("FR-ACDE-FHJ2"), "F R, A C D E, F H J 2");
});

test("the word is named exactly once in frontend/src: the policy line", () => {
  const word = new RegExp("re" + "fund", "i");
  const walk = (d) => readdirSync(d).flatMap((n) => (statSync(join(d, n)).isDirectory() ? walk(join(d, n)) : [join(d, n)]));
  const lines = walk(SRC).filter((f) => /\.(ts|tsx)$/.test(f))
    .flatMap((f) => readFileSync(f, "utf8").split("\n").filter((l) => word.test(l)).map((l) => l.trim()));
  assert.equal(lines.length, 1);
  assert.ok(lines[0].includes(POLICY));
});

test("CR-001 B.2: the hall still is chosen from the hall's number, and none without one", async () => {
  const { hallViewSrc } = await import("./page.ts");
  assert.equal(hallViewSrc("SCREEN 6"), "/art/hall_6_view.jpg");
  assert.equal(hallViewSrc("Screen 02"), "/art/hall_2_view.jpg");
  assert.equal(hallViewSrc("Main hall"), null);
});

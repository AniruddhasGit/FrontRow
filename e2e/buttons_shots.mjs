// Close-up screenshots of the button system on its main pages (owner: "each and every element ... premium").
// Run: cd e2e && node buttons_shots.mjs
import fs from "node:fs";
import { BASE, launch, openShowtime, signedIn } from "./lib.mjs";

const out = "evidence/buttons";
fs.mkdirSync(out, { recursive: true });
const browser = await launch();
const g = await (await browser.newContext({ viewport: { width: 1440, height: 900 } })).newPage();
await g.goto(BASE + "/films", { waitUntil: "networkidle" });
const st = await openShowtime(g);
for (const [p, n, wait] of [["/", "landing", 5000], [`/showtimes/${st}`, "seat", 6000], ["/sign-in", "signin", 1200], ["/films", "films", 1200]]) {
  await g.goto(BASE + p, { waitUntil: "networkidle" });
  await g.waitForTimeout(wait);
  await g.screenshot({ path: `${out}/${n}.png` });
}
const { page: c } = await signedIn(browser, "e2e-pay-1@example.com");
await c.goto(BASE + "/bookings", { waitUntil: "networkidle" });
const ref = await c.evaluate(async () => { const b = await (await fetch("/api/me/bookings")).json(); return (b.upcoming?.[0] ?? b.past?.[0])?.reference; });
await c.goto(BASE + `/bookings/${ref}`, { waitUntil: "networkidle" });
await c.waitForTimeout(1200);
await c.screenshot({ path: `${out}/ticket.png` });
const { page: a } = await signedIn(browser, "e2e-adm-1@example.com");
for (const [p, n] of [["/dashboard", "dashboard"], ["/admin/halls", "halls"]]) {
  await a.goto(BASE + p, { waitUntil: "networkidle" });
  await a.waitForTimeout(1200);
  await a.screenshot({ path: `${out}/${n}.png` });
}
console.log("ok");
await browser.close();

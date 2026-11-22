// A screenshot tour of every page, desktop and phone, for the design audit. Run: cd e2e && node tour.mjs <folder>
import fs from "node:fs";
import { BASE, launch, openShowtime, signedIn } from "./lib.mjs";

const out = `evidence/${process.argv[2] ?? "tour"}`;
fs.mkdirSync(out, { recursive: true });
const browser = await launch();
const errors = [];
async function shoot(page, path, name, wait = 1500, full = true) {
  await page.goto(BASE + path, { waitUntil: "networkidle" }).catch(() => null);
  await page.waitForTimeout(wait);
  await page.screenshot({ path: `${out}/${name}.png`, fullPage: full });
}
for (const [w, h, tag] of [[1440, 900, "d"], [390, 844, "m"]]) {
  const guest = await (await browser.newContext({ viewport: { width: w, height: h } })).newPage();
  guest.on("pageerror", (e) => errors.push(`${tag} guest ${e.message}`));
  const st = await (async () => { await guest.goto(BASE + "/films"); return openShowtime(guest); })();
  const film = await guest.evaluate(async () => (await (await fetch("/api/movies")).json()).movies[0]?.id);
  await shoot(guest, "/", `${tag}_01_landing`, 6000, false);
  await shoot(guest, "/films", `${tag}_02_films`);
  await shoot(guest, `/movies/${film}`, `${tag}_03_movie`);
  await shoot(guest, `/showtimes/${st}`, `${tag}_04_seatmap`, 9000);
  await shoot(guest, "/sign-in", `${tag}_05_signin`);
  await shoot(guest, "/nope", `${tag}_06_404`);
  const { page: cust } = await signedIn(browser, "e2e-pay-1@example.com", undefined, { width: w, height: h });
  cust.on("pageerror", (e) => errors.push(`${tag} cust ${e.message}`));
  await shoot(cust, "/bookings", `${tag}_07_bookings`);
  const ref = await cust.evaluate(async () => (await (await fetch("/api/me/bookings")).json()).upcoming?.[0]?.reference
    ?? (await (await fetch("/api/me/bookings")).json()).past?.[0]?.reference);
  if (ref) await shoot(cust, `/bookings/${ref}`, `${tag}_08_ticket`);
  const { page: adm } = await signedIn(browser, "e2e-adm-1@example.com", undefined, { width: w, height: h });
  for (const [p, n] of [["/dashboard", "09_dashboard"], ["/admin/movies", "10_admin_films"], ["/admin/showtimes", "11_admin_showtimes"],
    ["/admin/halls", "12_admin_halls"], ["/dashboard/audit", "13_audit"]]) await shoot(adm, p, `${tag}_${n}`);
}
console.log(JSON.stringify({ out, errors }));
await browser.close();

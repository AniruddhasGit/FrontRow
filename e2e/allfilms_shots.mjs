// Screenshots of the landing's "All films" motion (owner, 2026-11-22): the rail expanding, then /films.
// Run: cd e2e && node allfilms_shots.mjs
import { BASE, launch } from "./lib.mjs";

const browser = await launch();
const page = await (await browser.newContext({ viewport: { width: 1440, height: 900 } })).newPage();
const errors = [];
page.on("pageerror", (e) => errors.push(e.message));
await page.goto(BASE + "/", { waitUntil: "networkidle" });
await page.waitForTimeout(5000);
await page.getByRole("button", { name: "All films" }).click();
for (const [ms, name] of [[300, "a_expanding"], [500, "b_expanded"], [500, "c_films"], [1500, "d_settled"]]) {
  await page.waitForTimeout(ms);
  await page.screenshot({ path: `evidence/allfilms_${name}.png` });
}
console.log(JSON.stringify({ url: page.url(), errors }));
await browser.close();

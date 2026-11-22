// The screen lighting the room (owner, 2026-11-22): the landing in four films' halls, each lit by its own still.
// Run: cd e2e && node glow_shots.mjs
import { BASE, launch } from "./lib.mjs";
const b = await launch();
const p = await (await b.newContext({ viewport: { width: 1440, height: 900 } })).newPage();
const errors = [];
p.on("pageerror", (e) => errors.push(e.message));
p.on("console", (m) => m.type() === "error" && /shader|WebGL|GLSL/i.test(m.text()) && errors.push(m.text().slice(0, 300)));
await p.goto(BASE + "/", { waitUntil: "networkidle" });
await p.waitForTimeout(7000);
for (const title of ["Apartment 4B", "The Last Stage", "Neon Reverie", "Outpost 77"]) {
  await p.getByRole("button", { name: new RegExp(title) }).first().click();
  await p.waitForTimeout(9000);
  await p.screenshot({ path: `evidence/glow_${title.replace(/\W+/g, "_")}.png` });
}
console.log(JSON.stringify(errors));
await b.close();

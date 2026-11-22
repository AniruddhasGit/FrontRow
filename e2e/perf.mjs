// How heavy the landing is while it sits idle: main-thread busy time, frames painted, and canvases alive.
// Run: cd e2e && node perf.mjs [label]   (the local stack and Vite on :5173). Headless Chromium renders WebGL in
// software, so the absolute numbers are worse than a real GPU; compare runs with each other, not with a laptop.
import { BASE, launch } from "./lib.mjs";

const label = process.argv[2] ?? "run";
const browser = await launch();
const page = await (await browser.newContext({ viewport: { width: 1440, height: 900 } })).newPage();
const cdp = await page.context().newCDPSession(page);
await cdp.send("Performance.enable");
const t0 = Date.now();
await page.goto(BASE + "/", { waitUntil: "networkidle" });
const loadMs = Date.now() - t0;
await page.waitForTimeout(6000); // settle: the hall has loaded and the rail has popped in
const metric = async () => Object.fromEntries((await cdp.send("Performance.getMetrics")).metrics.map((m) => [m.name, m.value]));
const a = await metric();
const frames = await page.evaluate(() => new Promise((done) => {
  let n = 0, long = 0, last = performance.now();
  const end = last + 5000;
  const tick = (t) => { n++; if (t - last > 34) long++; last = t; t < end ? requestAnimationFrame(tick) : done({ n, long }); };
  requestAnimationFrame(tick);
}));
const b = await metric();
const canvases = await page.evaluate(() => document.querySelectorAll("canvas").length);
const bytes = await page.evaluate(() => performance.getEntriesByType("resource").reduce((s, r) => s + (r.transferSize || 0), 0));
console.log(JSON.stringify({
  label, loadMs, canvases, transferredMB: +(bytes / 1048576).toFixed(2),
  idle5s_mainThreadBusyMs: Math.round((b.TaskDuration - a.TaskDuration) * 1000),
  idle5s_scriptMs: Math.round((b.ScriptDuration - a.ScriptDuration) * 1000),
  idle5s_frames: frames.n, idle5s_longFrames: frames.long,
}));
await browser.close();

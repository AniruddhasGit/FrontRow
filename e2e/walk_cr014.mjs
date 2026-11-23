// CR-014: the corridor in the hall - one live 3D hall from the film page to the seats, recorded on video
// (evidence/cr014/<run>/video.webm, then cut into frames with ffmpeg and read in order). Local stack + Vite.
//   node walk_cr014.mjs desk   - 1440x900: film page cold -> hall live -> hover -> press -> walk -> seat page;
//                                Back to the corridor; a warm repeat (press again)
//   node walk_cr014.mjs phone  - 390x844: the same, and no sideways scroll on either page
//   node walk_cr014.mjs slow   - /halls/* delayed ~4 s: the picture stands in and nothing moves until the hall is ready
//   node walk_cr014.mjs fail   - /halls/hallN.json answers 404: the picture stays and the door still reaches the seats
//   node walk_cr014.mjs seat   - the seat page loaded cold from its URL: the readiness gate, then its own arrival
//   node walk_cr014.mjs reduced - prefers-reduced-motion: no walk, the door goes straight to the seat page
//   node walk_cr014.mjs hover  - stills of the door at rest, hovered (peek), left again, and focused from the keyboard
// Add `stub` to give a hall file without a corridor a stand-in one (the Blender half not landed yet).
// One browser at a time; a fresh context per run, so every run is cold.
import assert from "node:assert/strict";
import fs from "node:fs";
import { BASE, launch } from "./lib.mjs";

const [mode = "desk", ...flags] = process.argv.slice(2);
const stub = flags.includes("stub");
const ROOT = new URL("./evidence/cr014/", import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, "$1");
const HALL = Number(process.env.HALL || 1); // HALL=n: walk into SCREEN n
const EV = `${ROOT}${mode}${flags.includes("phone") ? "-phone" : ""}${HALL > 1 ? `-hall${HALL}` : ""}/`;
fs.rmSync(EV, { recursive: true, force: true });
fs.mkdirSync(EV, { recursive: true });
const say = (...a) => console.log("-", ...a);
const phone = mode === "phone" || flags.includes("phone");
const viewport = phone ? { width: 390, height: 844 } : { width: 1440, height: 900 };

const browser = await launch();
const ctx = await browser.newContext({ viewport, reducedMotion: mode === "reduced" ? "reduce" : "no-preference", recordVideo: { dir: EV, size: viewport }, deviceScaleFactor: 1, hasTouch: phone, isMobile: phone });
const page = await ctx.newPage();
const t0 = Date.now();
const marks = [];
const mark = (what) => {
  const ms = Date.now() - t0;
  marks.push({ ms, what });
  say(`${(ms / 1000).toFixed(2)} s  ${what}`);
};
page.on("console", (m) => (m.type() === "error" || m.type() === "warning") && say("console", m.type(), m.text().slice(0, 200)));
page.on("pageerror", (e) => say("pageerror", e.message));

// the stand-in corridor: in front of the hall's ENTRY door (its walk-in's first pose), looking at it
if (stub) {
  await page.route(/\/halls\/hall\d+\.json$/, async (route) => {
    const r = await route.fetch();
    const m = await r.json();
    if (!m.corridor && m.intro?.length) {
      const d = m.intro[0];
      const dir = d.look.map((v, i) => v - d.eye[i]);
      const len = Math.hypot(...dir);
      const eye = d.eye.map((v, i) => v - (dir[i] / len) * 5);
      m.corridor = { eye, look: d.eye, door: { node: "corr_leaf", ajar: 10, peek: 22, wide: 92, sign: 1 } };
      m.enter = [{ eye, look: d.eye }, ...m.intro];
    }
    await route.fulfill({ response: r, json: m });
  });
}
if (mode === "slow") {
  await page.route(/\/halls\//, async (route) => {
    await new Promise((r) => setTimeout(r, 4000));
    await route.fallback();
  });
}

/** A showing film with an open show in SCREEN $HALL (default 1). */
async function pick() {
  await page.goto(BASE + "/films");
  return page.evaluate(async (hall) => {
    const j = async (p) => (await fetch(p)).json();
    const out = [];
    for (const f of (await j("/api/movies")).movies.filter((m) => !m.coming_soon)) {
      let day = await j(`/api/showtimes?movie_id=${f.id}`);
      if (!day.showtimes.some((s) => !s.sales_closed) && day.next_date_with_showtimes) day = await j(`/api/showtimes?movie_id=${f.id}&date=${day.next_date_with_showtimes}`);
      for (const s of day.showtimes.filter((x) => !x.sales_closed)) out.push({ film: f.id, title: f.title, date: day.date, show: s.id, screen: s.screen.name });
    }
    return out.find((o) => o.screen === `SCREEN ${hall}`) ?? out[0];
  }, HALL);
}
const target = await pick();
assert.ok(target, "an open showtime in the local data");
say("show", target.show, target.screen, "of", target.title);
const n = Number(/(\d+)$/.exec(target.screen)[1]);
if (mode === "fail") await page.route(new RegExp(`/halls/hall${n}\\.json$`), (r) => r.fulfill({ status: 404, body: "" }));
const filmUrl = `${BASE}/movies/${target.film}?date=${target.date}&show=${target.show}`;
const doorState = () => page.locator(".fr-corridor").getAttribute("data-door");
// frames the page actually drew: every gap over 50 ms between animation frames, timed from the press
const watchFrames = () => page.evaluate(() => {
  window.__gaps = [];
  window.__press = performance.now();
  let last = performance.now();
  const tick = (t) => {
    if (t - last > 50) window.__gaps.push([Math.round(last - window.__press), Math.round(t - last)]);
    last = t;
    if (performance.now() - window.__press < 9000) requestAnimationFrame(tick);
  };
  requestAnimationFrame(tick);
});
const frameGaps = () => page.evaluate(() => window.__gaps);
const sideways = () => page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);

async function filmPageToSeats(label) {
  const open = Date.now();
  if (label === "cold") {
    await page.goto("about:blank");
    mark("film page: open (cold)");
    await page.goto(filmUrl);
  }
  await page.locator(".fr-corridor").waitFor();
  let state = await doorState();
  if (mode === "slow") { // press while the hall is still loading: the press waits (queued), the picture stays still
    await page.waitForTimeout(2000);
    mark(`door state before the press: ${await doorState()}`);
    await page.locator(".fr-corridor-book").click();
    mark(`pressed while loading - door state: ${await doorState()}`);
    await page.waitForFunction(() => document.querySelector(".fr-corridor")?.getAttribute("data-door") === "flying", null, { timeout: 30000 });
    mark(`the walk starts - ${((Date.now() - open) / 1000).toFixed(2)} s after open`);
    await page.waitForURL(/\/showtimes\/\d+$/, { timeout: 20000 });
    mark("URL is the seat page");
    await page.waitForTimeout(1500);
    say("canvases on the seat page:", await page.locator("canvas").count());
    return {};
  }
  if (mode !== "fail") {
    await page.waitForFunction(() => document.querySelector(".fr-corridor")?.getAttribute("data-door") === "live", null, { timeout: 30000 });
    mark(`film page: corridor live (${label}) - ${((Date.now() - open) / 1000).toFixed(2)} s after open`);
    state = "live";
  } else {
    await page.waitForFunction(() => document.querySelector(".fr-corridor")?.getAttribute("data-door") === "fallback", null, { timeout: 30000 });
    mark("film page: fallback (no hall file) - the picture stays");
    state = "fallback";
  }
  if (phone) say("film page sideways scroll px:", await sideways());
  if (!phone) {
    await page.locator(".fr-corridor-door").hover();
    mark("hover the door");
    await page.waitForTimeout(900);
    await page.mouse.move(5, 5);
    await page.waitForTimeout(700);
  }
  await page.evaluate((l) => { const c = document.querySelector("canvas"); if (c) c.dataset.cr014 = `film-${l}`; }, label);
  await watchFrames();
  const pressed = Date.now();
  mark("press Book");
  await page.locator(".fr-corridor-book").click();
  await page.waitForURL(/\/showtimes\/\d+$/, { timeout: 20000 });
  const at = Date.now();
  mark(`URL is the seat page - ${((at - pressed) / 1000).toFixed(2)} s after the press`);
  await page.locator(".fr-seatmap-panel").waitFor();
  await page.waitForTimeout(1500);
  say("frame gaps over 50 ms after the press [at ms, gap ms]:", JSON.stringify(await frameGaps()));
  if (phone) say("seat page sideways scroll px:", await sideways());
  say("canvases on the seat page:", await page.locator("canvas").count(), "- tag:", await page.evaluate(() => document.querySelector("canvas")?.dataset.cr014 ?? "none (a new canvas)"));
  return { open, pressed, at, state };
}

if (mode === "desk" || mode === "phone" || mode === "slow" || mode === "fail" || mode === "reduced") {
  // the hall's canvas element on the film page, tagged, so the seat page can show it is the same one (not remounted)
  await filmPageToSeats("cold");
  if (mode === "desk" || mode === "phone") {
    await page.evaluate(() => { const c = document.querySelector("canvas"); if (c) c.dataset.cr014 = "seat"; });
    mark("Back");
    await page.locator(".fr-back").click();
    await page.waitForURL(/\/movies\//);
    await page.waitForFunction(() => document.querySelector(".fr-corridor")?.getAttribute("data-door") === "live", null, { timeout: 20000 });
    mark("film page again: corridor live");
    say("same canvas after Back:", await page.evaluate(() => document.querySelector("canvas")?.dataset.cr014 ?? "a new one"));
    await page.waitForTimeout(800);
    await filmPageToSeats("warm");
    say("same canvas after the warm walk:", await page.evaluate(() => document.querySelector("canvas")?.dataset.cr014 ?? "a new one"));
  }
}

if (mode === "hover") {
  await page.goto(filmUrl);
  await page.waitForFunction(() => document.querySelector(".fr-corridor")?.getAttribute("data-door") === "live", null, { timeout: 30000 });
  await page.waitForTimeout(600);
  const b = await page.locator(".fr-corridor").boundingBox();
  const still = (name) => page.screenshot({ path: `${EV}${name}.png`, clip: b });
  await still("1-ajar");
  await page.locator(".fr-corridor-door").hover();
  await page.waitForTimeout(800);
  await still("2-peek");
  await page.mouse.move(5, 5);
  await page.waitForTimeout(800);
  await still("3-ajar-again");
  await page.locator(".fr-corridor-door").focus();
  await page.waitForTimeout(800);
  await still("4-focus-peek");
  say("stills in", EV);
}

if (mode === "seat") {
  await page.goto(`${BASE}/showtimes/${target.show}`);
  mark("seat page opened cold");
  await page.waitForFunction(() => !!document.querySelector(".fr-hall-canvas[data-shown]"), null, { timeout: 30000 });
  mark("hall shown");
  await page.waitForTimeout(6500);
  await page.screenshot({ path: `${EV}seat-settled.png` }); // after the arrival: a still, at the end of the video
}

await page.waitForTimeout(800);
const video = await page.video()?.path();
await ctx.close();
await browser.close();
if (video) fs.renameSync(video, `${EV}video.webm`);
fs.writeFileSync(`${EV}marks.json`, JSON.stringify(marks, null, 1));
say("video:", `${EV}video.webm`);

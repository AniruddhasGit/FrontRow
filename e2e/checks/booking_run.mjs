// S-ACC-15: the scripted booking run, measured from the accessibility tree, with a network log per run.
// Run: cd e2e && node checks/booking_run.mjs        (RUNS=n overrides 20 per set; needs the local stack and Vite on :5173)
// stdout is exactly three lines; everything else goes to stderr.
//   t0: the first moment the accessibility tree holds a gridcell named as SCR-SEA-01 publishes (real seat data painted).
//   t1: the first moment an element's ENTIRE text matches the P-TKT-01 reference pattern on the confirmation screen.
// ponytail: a first-time run must register, and RATE_LIMIT_REGISTER_IP_PER_HOUR is 5 locally; restarting the API with a
// bigger bucket is the clean way (P-XCT-07), so instead this script deletes the local register bucket before each
// first-time run and says so on stderr. Never point it at a shared environment.
import { execFileSync } from "node:child_process";
import { BASE, launch } from "../lib.mjs";

const RUNS = Number(process.env.RUNS ?? 20);
const PASSWORD = "e2e-check-password-123";
const SEAT = /^Row [A-Z]+ seat [0-9]+, .+, (available|sold|held by someone else|held by you|out of service)$/;
const REF = /^FR-[23456789ACDEFHJKMNPQRTVWXY]{4}-[23456789ACDEFHJKMNPQRTVWXY]{4}$/;
const EXPIRED = "The hold on your seats has ended and they have been released. You have not been charged.";
const log = (...a) => console.error(...a);

// The simulated payment's delay, read back from the running API's own resolved configuration.
const resolved = execFileSync("docker", ["logs", "frontrow-api-1"], { encoding: "utf8", stdio: ["ignore", "pipe", "pipe"], maxBuffer: 1 << 30 })
  .split("\n").filter((l) => l.includes('"configuration resolved"')).pop();
const delay = Number(JSON.parse(resolved).settings.PAYMENT_SIMULATED_DELAY_MS);
if (!(delay > 0)) throw new Error(`PAYMENT_SIMULATED_DELAY_MS must be > 0, read ${delay}`);
log(`PAYMENT_SIMULATED_DELAY_MS=${delay} (read from the api's configuration log)`);

const browser = await launch();
const ctx0 = await browser.newContext();
const p0 = await ctx0.newPage();
await p0.goto(BASE + "/films");
const showtimes = await p0.evaluate(async () => {
  const out = [];
  for (const f of (await (await fetch("/api/movies")).json()).movies) {
    for (const s of (await (await fetch(`/api/showtimes?movie_id=${f.id}`)).json()).showtimes ?? []) if (!s.sales_closed) out.push(s.id);
  }
  return out;
});
await ctx0.close();
let at = 0; // rotates the runs over every open showtime so no hall runs out of seats

/** One run on `page`; `firstTime` registers through "Sign in to hold these seats". Returns { secs | null, expired }. */
async function run(page, firstTime) {
  const sid = showtimes[at++ % showtimes.length];
  const net = [];
  const onReq = (r) => net.push(`${r.method()} ${new URL(r.url()).pathname}`);
  page.on("request", onReq);
  let expired = false;
  const onResp = async (r) => {
    if (r.request().method() === "POST" && new URL(r.url()).pathname === "/api/bookings" && r.status() === 409) {
      const e = (await r.json().catch(() => ({}))).error ?? {};
      if (e.code === "HOLD_EXPIRED" && String(e.message).startsWith(EXPIRED)) expired = true;
    }
  };
  page.on("response", onResp);
  try {
    await page.goto(`${BASE}/showtimes/${sid}`);
    await page.getByRole("gridcell", { name: SEAT }).first().waitFor({ timeout: 60_000 });
    const t0 = Date.now();
    const free = page.getByRole("gridcell", { name: /, available$/ }).first();
    await free.click();
    if (firstTime) {
      await page.getByRole("button", { name: "Sign in to hold these seats" }).click();
      await page.getByRole("tab", { name: "Register" }).click();
      await page.getByLabel("Email address").fill(`e2e-run-${Date.now()}-${Math.floor(Math.random() * 1e6)}@example.com`);
      await page.locator("#fr-password").fill(PASSWORD);
      await page.getByRole("button", { name: "Create account" }).click();
      await page.waitForURL(new RegExp(`/showtimes/${sid}$`), { timeout: 60_000 });
    }
    await page.getByRole("button", { name: "Hold these seats" }).click();
    await page.getByRole("button", { name: "Continue to payment" }).click();
    await page.getByRole("button", { name: /^Pay / }).click();
    const done = await Promise.race([
      page.waitForFunction((src) => {
        const re = new RegExp(src);
        return [...document.querySelectorAll("main *")].some((e) => re.test(e.textContent ?? ""));
      }, REF.source, { timeout: 200_000, polling: "raf" }).then(() => true),
      (async () => { while (!expired) await page.waitForTimeout(100); return false; })(),
    ]);
    const t1 = Date.now();
    const holds = net.filter((n) => n === `POST /api/showtimes/${sid}/holds`).length;
    const books = net.filter((n) => n === "POST /api/bookings").length;
    if (holds !== 1 || books !== 1) throw new Error(`network log: ${holds} hold POSTs and ${books} booking POSTs (want 1 and 1)`);
    return done ? { secs: (t1 - t0) / 1000, expired: false } : { secs: null, expired: true };
  } finally {
    page.off("request", onReq);
    page.off("response", onResp);
  }
}

const median = (xs) => {
  const s = [...xs].sort((a, b) => a - b);
  return s.length ? (s.length % 2 ? s[(s.length - 1) / 2] : (s[s.length / 2 - 1] + s[s.length / 2]) / 2) : 0;
};
const sets = { "signed-in": [], "first-time": [] };
let errors = 0;

// Signed-in: an account that exists before t0, signed in once outside the measurement.
const signed = await browser.newContext({ viewport: { width: 1440, height: 900 } });
{
  const p = await signed.newPage();
  await p.goto(BASE + "/films");
  const email = "e2e-pay-1@example.com"; // the account pay_ticket_account.test.mjs uses; it exists before t0
  const ok = await p.evaluate(async ([email, password]) => {
    const h = { "content-type": "application/json" }, body = JSON.stringify({ email, password });
    if ((await fetch("/api/auth/login", { method: "POST", headers: h, body })).status === 200) return true;
    return (await fetch("/api/auth/register", { method: "POST", headers: h, body })).status === 201;
  }, [email, PASSWORD]);
  if (!ok) throw new Error(`could not sign in ${email}`);
  await p.close();
}
for (let i = 0, last = 0; i < RUNS; i++) {
  // RATE_LIMIT_CONFIRM_USER_PER_MIN is 10 and these runs share one account: start them >= 6.5 s apart (outside t0..t1).
  await new Promise((r) => setTimeout(r, Math.max(0, last + 6500 - Date.now())));
  last = Date.now();
  const page = await signed.newPage();
  try {
    sets["signed-in"].push(await run(page, false));
  } catch (e) {
    errors++;
    sets["signed-in"].push({ secs: null, expired: false });
    log(`signed-in run ${i + 1} failed: ${e.message.split("\n")[0]}`);
  }
  log(`signed-in ${i + 1}: ${JSON.stringify(sets["signed-in"].at(-1))}`);
  await page.close();
}
await signed.close();

for (let i = 0; i < RUNS; i++) {
  execFileSync("docker", ["exec", "frontrow-redis-1", "redis-cli", "DEL", "rl:register:ip:172.18.0.1"]);
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } }); // no account, no session at t0
  const page = await ctx.newPage();
  try {
    sets["first-time"].push(await run(page, true));
  } catch (e) {
    errors++;
    sets["first-time"].push({ secs: null, expired: false });
    log(`first-time run ${i + 1} failed: ${e.message.split("\n")[0]}`);
  }
  log(`first-time ${i + 1}: ${JSON.stringify(sets["first-time"].at(-1))} (register bucket cleared before this run)`);
  await ctx.close();
}
await browser.close();

const line = (name) => {
  const done = sets[name].filter((r) => r.secs !== null).map((r) => r.secs);
  return `${name}: ${sets[name].length} runs; slowest ${Math.ceil(done.length ? Math.max(...done) : 0)} s; median ${Math.round(median(done))} s`;
};
const exp = (name) => sets[name].filter((r) => r.expired).length;
console.log(line("signed-in"));
console.log(line("first-time"));
console.log(`expired: ${exp("signed-in")} of ${RUNS} signed-in runs, ${exp("first-time")} of ${RUNS} first-time runs ended 409 HOLD_EXPIRED`);
if (errors) log(`${errors} run(s) failed for a reason other than HOLD_EXPIRED; they reached no t1 and are counted in the runs integer`);
process.exitCode = errors ? 1 : 0;

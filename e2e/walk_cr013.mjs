// CR-013: the film page's rating on top of the reviews, the scrolling review list and the star filter, with screenshots
// (evidence/reviews2/). Local stack + Vite. Run: node walk_cr013.mjs [film id]
// Local data only; the account is one lib.mjs registers locally (never the demo logins), and it has never booked the film.
import assert from "node:assert/strict";
import fs from "node:fs";
import { BASE, launch, signedIn } from "./lib.mjs";

const EV = new URL("./evidence/reviews2/", import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, "$1");
fs.mkdirSync(EV, { recursive: true });
const browser = await launch();
const say = (...a) => console.log("-", ...a);
const noSideways = (page) => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth);

const probe = await browser.newPage();
await probe.goto(BASE + "/films");
const films = (await probe.evaluate(async () => (await (await fetch("/api/movies")).json()).movies)).filter((m) => !m.coming_soon);
const film = films.find((m) => m.id === Number(process.argv[2])) ?? films[0];
await probe.close();
say("film", film.id, film.title);

// 1. Signed out: the sign-in prompt sits above the list, at both widths, with no sideways scroll
for (const [w, h] of [[1440, 900], [390, 844]]) {
  const page = await browser.newPage({ viewport: { width: w, height: h } });
  await page.goto(`${BASE}/movies/${film.id}`);
  const rate = page.locator("#film-rate");
  await rate.getByText("to rate and review it").waitFor();
  await page.locator(".fr-review-row").first().waitFor();
  const [above, list] = [await rate.boundingBox(), await page.locator(".fr-review-scroll").boundingBox()];
  assert.ok(above.y + above.height <= list.y, "the sign-in prompt is above the list");
  assert.ok(await noSideways(page), `no sideways scroll at ${w}`);
  await rate.scrollIntoViewIfNeeded();
  await page.screenshot({ path: `${EV}guest-${w}.png` });
  say(`guest ${w}: prompt above the list, no sideways scroll`);
  await page.close();
}

// 2. Signed in, never booked: rate and review; the review appears in the list
const stamp = Date.now();
const { page, ctx } = await signedIn(browser, `e2e-cr013-${stamp}@example.com`);
await page.goto(`${BASE}/movies/${film.id}`);
const rate = page.locator("#film-rate");
await rate.getByRole("button", { name: "8 out of 10" }).click();
await rate.getByText("You gave it 8").waitFor();
await rate.getByRole("button", { name: "Write a review" }).click();
const words = `CR-013 check ${stamp}: sound and seats were great.`;
await rate.getByLabel(/Your review/).fill(words);
await rate.getByRole("button", { name: "Post review" }).click();
await rate.getByRole("button", { name: "Edit your review" }).waitFor();
const mine = page.locator(".fr-review-row", { hasText: words });
await mine.waitFor();
assert.equal(await mine.locator(".fr-review-badge").count(), 0, "no badge: this account never saw it here");
assert.match(await mine.locator(".fr-review-score").innerText(), /★ 8\/10/);
await rate.scrollIntoViewIfNeeded();
await page.screenshot({ path: `${EV}signed-in-reviewed-1440.png` });
say("signed in: rated 8, reviewed, listed without a badge");

// 3. The list scrolls vertically; each score sits beside (right of) its comment on a wide screen
const scroll = page.locator(".fr-review-scroll");
const dims = await scroll.evaluate((el) => ({ sh: el.scrollHeight, ch: el.clientHeight, sw: el.scrollWidth, cw: el.clientWidth }));
assert.ok(dims.sh > dims.ch, "the list scrolls vertically");
assert.ok(dims.sw <= dims.cw, "the list never scrolls sideways");
const row = page.locator(".fr-review-row").nth(1);
const [text, score] = [await row.locator(".fr-review-text").boundingBox(), await row.locator(".fr-review-score").boundingBox()];
assert.ok(score.x >= text.x + text.width - 1 && score.y < text.y + text.height, "the score is to the right of the comment");
await scroll.evaluate((el) => el.scrollTo(0, 400));
await scroll.scrollIntoViewIfNeeded();
await page.screenshot({ path: `${EV}list-scrolled-1440.png` });
say("list scrolls", dims.ch, "of", dims.sh, "px; score beside the text");

// 4. The star filter narrows the list (and combines with Most helpful)
const filter = page.getByRole("group", { name: "Show reviews by stars" });
await filter.getByRole("button", { name: /9–10/ }).click();
await page.waitForFunction(() => [...document.querySelectorAll(".fr-review-score")].length > 0
  && [...document.querySelectorAll(".fr-review-score")].every((e) => /★ (9|10)\/10/.test(e.textContent)));
await page.getByRole("group", { name: "Sort reviews" }).getByRole("button", { name: "Most helpful" }).click();
await page.locator(".fr-state").waitFor({ state: "detached" }).catch(() => {});
await page.waitForFunction(() => [...document.querySelectorAll(".fr-review-score")].every((e) => /★ (9|10)\/10/.test(e.textContent)));
assert.equal(await filter.getByRole("button", { name: /9–10/ }).getAttribute("aria-pressed"), "true");
await filter.scrollIntoViewIfNeeded();
await page.screenshot({ path: `${EV}filter-9-10-helpful-1440.png` });
say("filter 9-10 + Most helpful: every score is 9 or 10");
await ctx.close();

// 5. A phone: the list and the filter wrap, with no sideways scroll
const phone = await signedIn(browser, `e2e-cr013-${stamp}@example.com`, undefined, { width: 390, height: 844 });
await phone.page.goto(`${BASE}/movies/${film.id}`);
await phone.page.locator(".fr-review-row").first().waitFor();
assert.ok(await noSideways(phone.page), "no sideways scroll at 390");
await phone.page.locator(".fr-review-tools").scrollIntoViewIfNeeded();
await phone.page.screenshot({ path: `${EV}signed-in-list-390.png` });
await phone.page.getByRole("group", { name: "Show reviews by stars" }).getByRole("button", { name: /1–2/ }).click();
await phone.page.waitForFunction(() => [...document.querySelectorAll(".fr-review-score")].every((e) => /★ [12]\/10/.test(e.textContent))
  || document.querySelector(".fr-state")?.textContent?.includes("No reviews scored"));
assert.ok(await noSideways(phone.page), "no sideways scroll at 390 with a band chosen");
await phone.page.screenshot({ path: `${EV}filter-1-2-390.png` });
say("phone 390: no sideways scroll, band 1-2 narrows");
await browser.close();

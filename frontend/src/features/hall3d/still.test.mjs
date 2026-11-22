// The 3D screen's still (CR-006): found from the poster redirect. The lookup used HEAD, which the API answers 405,
// and gave up after one failure, so the title card sometimes stayed instead of the film (owner, 2026-11-22).
// Run: node --test frontend/src/features/hall3d/still.test.mjs
import assert from "node:assert/strict";
import { test } from "node:test";
import { stillPath } from "./still.ts";

const answer = (url, ok = true) => ({ ok, url });

test("a GET follows the poster redirect to the still beside it", async () => {
  const seen = [];
  const path = await stillPath(7, async (u, init) => (seen.push(init?.method ?? "GET"), answer("https://x/art/films/silent-sky.webp")));
  assert.equal(path, "/art/films/silent-sky-still.webp");
  assert.deepEqual(seen, ["GET"]);
});

test("a failed or refused lookup is retried, then gives up with null", async () => {
  let n = 0;
  const flaky = async () => (++n < 3 ? Promise.reject(new Error("down")) : answer("https://x/art/films/caldera.webp"));
  assert.equal(await stillPath(1, flaky, { tries: 3, wait: async () => {} }), "/art/films/caldera-still.webp");
  let m = 0;
  const never = async () => (++m, answer("https://x/api/movies/1/poster", false));
  assert.equal(await stillPath(1, never, { tries: 3, wait: async () => {} }), null);
  assert.equal(m, 3);
});

test("a poster that is not a demo film's has no still", async () => {
  assert.equal(await stillPath(2, async () => answer("https://bucket.example/posters/abc.jpg")), null);
});

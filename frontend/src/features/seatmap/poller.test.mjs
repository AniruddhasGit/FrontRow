// S-BRW-15 (P-BRW-11): the seat-map poll loop on a FAKE timer. No wall clock: time moves only when the test says.
// Run: node --test frontend/src/features/seatmap/
import assert from "node:assert/strict";
import { test } from "node:test";
import { createPoller } from "./poller.ts";

function fakeWorld() {
  let now = 0;
  let seq = 0;
  const timers = new Map();
  const listeners = new Set();
  const world = {
    hidden: false,
    requests: [],
    timer: {
      setTimeout(fn, ms) { const id = ++seq; timers.set(id, { at: now + ms, fn }); return id; },
      clearTimeout(id) { timers.delete(id); },
    },
    visibility: { hidden: () => world.hidden, onChange(fn) { listeners.add(fn); return () => listeners.delete(fn); } },
    setHidden(h) { world.hidden = h; for (const fn of listeners) fn(); },
    async advance(ms) {
      const end = now + ms;
      for (;;) {
        const due = [...timers.entries()].filter(([, t]) => t.at <= end).sort((a, b) => a[1].at - b[1].at)[0];
        if (!due) break;
        timers.delete(due[0]);
        now = due[1].at;
        due[1].fn();
        await new Promise((r) => setImmediate(r));
      }
      now = end;
      await new Promise((r) => setImmediate(r));
    },
    get now() { return now; },
  };
  return world;
}

const flush = () => new Promise((r) => setImmediate(r));

test("one request per published interval, the first immediately", async () => {
  const w = fakeWorld();
  const poller = createPoller({
    timer: w.timer, visibility: w.visibility,
    fetchOnce: async () => { w.requests.push(w.now); return { ok: true, value: {}, interval: 3 }; },
    onValue() {}, onError() {},
  });
  poller.start();
  await flush();
  await w.advance(9000);
  assert.deepEqual(w.requests, [0, 3000, 6000, 9000]);
  poller.stop();
});

test("the interval comes from the payload: 5 seconds with no change to this code", async () => {
  const w = fakeWorld();
  const poller = createPoller({
    timer: w.timer, visibility: w.visibility,
    fetchOnce: async () => { w.requests.push(w.now); return { ok: true, value: {}, interval: 5 }; },
    onValue() {}, onError() {},
  });
  poller.start();
  await flush();
  await w.advance(10000);
  assert.deepEqual(w.requests, [0, 5000, 10000]);
  poller.stop();
});

test("a 5-second response: nothing else is sent until it lands, then the interval restarts", async () => {
  const w = fakeWorld();
  const poller = createPoller({
    timer: w.timer, visibility: w.visibility,
    fetchOnce: () => { w.requests.push(w.now); return new Promise((resolve) => w.timer.setTimeout(() => resolve({ ok: true, value: {}, interval: 3 }), 5000)); },
    onValue() {}, onError() {},
  });
  poller.start();
  await flush();
  await w.advance(7999);
  assert.deepEqual(w.requests, [0]);
  await w.advance(1);
  assert.deepEqual(w.requests, [0, 8000]);
  poller.stop();
});

test("hidden: no request for 30 seconds; visible again: one request immediately", async () => {
  const w = fakeWorld();
  const poller = createPoller({
    timer: w.timer, visibility: w.visibility,
    fetchOnce: async () => { w.requests.push(w.now); return { ok: true, value: {}, interval: 3 }; },
    onValue() {}, onError() {},
  });
  poller.start();
  await flush();
  w.setHidden(true);
  await w.advance(30000);
  assert.deepEqual(w.requests, [0]);
  w.setHidden(false);
  await flush();
  assert.deepEqual(w.requests, [0, 30000]);
  poller.stop();
});

test("a failed poll reports an error and keeps polling; the last good value is never withdrawn", async () => {
  const w = fakeWorld();
  const seen = [];
  let n = 0;
  const poller = createPoller({
    timer: w.timer, visibility: w.visibility,
    fetchOnce: async () => { n++; return n === 1 ? { ok: true, value: "map", interval: 3 } : { ok: false }; },
    onValue: (v) => seen.push(["value", v]), onError: () => seen.push(["error"]),
  });
  poller.start();
  await flush();
  await w.advance(6000);
  assert.deepEqual(seen, [["value", "map"], ["error"], ["error"]]);
  poller.stop();
});

test("a refused poll waits Retry-After before the next one", async () => {
  const w = fakeWorld();
  let n = 0;
  const poller = createPoller({
    timer: w.timer, visibility: w.visibility,
    fetchOnce: async () => { w.requests.push(w.now); n++; return n === 2 ? { ok: false, retryAfter: 10 } : { ok: true, value: {}, interval: 3 }; },
    onValue() {}, onError() {},
  });
  poller.start();
  await flush();
  await w.advance(13000);
  assert.deepEqual(w.requests, [0, 3000, 13000]);
  poller.stop();
});

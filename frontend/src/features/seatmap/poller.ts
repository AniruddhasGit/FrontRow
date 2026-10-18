// The seat map's refresh loop (P-BRW-11), behind a subscription-shaped interface so SRC-002 §8.6.2's later
// switch to WebSockets replaces this file and nothing that renders.
//
// - The interval is the one the LAST GOOD RESPONSE carried (poll_interval_seconds). The client holds no constant.
// - One request in flight at a time; the interval restarts when a response lands, success or failure.
// - Paused while the document is hidden; on becoming visible, one request immediately.
// - A refused poll (429) waits Retry-After instead of the interval.
// - The first load failing starts no loop: there is no map and nothing to keep fresh (P-BRW-11 exception 4).
// Timer and visibility are injected, so tests drive it on a fake timer and nothing here reads a clock.

export type PollResult<T> = { ok: true; value: T; interval: number } | { ok: false; retryAfter?: number };

export interface Timer {
  setTimeout(fn: () => void, ms: number): unknown;
  clearTimeout(handle: unknown): void;
}
export interface Visibility {
  hidden(): boolean;
  onChange(fn: () => void): () => void;
}

export interface PollerOptions<T> {
  fetchOnce: () => Promise<PollResult<T>>;
  timer: Timer;
  visibility: Visibility;
  onValue: (value: T) => void;
  onError: (firstLoad: boolean) => void;
}

export function createPoller<T>(o: PollerOptions<T>): { start(): void; stop(): void } {
  let interval: number | null = null; // seconds; null until a first good response says what it is
  let handle: unknown = null;
  let inFlight = false;
  let stopped = true;
  let unlisten: (() => void) | null = null;

  const queueNext = (seconds: number) => {
    if (stopped || o.visibility.hidden()) return;
    handle = o.timer.setTimeout(run, seconds * 1000);
  };

  const run = async () => {
    handle = null;
    if (stopped || inFlight || o.visibility.hidden()) return;
    inFlight = true;
    const result = await o.fetchOnce().catch((): PollResult<T> => ({ ok: false }));
    inFlight = false;
    if (stopped) return;
    if (result.ok) {
      interval = result.interval;
      o.onValue(result.value);
      queueNext(interval);
      return;
    }
    const firstLoad = interval === null;
    if (firstLoad) {
      // No loop starts; `Try again` calls start() again.
      stopped = true;
      unlisten?.();
    }
    o.onError(firstLoad);
    if (!firstLoad) queueNext(result.retryAfter ?? (interval as number));
  };

  return {
    start() {
      stopped = false;
      unlisten = o.visibility.onChange(() => {
        if (o.visibility.hidden()) {
          if (handle !== null) o.timer.clearTimeout(handle);
          handle = null;
        } else if (!inFlight && handle === null) {
          void run();
        }
      });
      void run();
    },
    stop() {
      stopped = true;
      if (handle !== null) o.timer.clearTimeout(handle);
      handle = null;
      unlisten?.();
    },
  };
}

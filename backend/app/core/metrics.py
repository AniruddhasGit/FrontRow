"""Process-wide counters and the Prometheus text exposition (P-XCT-13, EP-XCT-03).

The eight series P-XCT-13 tabulates, and nothing else. The api's GET /metrics (app/api/metrics.py) and the
worker's listener on WORKER_METRICS_PORT (app/workers) both render from here; each process holds its own counters,
which is why the api runs ONE uvicorn worker per container (app/server.py): two would each answer with half.

NOTHING SCRAPES THIS (P-XCT-13 "Server-side validation"): no Prometheus, no agent, no alarm reads it. It exists for an
operator with a terminal on the host during an incident.

ponytail: seat_locks_held is SCARD of this api instance's hold registry (instance:{id}:holds) - O(1), one Redis command
per scrape - not P-XCT-13's INCR/DECR counter. An expired lock stays a member until the registry's own TTL ends (at most
SEAT_HOLD_TTL_SECONDS), so the value can overstate by locks that expired unreleased. The upgrade path is the counter on
the hold lane's acquire and release paths, reconciled by a bounded SCAN on the worker's receive loop.

ponytail: the text format (version 0.0.4) is written by hand - a few lines - instead of adding prometheus_client: eight
series, no exemplars, no multiprocess mode. The upgrade path, if a scraper is ever approved, is that library.
"""

from __future__ import annotations

import math
from collections import defaultdict

CONTENT_TYPE = "text/plain; version=0.0.4"

# name -> (type, help). Exactly P-XCT-13's eight; S-XCT-27 fails on a ninth.
SERIES: dict[str, tuple[str, str]] = {
    "http_requests_total": ("counter", "Completed HTTP requests by route template, method and status."),
    "http_request_duration_seconds": ("histogram", "HTTP request duration by route template."),
    "seat_locks_held": ("gauge", "Seat locks this api instance granted that are still in its hold registry."),
    "queue_depth": ("gauge", "Approximate visible messages on QUEUE_URL, read at most once per cache period."),
    "seat_conflicts_total": ("counter", "Confirms refused 409 SEAT_UNAVAILABLE by the database guard."),
    "booking_confirmations_total": ("counter", "Booking confirm outcomes."),
    "receipt_dispatch_total": ("counter", "Receipt send outcomes in the worker."),
    "outbox_pending": ("gauge", "outbox_message rows with status pending."),
}
# Shown only when queue_depth is a stale value because the last read failed (P-XCT-13 exception 4).
AGE_SERIES = "queue_depth_age_seconds"
# Prometheus's default latency buckets, in seconds.
BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)

_counters: dict[tuple[str, tuple[tuple[str, str], ...]], float] = defaultdict(float)
_hist: dict[str, list[float]] = {}  # route -> per-bucket counts, then sum, then count


def inc(name: str, by: float = 1, **labels: str) -> None:
    _counters[(name, tuple(sorted(labels.items())))] += by


def observe(route: str, seconds: float) -> None:
    h = _hist.setdefault(route, [0.0] * (len(BUCKETS) + 2))
    for i, bound in enumerate(BUCKETS):
        if seconds <= bound:
            h[i] += 1
    h[-2] += seconds
    h[-1] += 1


def reset() -> None:
    """Tests only: counters are process-global."""
    _counters.clear()
    _hist.clear()


def _esc(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def _labels(pairs) -> str:
    return "{" + ",".join(f'{k}="{_esc(str(v))}"' for k, v in pairs) + "}" if pairs else ""


def _num(value: float | None) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return "NaN"
    return repr(float(value)) if isinstance(value, float) and not value.is_integer() else str(int(value))


def render(gauges: dict[str, float | None], queue_depth_age: float | None = None) -> str:
    """The exposition. `gauges` carries the four gauges read at scrape time (None = unknown here, rendered NaN)."""
    out: list[str] = []
    for name, (kind, text) in SERIES.items():
        out += [f"# HELP {name} {text}", f"# TYPE {name} {kind}"]
        if kind == "gauge":
            out.append(f"{name} {_num(gauges.get(name))}")
            if name == "queue_depth" and queue_depth_age is not None:
                out += [f"# HELP {AGE_SERIES} Seconds since queue_depth was last read successfully.",
                        f"# TYPE {AGE_SERIES} gauge", f"{AGE_SERIES} {_num(queue_depth_age)}"]
        elif kind == "counter":
            out += [f"{name}{_labels(lbl)} {_num(v)}" for (n, lbl), v in sorted(_counters.items()) if n == name]
        else:
            for route, h in sorted(_hist.items()):
                out += [f"{name}_bucket{_labels([('route', route), ('le', repr(b))])} {_num(h[i])}" for i, b in enumerate(BUCKETS)]
                out += [f"{name}_bucket{_labels([('route', route), ('le', '+Inf')])} {_num(h[-1])}",
                        f"{name}_sum{_labels([('route', route)])} {_num(h[-2])}",
                        f"{name}_count{_labels([('route', route)])} {_num(h[-1])}"]
    return "\n".join(out) + "\n"


class QueueDepth:
    """queue_depth read through a cache (P-XCT-13 exception 4): a scrape is never an AWS call each time. On a failed
    read the last value is kept and its age is reported beside it."""

    # ponytail: a fixed cache period, not a setting - nothing scrapes /metrics, so no operator tunes it. Make it a
    # named setting (and an .env.example row) if a scraper is ever approved.
    CACHE_SECONDS = 15

    def __init__(self, read, monotonic) -> None:
        self.read, self.monotonic = read, monotonic
        self.value: float | None = None
        self.read_at: float | None = None  # monotonic instant of the last successful read
        self.tried_at: float | None = None
        self.stale = False

    async def get(self) -> tuple[float | None, float | None]:
        """(value, age-or-None). Age is returned only while the value is stale."""
        now = self.monotonic()
        if self.tried_at is None or now - self.tried_at >= self.CACHE_SECONDS:
            self.tried_at = now
            try:
                self.value, self.read_at, self.stale = float(await self.read()), now, False
            except Exception:  # noqa: BLE001 - SQS unreachable: keep the last value (exception 4)
                self.stale = True
        age = (now - self.read_at if self.read_at is not None else None) if self.stale else None
        if self.stale and age is None:
            age = math.nan  # never read successfully: the age is unknown, and saying so beats a made-up zero
        return self.value, age


async def serve(port: int, gauges):
    """The worker's own /metrics listener on WORKER_METRICS_PORT (P-XCT-13 preconditions): worker-side counters have
    nowhere else to go. `gauges` is an async callable returning (gauges, queue_depth_age). Returns the asyncio server.

    ponytail: a bare asyncio HTTP/1.0 responder - one GET, one answer, connection closed - not a web framework in the
    worker. Anything that is not `GET /metrics` gets 404. The upgrade path is prometheus_client's start_http_server."""
    import asyncio

    async def answer(reader, writer) -> None:
        try:
            line = (await asyncio.wait_for(reader.readline(), 5)).decode("latin-1").split()
            if line[:2] == ["GET", "/metrics"]:
                g, age = await gauges()
                body, status = render(g, age).encode(), "200 OK"
            else:
                body, status = b"not found\n", "404 Not Found"
            writer.write(f"HTTP/1.0 {status}\r\nContent-Type: {CONTENT_TYPE}\r\nContent-Length: {len(body)}\r\n\r\n".encode() + body)
            await writer.drain()
        except Exception:  # noqa: BLE001 - a broken scrape must never touch the worker loop
            pass
        finally:
            writer.close()

    # 0.0.0.0 for the same reason as the api: loopback inside a container is unreachable from the host's port mapping.
    return await asyncio.start_server(answer, "0.0.0.0", port)

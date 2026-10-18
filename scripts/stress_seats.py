"""The concurrency proof (SRC-002 §9.1, P-HLD-13, P-XCT-01). Never waivable.

STAGE A (the default) - S-SEA-18, S-XCT-01. Fifty distinct signed-in customers fire one hold request each for ONE
seat, released together from fifty separate connections. Passes only with exactly one 201 and n-1 409
SEAT_UNAVAILABLE naming that seat, a start-instant spread under STRESS_CONCURRENCY_SPREAD_MS, the winner's
confirm answered 201, and exactly one booking_seat row for the pair COUNTED IN POSTGRESQL. Stage A never reaches
the unique constraint: every loser is refused by Redis at SET NX. Removing the constraint leaves this stage green,
and that is expected - it is why the red proof is a different run.

STAGE B - S-XCT-02, local only. Two live holders on one seat: A holds and starts a confirm, the lock key is
deleted from Redis by hand inside the simulated payment delay, B holds the same seat and confirms. Both confirms
reach the booking_seat insert. The script never alters the schema: the operator removes and restores the
constraint by hand between runs (docs/07 Architecture/for_llm/03_concurrency_model.md, the drill), and this
stage reads the catalogue and reports which state it ran against.

Usage, from a container sharing the api's network so the base URL is loopback:
    stress_seats.py --showtime 41 --seat 312 --n 50 --database-url <owner or app URL> [--stage B --redis-url <url>]
The deployed run differs from the local one by --base-url alone.

Environment: STRESS_OPERATOR (required, no default - an unattributed run is not evidence), SEED_DEFAULT_PASSWORD
(the seeded customers' password), SEED_EMAIL_DOMAIN (default demo.frontrow.invalid), STRESS_CONCURRENCY_SPREAD_MS
(default 100), and the two bucket sizes printed before the warm-up (below).

Standard library for HTTP and threads; psycopg (already a backend dependency) for the PostgreSQL count, and redis
(also already one) for stage B's hand-made eviction.
"""

from __future__ import annotations

import argparse
import http.client
import ipaddress
import json
import os
import socket
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from urllib.parse import urlsplit


def fail(message: str) -> None:
    print(message, file=sys.stderr)
    sys.exit(1)


def required(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        fail(f"{name} is not set; this run cannot say what it ran against")
    return value


class Api:
    """One connection per instance: fifty instances are fifty separate TCP connections."""

    def __init__(self, base_url: str) -> None:
        parts = urlsplit(base_url)
        self.host, self.port, self.tls = parts.hostname, parts.port, parts.scheme == "https"

    def connection(self) -> http.client.HTTPConnection:
        kind = http.client.HTTPSConnection if self.tls else http.client.HTTPConnection
        return kind(self.host, self.port, timeout=30)

    def call(self, method: str, path: str, body: dict | None = None, cookie: str | None = None,
             extra: dict | None = None, conn: http.client.HTTPConnection | None = None):
        conn = conn or self.connection()
        headers = {"Content-Type": "application/json"}
        if cookie:
            headers["Cookie"] = cookie
        headers.update(extra or {})
        data = json.dumps(body).encode() if body is not None else None
        conn.putrequest(method, path, skip_accept_encoding=True)
        for k, v in headers.items():
            conn.putheader(k, v)
        if data is not None:
            conn.putheader("Content-Length", str(len(data)))
        conn.endheaders(data)
        response = conn.getresponse()
        raw = response.read()
        try:
            parsed = json.loads(raw) if raw else None
        except ValueError:
            parsed = None
        return response.status, parsed, response


def warm_up(api: Api, n: int, password: str, domain: str) -> tuple[list[str], float]:
    """Sign n seeded customers in through the real login endpoint, untimed. A 429 waits its Retry-After and retries
    that same customer: the login bucket must never decide the race in the measured window."""
    started = time.monotonic()
    cookies = []
    for i in range(1, n + 1):
        email = f"customer-{i:02d}@{domain}"
        while True:
            status, body, response = api.call("POST", "/api/auth/login", {"email": email, "password": password})
            if status == 429:
                time.sleep(int(response.getheader("Retry-After") or "1"))
                continue
            if status != 200:
                fail(f"warm-up sign-in for {email} answered {status}: {body}")
            cookie = response.getheader("Set-Cookie", "").split(";", 1)[0]
            cookies.append(cookie)
            break
    return cookies, round(time.monotonic() - started, 1)


def fire(api: Api, path: str, body: dict, cookies: list[str]) -> list[dict]:
    """One request per customer, each on its own already-open connection, all released by one barrier."""
    barrier = threading.Barrier(len(cookies))
    results: list[dict] = [{} for _ in cookies]

    def one(i: int) -> None:
        conn = api.connection()
        conn.connect()  # connected BEFORE the barrier, so the measured window holds requests, not handshakes
        barrier.wait()
        start = time.perf_counter_ns()
        status, parsed, _ = api.call("POST", path, body, cookies[i], conn=conn)
        results[i] = {"start_ns": start, "status": status, "body": parsed, "user": i}

    threads = [threading.Thread(target=one, args=(i,)) for i in range(len(cookies))]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return results


def booking_seat_rows(database_url: str, showtime_id: int, seat_id: int) -> int:
    import psycopg

    with psycopg.connect(database_url) as conn:
        return conn.execute("SELECT count(*) FROM booking_seat WHERE showtime_id = %s AND seat_id = %s",
                            (showtime_id, seat_id)).fetchone()[0]


def unique_constraints(database_url: str) -> list[tuple[str, str]]:
    import psycopg

    with psycopg.connect(database_url) as conn:
        return conn.execute("SELECT conname, pg_get_constraintdef(oid) FROM pg_constraint "
                            "WHERE conrelid = 'booking_seat'::regclass AND contype = 'u'").fetchall()


def confirm(api: Api, cookie: str, token: str, showtime_id: int) -> tuple[int, dict | None]:
    status, body, _ = api.call("POST", "/api/bookings", {"hold_token": token, "showtime_id": showtime_id}, cookie,
                               {"Idempotency-Key": str(uuid.uuid4())})
    return status, body


def stage_a(args, api: Api, operator: str, limit_ms: int) -> int:
    cookies, warmup = warm_up(api, args.n, required("SEED_DEFAULT_PASSWORD"), args.email_domain)
    results = fire(api, f"/api/showtimes/{args.showtime}/holds", {"seat_ids": [args.seat]}, cookies)
    starts = [r["start_ns"] for r in results]
    spread_ms = round((max(starts) - min(starts)) / 1e6, 1)
    winners = [r for r in results if r["status"] == 201]
    losers = [r for r in results if r["status"] == 409 and (r["body"] or {}).get("error", {}).get("code") == "SEAT_UNAVAILABLE"]
    labels = {json.dumps(r["body"]["error"]["details"].get("unavailable_seats")) for r in losers}
    others = sorted({r["status"] for r in results} - {201, 409})
    outcome = {"operator": operator, "run_at": datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
               "stage": "A", "base_url": args.base_url, "showtime_id": args.showtime, "seat_id": args.seat, "n": args.n,
               "winners": len(winners), "losers": len(losers), "loser_unavailable_seats": sorted(labels),
               "other_statuses": others, "spread_ms": spread_ms, "spread_limit_ms": limit_ms,
               "distinct_users": len({r["user"] for r in results}), "warmup_elapsed_seconds": warmup}
    problems = []
    if spread_ms > limit_ms:
        problems.append(f"NOT CONCURRENT: spread {spread_ms} ms exceeds {limit_ms} ms")
    if 429 in others:
        problems.append("RUN VOID: 429 inside the measured window")
    if len(winners) != 1 or len(losers) != args.n - 1 or len(labels) != 1:
        problems.append(f"expected exactly 1 x 201 and {args.n - 1} x 409 SEAT_UNAVAILABLE naming one seat")
    if outcome["distinct_users"] < args.n:
        problems.append(f"distinct_users is {outcome['distinct_users']}, fewer than {args.n}")
    violations = 0
    if len(winners) == 1:
        status, body = confirm(api, cookies[winners[0]["user"]], winners[0]["body"]["hold_token"], args.showtime)
        outcome["winner_confirm_status"] = status
        violations = int(status == 409 and (body or {}).get("error", {}).get("code") == "SEAT_UNAVAILABLE")
        if status != 201:
            problems.append(f"CONFIRM UNAVAILABLE: the winner's POST /api/bookings answered {status}")
    outcome["unique_constraint_violations"] = violations
    if args.database_url:
        outcome["booking_seat_rows"] = booking_seat_rows(args.database_url, args.showtime, args.seat)
        if outcome["booking_seat_rows"] != 1:
            problems.append(f"booking_seat holds {outcome['booking_seat_rows']} rows for the pair, not exactly 1")
    else:
        problems.append("no --database-url: the row count was not read from PostgreSQL, so nothing is proved")
    outcome["problems"] = problems
    print(json.dumps(outcome))
    for p in problems:
        print(p, file=sys.stderr)
    return 1 if problems else 0


def loopback_only(base_url: str) -> None:
    host = urlsplit(base_url).hostname or ""
    try:
        addresses = {info[4][0] for info in socket.getaddrinfo(host, None)}
    except OSError:
        addresses = set()
    if not addresses or not all(ipaddress.ip_address(a).is_loopback for a in addresses):
        fail("LOCAL ONLY: stage B runs against a loopback --base-url and nowhere else")


def stage_b(args, api: Api, operator: str) -> int:
    loopback_only(args.base_url)
    if not args.redis_url or not args.database_url:
        fail("stage B needs --redis-url (for the hand-made eviction) and --database-url (for the count)")
    import redis

    a, b = warm_up(api, 2, required("SEED_DEFAULT_PASSWORD"), args.email_domain)[0]
    path = f"/api/showtimes/{args.showtime}/holds"
    status_a, hold_a, _ = api.call("POST", path, {"seat_ids": [args.seat]}, a)
    if status_a != 201:
        fail(f"customer A's hold answered {status_a}: {hold_a}")
    confirms: dict[str, tuple] = {}
    first = threading.Thread(target=lambda: confirms.__setitem__("A", confirm(api, a, hold_a["hold_token"], args.showtime)))
    first.start()
    time.sleep(args.evict_after_ms / 1000)  # inside PAYMENT_SIMULATED_DELAY_MS, after A's re-validation
    redis.Redis.from_url(args.redis_url).delete(f"lock:seat:{args.showtime}:{args.seat}")
    status_b, hold_b, _ = api.call("POST", path, {"seat_ids": [args.seat]}, b)
    second = None
    if status_b == 201:
        second = threading.Thread(target=lambda: confirms.__setitem__("B", confirm(api, b, hold_b["hold_token"], args.showtime)))
        second.start()
    first.join()
    if second:
        second.join()
    statuses = [s for s, _ in confirms.values()]
    constraints = unique_constraints(args.database_url)
    rows = booking_seat_rows(args.database_url, args.showtime, args.seat)
    outcome = {"operator": operator, "run_at": datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
               "stage": "B", "base_url": args.base_url, "hold_b_status": status_b,
               "constraint_present": bool(constraints), "constraints": constraints,
               "confirms_201": statuses.count(201),
               "confirms_409_seat_unavailable": sum(1 for s, body in confirms.values()
                                                    if s == 409 and (body or {}).get("error", {}).get("code") == "SEAT_UNAVAILABLE"),
               "confirm_statuses": statuses, "booking_seat_rows": rows}
    print(json.dumps(outcome))
    if not constraints and rows == 1:
        print("DRILL VOID: constraint dropped and count(*) is 1", file=sys.stderr)
        return 1
    if 404 in statuses:
        print("CONFIRM UNAVAILABLE: POST /api/bookings answered 404", file=sys.stderr)
        return 1
    expected = (2, 0, 2) if not constraints else (1, 1, 1)
    return 0 if (outcome["confirms_201"], outcome["confirms_409_seat_unavailable"], rows) == expected else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="FrontRow seat concurrency proof")
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--showtime", type=int, required=True)
    parser.add_argument("--seat", type=int, required=True)
    parser.add_argument("--n", type=int, default=50)
    parser.add_argument("--stage", choices=("A", "B"), default="A")
    parser.add_argument("--database-url")
    parser.add_argument("--redis-url")
    parser.add_argument("--email-domain", default=os.environ.get("SEED_EMAIL_DOMAIN", "demo.frontrow.invalid"))
    parser.add_argument("--evict-after-ms", type=int, default=300)
    args = parser.parse_args()
    operator = required("STRESS_OPERATOR")
    print("RATE_LIMIT_LOGIN_IP_PER_15MIN=" + required("RATE_LIMIT_LOGIN_IP_PER_15MIN"), file=sys.stderr)
    print("RATE_LIMIT_HOLD_IP_PER_MIN=" + required("RATE_LIMIT_HOLD_IP_PER_MIN"), file=sys.stderr)
    limit_ms = int(os.environ.get("STRESS_CONCURRENCY_SPREAD_MS", "100"))
    api = Api(args.base_url)
    return stage_a(args, api, operator, limit_ms) if args.stage == "A" else stage_b(args, api, operator)


if __name__ == "__main__":
    sys.exit(main())

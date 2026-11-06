"""The seat lane's LIVE drill - the criteria that only real containers can prove. Host-run, standard library only:

    python backend/tests/sea/drill_live.py            (from the repository root, Docker Desktop up, compose stack up)

Not collected by pytest (no test_ prefix): it starts and kills containers, which the test image cannot do.

It builds its own world and touches nothing shared: a throwaway database fr_drill_<hex> on the compose postgres
(roles_local.sql + the real `migrate` command), its OWN Redis container fr-drill-redis, and its OWN api container
fr-drill-api from an image built from this working tree (frontrow-api:p4-seats). The compose api, the compose
Redis and the `frontrow` database are never touched. Every container and the database are removed at the end.

Stages, in order (each prints what it observed; the run ends non-zero if any assertion failed):
  redproof   S-XCT-02 at the DATABASE layer: two live holders on one seat through the real hold endpoint (A holds,
             the lock is deleted by hand, B holds), then both "confirms" reach the booking_seat insert as two SQL
             transactions - constraint present: 1 row + a unique violation; constraint DROPPED: 2 rows, the seat sold
             twice; constraint restored: verified in pg_constraint, then 1 row + a violation again. The confirm
             endpoint itself (EP-PAY-01) is lane PAY's and not mounted, so its leg is SQL, and that is said.
  redis-stop S-SEA-15: `docker stop` the Redis container; every hold endpoint answers 503 with a body; ready 503,
             live 200; `docker start` it; the old holds are gone; the next hold is 201 and is all that exists.
  sigterm    S-SEA-17: a real SIGTERM to the running api; exit code 0; this instance's keys, records and index gone;
             a foreign token in the registry left alone; the same customer re-takes the seat with 201.
  sigkill    S-SEA-17: SIGKILL instead; the keys survive with a positive PTTL; with SEAT_HOLD_TTL_SECONDS=2 Redis
             alone removes them.
  stress     S-SEA-18 / S-XCT-01 Stage A: scripts/stress_seats.py, 50 seeded customers, from a container sharing the
             api's network so the base URL is loopback. The warm-up waits out the login bucket (about ten minutes).
"""

from __future__ import annotations

import http.client
import json
import os
import secrets
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
NET = "frontrow_default"
PG = "frontrow-postgres-1"
IMAGE, TEST_IMAGE = "frontrow-api:p4-seats", "frontrow-api:test"
API, REDIS = "fr-drill-api", "fr-drill-redis"
PORT = 18000
PASSWORD = secrets.token_urlsafe(18)  # a throwaway, in memory only; never written anywhere
DB = "fr_drill_" + secrets.token_hex(4)
FAILURES: list[str] = []
# The drill waits on REAL containers in real time - a Redis restart, a process exit, a key's own TTL - which is the
# point of it. It is not a test and asserts nothing against an application clock; every wait is this one helper.
# (A plain sleep: the S-SEA-08 rg over backend/tests finds it, which is that AC's over-reach - see its doc defect.)
def pause(seconds: float) -> None:
    time.sleep(seconds)


def sh(*args: str, check: bool = True, input: str | None = None, env: dict | None = None) -> subprocess.CompletedProcess:
    result = subprocess.run(list(args), capture_output=True, text=True, input=input, env=env, timeout=1800)
    if check and result.returncode != 0:
        raise RuntimeError(f"{' '.join(args[:4])} ... exited {result.returncode}: {result.stderr[-2000:]}")
    return result


def say(line: str) -> None:
    print(line, flush=True)


def check(label: str, ok: bool, observed: object) -> None:
    say(f"  [{'PASS' if ok else 'FAIL'}] {label}: {observed}")
    if not ok:
        FAILURES.append(label)


def psql(sql: str, role: str = "frontrow:local-dev-only") -> str:
    return sh("docker", "exec", "-i", PG, "psql", "-X", "-q", "-At", "-v", "ON_ERROR_STOP=1",
              "-d", f"postgresql://{role}@localhost/{DB}", input=sql).stdout.strip()


def psql_try(sql: str, role: str = "frontrow_app:local-dev-app") -> tuple[int, str]:
    r = sh("docker", "exec", "-i", PG, "psql", "-X", "-q", "-At", "-v", "ON_ERROR_STOP=1",
           "-d", f"postgresql://{role}@localhost/{DB}", input=sql, check=False)
    return r.returncode, (r.stdout + r.stderr).strip()


def rcli(*args: str) -> str:
    return sh("docker", "exec", REDIS, "redis-cli", *args).stdout.strip()


API_ENV = {
    "REDIS_URL": f"redis://{REDIS}:6379/0", "LOG_LEVEL": "INFO", "API_PORT": "8000", "SHUTDOWN_DRAIN_TIMEOUT_SECONDS": "20",
    "READINESS_CACHE_TTL_SECONDS": "0", "JWT_SECRET": "local-drill-only-signing-key-not-a-secret", "COOKIE_SECURE": "false",
    "PUBLIC_BASE_URL": "http://localhost:8080", "QUEUE_URL": "http://elasticmq:9324/000000000000/frontrow-receipts",
    "PAYMENT_PROVIDER": "simulated", "MAIL_PROVIDER": "stub", "S3_BUCKET_NAME": "frontrow-posters-local",
    "AWS_REGION": "ap-south-1", "SES_SENDER_ADDRESS": "receipts@example.invalid", "FORWARDED_ALLOW_IPS": "127.0.0.1",
    "PAYMENT_SIMULATOR_FAIL_KEY_PREFIX": "local-fail-", "BCRYPT_COST": "4",
}


def start_api(**overrides: str) -> None:
    env = {**API_ENV, "DATABASE_URL": f"postgresql://frontrow_app:local-dev-app@postgres:5432/{DB}", **overrides}
    flags = [x for k, v in env.items() for x in ("-e", f"{k}={v}")]
    sh("docker", "run", "-d", "--name", API, "--network", NET, "-p", f"{PORT}:8000", "--read-only", *flags, IMAGE, "api")
    wait_ready()


def wait_ready() -> None:
    for _ in range(120):
        try:
            if call("GET", "/health/ready")[0] == 200:
                return
        except OSError:
            pass
        pause(0.5)
    raise RuntimeError("the drill api never became ready:\n" + sh("docker", "logs", API, check=False).stdout[-3000:])


def call(method: str, path: str, body: dict | None = None, cookie: str | None = None):
    conn = http.client.HTTPConnection("127.0.0.1", PORT, timeout=30)
    headers = {"Content-Type": "application/json", **({"Cookie": cookie} if cookie else {})}
    started = time.monotonic()
    conn.request(method, path, json.dumps(body) if body is not None else None, headers)
    r = conn.getresponse()
    raw = r.read()
    elapsed = round((time.monotonic() - started) * 1000)
    return r.status, (json.loads(raw) if raw else None), r, elapsed


def login(n: int) -> str:
    while True:
        status, body, r, _ = call("POST", "/api/auth/login", {"email": f"customer-{n:02d}@demo.frontrow.invalid", "password": PASSWORD})
        if status == 429:
            pause(int(r.getheader("Retry-After") or "1"))
            continue
        if status != 200:
            raise RuntimeError(f"login {n} answered {status}: {body}")
        return r.getheader("Set-Cookie").split(";", 1)[0]


def remove(*names: str) -> None:
    for name in names:
        sh("docker", "rm", "-f", name, check=False)


# ---- setup -----------------------------------------------------------------------------------------------------


def setup() -> None:
    say(f"setup: database {DB}, image {IMAGE}")
    sh("docker", "build", "-f", "backend/Dockerfile", "--target", "runtime", "-t", IMAGE, str(REPO))
    sh("docker", "exec", PG, "psql", "-U", "frontrow", "-d", "postgres", "-c", f"CREATE DATABASE {DB}")
    sh("docker", "exec", PG, "psql", "-X", "-q", "-v", "ON_ERROR_STOP=1", "-v", "owner_password=local-dev-owner",
       "-v", "app_password=local-dev-app", "-U", "frontrow", "-d", DB, "-f", "/frontrow/roles_local.sql")
    sh("docker", "run", "--rm", "--network", NET, "-e", f"DATABASE_URL=postgresql://frontrow_owner:local-dev-owner@postgres:5432/{DB}",
       IMAGE, "migrate")
    pw_hash = sh("docker", "run", "--rm", "-e", "PW", "--entrypoint", "python", IMAGE, "-c",
                 "import os,bcrypt;print(bcrypt.hashpw(os.environ['PW'].encode(),bcrypt.gensalt(4)).decode())",
                 env={**os.environ, "PW": PASSWORD}).stdout.strip()
    psql(f"""
INSERT INTO cinema (id, name, timezone, version) OVERRIDING SYSTEM VALUE VALUES (1, 'Drill Venue', 'Asia/Kolkata', 1);
INSERT INTO screen (id, cinema_id, name, version) OVERRIDING SYSTEM VALUE VALUES (3, 1, 'Hall 3', 1);
INSERT INTO seat_category (id, name, uplift_basis_points, version) OVERRIDING SYSTEM VALUE VALUES (1, 'Standard', 0, 1);
INSERT INTO seat (id, screen_id, row_label, seat_number, grid_row, grid_col, seat_category_id) OVERRIDING SYSTEM VALUE
  SELECT 300 + n, 3, 'B', n, 2, n, 1 FROM generate_series(1, 20) n UNION ALL SELECT 400 + n, 3, 'C', n, 3, n, 1 FROM generate_series(1, 20) n;
INSERT INTO certification (id, name, is_active) OVERRIDING SYSTEM VALUE VALUES (1, 'Drill cert', true);
INSERT INTO language (id, name, is_active) OVERRIDING SYSTEM VALUE VALUES (1, 'Drill language', true);
INSERT INTO movie (id, title, synopsis, runtime_minutes, certification_id, language_id, published_at, display_from, display_until, version)
  OVERRIDING SYSTEM VALUE VALUES (1, 'DRILL FILM', 'Drill.', 120, 1, 1, now() - interval '1 day', now() - interval '1 day', now() + interval '7 days', 1);
INSERT INTO showtime (id, movie_id, screen_id, starts_at, ends_at, base_price_paise, seat_count_at_creation, version) OVERRIDING SYSTEM VALUE
  VALUES (41, 1, 3, now() + interval '1 day', now() + interval '1 day 2 hours', 25000, 40, 1),
         (77, 1, 3, now() + interval '1 day 3 hours', now() + interval '1 day 5 hours', 25000, 40, 1);
INSERT INTO showtime_seat (showtime_id, seat_id) SELECT v.s, seat.id FROM seat, (VALUES (41), (77)) v(s);
INSERT INTO users (email, password_hash, role, password_version)
  SELECT format('customer-%s@demo.frontrow.invalid', lpad(n::text, 2, '0')), '{pw_hash}', 'customer', 1 FROM generate_series(1, 50) n;
""", role="frontrow_owner:local-dev-owner")
    sh("docker", "run", "-d", "--name", REDIS, "--network", NET, "redis:7-alpine", "redis-server", "--save", "", "--appendonly", "no")
    start_api()
    say(f"  drill api ready on :{PORT}, instance registry {rcli('KEYS', 'instance:*') or '(none yet)'}")


# ---- stages ----------------------------------------------------------------------------------------------------


def insert_seat_sold(ref: str, user: int) -> tuple[int, str]:
    """The confirm's step 7 for one holder, as one transaction, as the API's own role."""
    return psql_try(f"""
BEGIN;
WITH p AS (INSERT INTO payment (state, amount_paise, idempotency_key, pending_at, authorized_at, captured_at)
           VALUES ('captured', 25000, '{secrets.token_hex(8)}', now(), now(), now()) RETURNING id),
     b AS (INSERT INTO booking (reference, user_id, showtime_id, payment_id, total_paise, status)
           SELECT '{ref}', {user}, 41, p.id, 25000, 'confirmed' FROM p RETURNING id)
INSERT INTO booking_seat (booking_id, showtime_id, seat_id, price_paise, base_price_paise_applied, uplift_basis_points_applied, seat_category_id)
SELECT b.id, 41, 312, 25000, 25000, 0, 1 FROM b;
COMMIT;""")


def two_live_holders(a: str, b: str) -> bool:
    sa, ha, _, _ = call("POST", "/api/showtimes/41/holds", {"seat_ids": [312]}, a)
    rcli("DEL", "lock:seat:41:312")  # the hand-made eviction: a restart, an expiry race, a bad release
    sb, hb, _, _ = call("POST", "/api/showtimes/41/holds", {"seat_ids": [312]}, b)
    both = sa == 201 and sb == 201 and rcli("EXISTS", f"hold:{ha['hold_token']}") == "1"
    check("two live holders on (41, 312): A 201, eviction, B 201, A's hold record still present", both, (sa, sb))
    for token, cookie in ((ha, a), (hb, b)):
        if isinstance(token, dict) and "hold_token" in token:
            call("DELETE", f"/api/holds/{token['hold_token']}", None, cookie)
    return both


def clear_bookings() -> None:
    psql("DELETE FROM booking_seat WHERE showtime_id = 41; DELETE FROM booking WHERE showtime_id = 41;", role="frontrow_owner:local-dev-owner")


def run_pair(label: str, refs: tuple[str, str]) -> int:
    first = insert_seat_sold(refs[0], 1)
    second = insert_seat_sold(refs[1], 2)
    rows = int(psql("SELECT count(*) FROM booking_seat WHERE showtime_id = 41 AND seat_id = 312"))
    say(f"  {label}: holder A insert exit {first[0]}; holder B insert exit {second[0]} {second[1][-160:]!r}; rows {rows}")
    return rows


def constraint_rows() -> str:
    return psql("SELECT conname || ' ' || pg_get_constraintdef(oid) FROM pg_constraint "
                "WHERE conrelid = 'booking_seat'::regclass AND contype = 'u'")


def redproof() -> None:
    say("stage redproof (S-XCT-02, database layer)")
    a, b = login(1), login(2)
    clear_bookings()
    two_live_holders(a, b)
    check("constraint present: one row and B refused by uq_booking_seat__showtime_id_seat_id", run_pair("present", ("AAAAAAA2", "AAAAAAA3")) == 1, constraint_rows())
    psql("ALTER TABLE booking_seat DROP CONSTRAINT uq_booking_seat__showtime_id_seat_id;", role="frontrow_owner:local-dev-owner")
    say(f"  constraint dropped; catalogue now: {constraint_rows()!r}")
    clear_bookings()
    two_live_holders(a, b)
    rows = run_pair("dropped", ("AAAAAAA4", "AAAAAAA5"))
    check("constraint DROPPED: the seat is sold twice (2 rows) - the guard watched failing", rows == 2, rows)
    if rows == 1:
        say("DRILL VOID: constraint dropped and count(*) is 1")
    clear_bookings()
    psql("ALTER TABLE booking_seat ADD CONSTRAINT uq_booking_seat__showtime_id_seat_id UNIQUE (showtime_id, seat_id);",
         role="frontrow_owner:local-dev-owner")
    restored = constraint_rows()
    check("restore verified by catalogue", restored == "uq_booking_seat__showtime_id_seat_id UNIQUE (showtime_id, seat_id)", restored)
    clear_bookings()
    two_live_holders(a, b)
    check("constraint restored: one row again", run_pair("restored", ("AAAAAAA6", "AAAAAAA7")) == 1, "1 row")
    clear_bookings()


def redis_stop() -> None:
    say("stage redis-stop (S-SEA-15, the container actually stopped)")
    cookie = login(3)
    s, hold, _, _ = call("POST", "/api/showtimes/77/holds", {"seat_ids": [402]}, cookie)
    check("a hold before the outage", s == 201, s)
    sh("docker", "stop", REDIS)
    token = hold["hold_token"]
    for method, path, body in (("POST", "/api/showtimes/77/holds", {"seat_ids": [403]}), ("GET", f"/api/holds/{token}", None),
                               ("DELETE", f"/api/holds/{token}", None), ("DELETE", f"/api/holds/{token}/seats/402", None)):
        status, body_, _, ms = call(method, path, body, cookie)
        err = (body_ or {}).get("error", {})
        check(f"{method} {path.replace(token, '<token>')} during the outage", status == 503 and err.get("code") == "DEPENDENCY_UNAVAILABLE"
              and err.get("message") == "Seat holds are unavailable right now. You can still browse showtimes. Try again in a few minutes.",
              f"{status} {err.get('code')} in {ms} ms")
    check("/health/live during the outage", call("GET", "/health/live")[0] == 200, "200")
    check("/health/ready during the outage", call("GET", "/health/ready")[0] == 503, "503")
    sh("docker", "start", REDIS)
    for _ in range(60):
        if sh("docker", "exec", REDIS, "redis-cli", "PING", check=False).stdout.strip() == "PONG":
            break
        pause(0.5)
    before = rcli("KEYS", "lock:seat:77:*")
    check("the holds taken before the outage are gone, before the next request", before == "", repr(before))
    s, _, _, _ = call("POST", "/api/showtimes/77/holds", {"seat_ids": [404]}, cookie)
    after = rcli("KEYS", "lock:seat:77:*")
    check("the next hold is 201 and is the only key", s == 201 and after == "lock:seat:77:404", (s, after))


def sigterm() -> None:
    say("stage sigterm (S-SEA-17, a real SIGTERM)")
    cookie = login(4)
    s, hold, _, _ = call("POST", "/api/showtimes/77/holds", {"seat_ids": [410, 411]}, cookie)
    registry = rcli("KEYS", "instance:*:holds").splitlines()
    members = sorted(rcli("SMEMBERS", registry[0]).splitlines()) if registry else []
    check("the registry lists this instance's keys", s == 201 and "lock:seat:77:410" in members and "lock:seat:77:411" in members, (registry, members))
    pttl, ttl = int(rcli("PTTL", "lock:seat:77:410")), int(rcli("PTTL", registry[0]))
    check("registry TTL within a second of the key's PTTL", abs(pttl - ttl) <= 1000, (pttl, ttl))
    rcli("SET", "lock:seat:77:420", "another-holds-token", "PX", "300000")
    rcli("SADD", registry[0], "lock:seat:77:420")
    sh("docker", "kill", "--signal", "SIGTERM", API)
    code = sh("docker", "wait", API).stdout.strip()
    logs = sh("docker", "logs", API, check=False).stdout
    order = [m for m in ("stop signal received", "drain complete; running shutdown hooks", "released this instance's seat holds",
                         "api stopped cleanly") if m in logs]
    check("exit code after SIGTERM", code == "0", code)
    check("the log shows stop, drain, release, exit - in that order", order == ["stop signal received", "drain complete; running shutdown hooks",
                                                                               "released this instance's seat holds", "api stopped cleanly"]
          and logs.index(order[0]) < logs.index(order[1]) < logs.index(order[2]) < logs.index(order[3]), order)
    check("this instance's keys are gone", rcli("EXISTS", "lock:seat:77:410") == "0" and rcli("EXISTS", "lock:seat:77:411") == "0", "EXISTS 0")
    check("the hold record and the cap index are gone", rcli("EXISTS", f"hold:{hold['hold_token']}") == "0"
          and rcli("KEYS", "holds:user:*:showtime:77") == "", "gone")
    check("a foreign token in the registry is left alone", rcli("GET", "lock:seat:77:420") == "another-holds-token", rcli("GET", "lock:seat:77:420"))
    remove(API)
    start_api()
    s, _, _, _ = call("POST", "/api/showtimes/77/holds", {"seat_ids": [410]}, cookie)
    check("the same customer re-takes the seat", s == 201, s)


def sigkill() -> None:
    say("stage sigkill (S-SEA-17: SIGKILL skips the release; Redis's TTL is the guarantee)")
    remove(API)
    start_api(SEAT_HOLD_TTL_SECONDS="2", PAYMENT_SIMULATED_DELAY_MS="100")
    cookie = login(5)
    s, _, _, _ = call("POST", "/api/showtimes/77/holds", {"seat_ids": [415]}, cookie)
    sh("docker", "kill", "--signal", "SIGKILL", API)
    pttl = int(rcli("PTTL", "lock:seat:77:415"))
    check("after SIGKILL the key survives with a positive PTTL", s == 201 and pttl > 0, pttl)
    polls = 0
    while rcli("EXISTS", "lock:seat:77:415") == "1" and polls < 100:
        polls += 1
        pause(0.1)
    check("Redis alone removed it once its TTL passed", rcli("EXISTS", "lock:seat:77:415") == "0", f"after {polls} polls")
    remove(API)
    start_api()


def stress() -> None:
    say("stage stress (S-SEA-18 / S-XCT-01 Stage A) - the warm-up waits out the login bucket")
    env = {**os.environ, "SEED_DEFAULT_PASSWORD": PASSWORD, "STRESS_OPERATOR": os.environ.get("STRESS_OPERATOR", "claude-p4-seats"),
           "RATE_LIMIT_LOGIN_IP_PER_15MIN": "30", "RATE_LIMIT_HOLD_IP_PER_MIN": "60"}
    live_env = sh("docker", "exec", API, "env", check=False).stdout
    say("  api container: RATE_LIMIT_* unset, so the Settings defaults apply: hold 20/user/min, 60/IP/min "
        f"(any RATE_LIMIT_ in env: {[l for l in live_env.splitlines() if l.startswith('RATE_LIMIT_')]})")
    r = sh("docker", "run", "--rm", "--network", f"container:{API}", "-v", f"{REPO / 'scripts'}:/scripts:ro",
           "-e", "SEED_DEFAULT_PASSWORD", "-e", "STRESS_OPERATOR", "-e", "RATE_LIMIT_LOGIN_IP_PER_15MIN", "-e", "RATE_LIMIT_HOLD_IP_PER_MIN",
           "--entrypoint", "python", TEST_IMAGE, "/scripts/stress_seats.py", "--base-url", "http://localhost:8000",
           "--showtime", "41", "--seat", "312", "--n", "50",
           "--database-url", f"postgresql://frontrow_app:local-dev-app@postgres:5432/{DB}", env=env, check=False)
    say("  stdout: " + r.stdout.strip())
    say("  stderr: " + r.stderr.strip().replace("\n", " | "))
    say(f"  exit {r.returncode}")
    try:
        out = json.loads(r.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        out = {}
    check("exactly one 201 and 49 x 409 SEAT_UNAVAILABLE naming one seat", out.get("winners") == 1 and out.get("losers") == 49
          and out.get("loser_unavailable_seats") == ['["B12"]'], (out.get("winners"), out.get("losers"), out.get("loser_unavailable_seats")))
    check("the script proved its own concurrency (spread under the limit)", (out.get("spread_ms") or 1e9) <= 100, out.get("spread_ms"))
    check("distinct_users = 50 and no 429 or 500 in the window", out.get("distinct_users") == 50 and not out.get("other_statuses"), out.get("other_statuses"))
    say(f"  winner confirm: {out.get('winner_confirm_status')} (EP-PAY-01 is lane PAY's); booking_seat rows: {out.get('booking_seat_rows')}")


def teardown() -> None:
    remove(API, REDIS)
    sh("docker", "exec", PG, "psql", "-U", "frontrow", "-d", "postgres", "-c", f"DROP DATABASE IF EXISTS {DB} WITH (FORCE)", check=False)
    say(f"teardown: containers removed, database {DB} dropped")


def main() -> int:
    stages = sys.argv[1:] or ["redproof", "redis-stop", "sigterm", "sigkill", "stress"]
    say(f"drill run_at {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())} operator {os.environ.get('STRESS_OPERATOR', 'claude-p4-seats')}")
    try:
        setup()
        for stage in stages:
            {"redproof": redproof, "redis-stop": redis_stop, "sigterm": sigterm, "sigkill": sigkill, "stress": stress}[stage]()
    finally:
        teardown()
    say(f"RESULT: {'FAIL ' + str(FAILURES) if FAILURES else 'every check passed'}")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())

# 02 — Containers and the module map

> **compressed per SRC-004 R-1.** Processes first, then the code layout inside the backend image,
> then the rules about which module may import which.

## Processes

Three long-running processes, two images (`SRC-003 OPEN-PROC-01`, `FR-ADR-005`, `FR-ADR-063`).
Two one-off commands run from the backend image and exit.

| Process | Image | Entrypoint command | Listens | Long-running | Touches |
|---|---|---|---|---|---|
| **api** | `backend` | `api` → uvicorn, **one** worker process, `--proxy-headers`, `--forwarded-allow-ips=$FORWARDED_ALLOW_IPS` | `API_PORT` (default `8000`) | yes | PostgreSQL, Redis, queue (send), S3 |
| **worker** | `backend` | `worker` → the receive loop | `WORKER_METRICS_PORT` (default `8001`), `/metrics` only | yes | PostgreSQL, Redis (reconcile scan only), queue (receive/delete/send for relay), SES |
| **frontend** | `frontend` | static web server over the Vite build; no Node at runtime | `[JUDGMENT CALL]` `8080` — any port ≥ 1024, because the image runs non-root (`P-XCT-18`) | yes | nothing |
| migrate | `backend` | `migrate` → `alembic upgrade head` as the **owner** role | — | **no**, exits | PostgreSQL |
| seed | `backend` | `seed` → `scripts/seed.py` | — | **no**, exits | PostgreSQL |

**`[JUDGMENT CALL]` frontend port.** No document names it. 8080 is the conventional unprivileged
static-server port. Reversible by one variable; the alternative is any other port ≥ 1024.

**Two database users** (`AWS_PREP_QUEUE` row 20, observed on PostgreSQL 16.14 by `GOAL_08`): `migrate`
connects as the owner; `api`, `worker` and `seed` connect as the application user, which owns no table
and holds `SELECT, INSERT` only on `audit_log`. *Whether `seed` needs owner rights is the seed lane's
call — the seed writes rows, not DDL, so the application user should suffice; unverified.*

## Backend layout (`SRC-002 §11.1`)

```
backend/
├── app/
│   ├── main.py            # builds the FastAPI app; mounts routers; installs middleware; no logic
│   ├── api/               # routers ONLY: request parsing, the router-level dependency, response shaping
│   │   ├── deps.py        #   current_user, require_role(...), manager_scope, idempotency_key, clock
│   │   ├── auth.py        #   EP-ACC-01..03, 05, 06 — public router at /api/auth
│   │   ├── auth_session.py #  EP-ACC-04 — authenticated router at /api/auth (current_user)
│   │   ├── me.py          #   EP-ACC-07..08
│   │   ├── browse.py      #   EP-BRW-01..07
│   │   ├── holds.py       #   EP-HLD-01..04
│   │   ├── bookings.py    #   EP-PAY-01, EP-TKT-01..02
│   │   ├── reports.py     #   EP-RPT-01..03 — require_role(manager, admin) + manager_scope
│   │   ├── reports_audit.py # EP-RPT-04 — require_role(admin) only, at /api/reports
│   │   ├── admin/         #   EP-ADM-01..29, one module per resource
│   │   └── health.py      #   EP-XCT-01..03
│   ├── core/              # config, logging, security, errors, clock, queue port, mail port, storage port
│   │   ├── config.py      #   every setting from the environment, validated at boot, crash if missing (FR-ADR-053)
│   │   ├── logging.py     #   JSON to stdout, request_id contextvar, REDACTION (below)
│   │   ├── security.py    #   bcrypt in a bounded thread pool, JWT cookie, CSPRNG tokens
│   │   ├── errors.py      #   one error envelope, stable codes (FR-ADR-052)
│   │   ├── clock.py       #   Clock protocol; SystemClock in running processes, FrozenClock in tests
│   │   ├── queue.py       #   QueuePort + SqsQueue (ElasticMQ is the same client, different URL)
│   │   ├── mail.py        #   MailPort + SesMail + StubMail
│   │   ├── storage.py     #   StoragePort + S3Storage
│   │   ├── redis.py       #   one client with REDIS_CONNECT/COMMAND_TIMEOUT_MS; the Lua scripts registered here
│   │   └── db.py          #   engine, session factory, DB_POOL_SIZE / MAX_OVERFLOW / statement timeout
│   ├── domain/            # the rules. No FastAPI import. No boto3 import. Ports only.
│   │   ├── locking.py     #   acquire_hold, release_hold, release_seat, revalidate_hold, instance registry
│   │   ├── booking.py     #   the confirm transaction (P-PAY-10), unique-violation translation
│   │   ├── pricing.py     #   integer half-up per seat, sum of seats; the ONLY money arithmetic
│   │   ├── reference.py   #   booking reference: 7 random + 1 D13 check char = 8, 26-char alphabet (SRC-004 R-5)
│   │   ├── payment.py     #   PaymentProvider protocol + SimulatedProvider (FR-ADR-041)
│   │   ├── seatmap.py     #   seat-map read, cache-aside, stampede guard
│   │   ├── catalogue.py   #   movies, display windows, publish rules
│   │   ├── venue.py       #   cinema, screens, seats; row_label = upper(btrim()) (SRC-004 R-4)
│   │   ├── accounts.py    #   register, login, reset request/confirm
│   │   ├── reporting.py   #   dashboard aggregates; takes a resolved scope, never a user
│   │   ├── outbox.py      #   insert inside the caller's transaction; fast-path relay after commit
│   │   ├── audit.py       #   write(session, ...) — never commits
│   │   └── ratelimit.py   #   token bucket Lua; fails closed
│   ├── models/            # SQLAlchemy tables mirroring docs/06 DataModel/schema.sql. No behaviour.
│   ├── workers/           # the long-running loop: backlog relay → receive → dispatch by topic → delete
│   │   └── loop.py
│   └── jobs/              # one handler per topic the worker dispatches. NOT scheduled jobs.
│       ├── receipt_send.py         # receipt.send (P-TKT-05)
│       └── password_reset_send.py  # password_reset.send (P-TKT-12 as amended by SRC-004 R-3)
├── migrations/            # Alembic. The seat guard constraint lands in the Phase 2 migration (FR-ADR-024)
└── tests/
```

**`[JUDGMENT CALL]` what `jobs/` holds.** `SRC-002 §11.1` labels `jobs/` "TMDB sync"; that is withdrawn
and nothing is scheduled. The directory is kept because the layout is the client's, and it now holds
the per-topic handlers the worker calls. The alternative is deleting `jobs/` and putting handlers in
`workers/`; either is one move.

## Import rules — what may depend on what

```
api  ──►  domain  ──►  models
 │          │
 └──► core ◄┘          workers ──► jobs ──► domain
```

- `domain/` imports **no** `fastapi`, **no** `boto3`, **no** `redis` client class directly — it receives
  ports (`QueuePort`, `MailPort`, `StoragePort`, a Redis wrapper from `core/redis.py`, a `Clock`). This
  is what makes the confirm transaction testable with a frozen clock and a fake queue.
- `api/` never contains a rule. A role check inside a handler is a defect (`P-XCT-05`): the role is a
  router-level dependency, declared once per router.
- `models/` contains no behaviour and no default timestamps the application must supply
  (`outbox_message.created_at` comes from the injected clock — `S-TKT-06`).
- `workers/` and `jobs/` never import `api/`.

## The queue port (`FR-ADR-059`)

```python
class QueuePort(Protocol):
    def send(self, queue: QueueName, body: dict, *, timeout_ms: int) -> str: ...
    def receive(self, queue: QueueName, *, wait_seconds: int, max_messages: int) -> list[Message]: ...
    def delete(self, queue: QueueName, receipt_handle: str) -> None: ...
    def extend_visibility(self, queue: QueueName, receipt_handle: str, seconds: int) -> None: ...
```

- **One implementation** (`SqsQueue`) over the AWS SDK. ElasticMQ speaks the SQS wire protocol, so
  local and deployed differ only by URL. No RQ, Dramatiq or Celery.
- **SDK-level retry disabled on `send`**, so `QUEUE_SEND_TIMEOUT_MS` is the real wall-clock bound
  (`S7.9`).
- **`[JUDGMENT CALL]` two queue names, not one: `receipts` (`QUEUE_URL`) and `resets`
  (`RESET_QUEUE_URL`, new).** `SRC-004 R-3` requires the queue holding a reset token to keep it only
  briefly. A receipt message must survive a worker outage of hours, because once the outbox row is
  marked `sent` the message is the only copy of the job. One retention value cannot be both. The
  alternative — one queue with short retention — silently loses receipts during any worker outage
  longer than that retention. Reversible: one variable and one queue. The PRD's single `QUEUE_URL`
  (`S7.9`) needs this added by its owning lane.

## Logging and redaction (`FR-ADR-056`, `SRC-004 R-3`)

- One JSON object per line on stdout. `request_id` from a contextvar; the worker sets it from each
  message's `request_id` before handling.
- **Redaction is in the formatter, not at call sites.** Any field named `reset_token`, `token`,
  `password`, `password_hash`, `hold_token`, `authorization`, `cookie`, `set-cookie`, `jwt` is
  replaced with `"[REDACTED]"` at any depth. A call site that forgets is still safe.
- **The queue message body is never logged whole.** The worker logs `topic`, `message_version`,
  `request_id`, and the row id — never `body`.
- **`botocore`, `boto3`, `urllib3` and `s3transfer` loggers are pinned at `WARNING` regardless of
  `LOG_LEVEL`.** At `DEBUG` the AWS SDK logs request bodies, and an SQS `SendMessage` body for a reset
  carries the plaintext token. Setting `LOG_LEVEL=DEBUG` must not be a way to print a credential.
  A test asserts the token's 43 characters appear in no captured log line at `DEBUG`.

## Frontend layout

```
frontend/src/
├── api/        # one typed client per contract area; credentials: 'include'; relative /api base
├── screens/    # one folder per SCR- id in the PRD
├── components/ # seat map, countdown, error banner — CSS Modules over the token layer (FR-ADR-044)
├── state/      # sessionStorage for the hold token and the pre-login selection (FR-ADR-046, FR-ADR-047)
└── styles/     # docs/05 B DesignSystem tokens
```

**`[JUDGMENT CALL]` the browser reaches the API on the same origin, under `/api`.** The session is an
`HttpOnly`, `SameSite=Lax` cookie (`FR-ADR-050`) and there is no domain yet (`OPEN-TLS-01`), so a
cross-origin API would need CORS with credentials across two load-balancer hostnames. Same origin
needs one listener with path routing (`04` §What the application expects). Alternative: CORS with an
explicit allowed origin; rejected as more configuration that can be wrong. Locally, Vite's dev proxy
forwards `/api` and `/health` to the api container.

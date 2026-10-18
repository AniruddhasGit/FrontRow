# 08 — Failure modes

> **compressed per SRC-004 R-1.** For each dependency or event: what the **customer** sees, what the
> **operator** sees, and whether **data is at risk**. The operator column says what the *application*
> emits (log lines, `/metrics`, readiness); what AWS then does with that is in the tagged notes under
> the table, because none of it has been observed.
>
> **SES is first** because the receipt is the customer's only proof of purchase and only way into the
> hall, so a failure after capture leaves someone who has paid and cannot enter
> (`OPEN-EMAILFAIL-01`, still open). **"TMDB down" is not a row**: there is no external movie API
> (`SRC-003 OPEN-TMDB-01`) — struck per the goal file's 2026-08-22 correction.

## Failure table

| ID | Failure | Customer sees | Operator sees | Data at risk |
|---|---|---|---|---|
| F-01 | **SES down or rejecting, after payment is captured** (outage, sandbox recipient not verified, sender identity not verified, throttled) | The booking succeeded: `201`, the reference on the confirmation screen, "a receipt is on its way to `<address>`". **No email arrives.** The reference stays visible in My bookings, and Resend is available. What else they are told is `OPEN-EMAILFAIL-01` — not invented here | `receipt_dispatch` rows go `sending → failed` with `last_error`; worker `ERROR` lines with `request_id`; messages redeliver and eventually reach the receipts DLQ. **Nothing alarms on the DLQ** (`P-TKT-11`) | **The booking and payment are safe** (committed before the send). **At risk: the customer's entry**, not the data — they hold a valid booking they may not know the reference of if they closed the screen |
| F-02 | SES accepts, the mail bounces or goes to someone else's address (typo, no verification gate, `FR-ADR-050`) | Same as F-01 but the system believes it succeeded | `receipt_dispatch.status = 'sent'` with an SES message id. **Nothing tells the application about a bounce** — no bounce handling is specified | The receipt (a reference) may reach a stranger. No card data exists to leak |
| F-03 | **Redis unreachable** | Browse, showtimes, the seat map and My bookings keep working, slower (cache-aside falls to PostgreSQL); held seats render as available. **Hold and confirm return `503 DEPENDENCY_UNAVAILABLE`**; rate-limited endpoints (login, register, reset) also `503` — the limiter fails closed. Soon after, every `/api/*` request fails at the load balancer once readiness turns (see note) | `/health/ready` → 503 naming `redis`; `DEPENDENCY_UNAVAILABLE` counter; `ERROR` log lines | **None.** Nothing can be held or confirmed, so nothing can be oversold; the database guard is untouched |
| F-04 | Redis restarts (holds dropped) | A customer mid-checkout sees the hold gone: confirm returns `409 HOLD_EXPIRED`; they re-select. If another customer took the seat meanwhile, `409 SEAT_UNAVAILABLE` | spike of `HOLD_EXPIRED`; `seat_locks_held` gauge drops to 0 | **None.** A confirm that raced the restart is refused by the unique constraint if it collides |
| F-05 | **PostgreSQL unreachable** | Every page that needs data errors (`503`/`500` with a request id); a cached seat map may still render for ≤ 10 s | `/health/ready` → 503 naming `postgres`; connection errors in logs | **None committed is lost.** An in-flight confirm rolls back in full, including the payment row: "No payment was taken" is true |
| F-06 | RDS connections exhausted (pool × processes, or a slow aggregate holding connections) | Slow, then `500`/`503` across the api | pool timeout errors; `DB_STATEMENT_TIMEOUT_MS` kills over-long statements | None. Requests fail; nothing half-commits |
| F-07 | **SQS unreachable at confirm** (the fast-path send) | Nothing different: the `201` arrives after at most `QUEUE_SEND_TIMEOUT_MS`; the receipt arrives late | outbox row stays `pending`; the worker's backlog relay sends it once SQS is back and the row is older than 30 s | **None.** The outbox row committed with the booking |
| F-08 | SQS unreachable at the worker | Receipts are delayed for the duration | worker receive errors in logs; outbox rows accumulate `pending`; `queue_depth` unavailable | **None for receipts** while the outage is shorter than the receipts queue's retention (see note AWS-08-03 below) |
| F-09 | **Reset message send fails** (`SRC-004 R-3` path) | The same 202 sentence as always; **no reset email ever arrives**; they must request again (5/hour per IP) | outbox row `password_reset.send` stays `pending` permanently; one `ERROR` line (no token) | **None.** The token is unrecoverable by design; the hash row expires in 30 min |
| F-10 | **S3 unreachable** | Browse works; poster images are broken (the redirect points at an unreachable URL, or the presigned mint fails and the poster endpoint returns an error). Admin poster upload fails with an error | upload errors in api logs; `EP-BRW-03` errors | **None.** Nothing is written until the upload succeeds; the movie row keeps its old `poster_object_key` |
| F-11 | Poster object missing (key on the row, object absent) | A broken image on that movie only | nothing, unless a browser error reaches somebody | None. Posters are never deleted (`FR-ADR-061`), so this means something outside the application removed it |
| F-12 | **Simulated payment slow** (`PAYMENT_SIMULATED_DELAY_MS` raised) | A longer spinner on Pay. If the delay approached the hold, the hold could expire mid-capture — prevented: boot refuses a delay that approaches `SEAT_HOLD_TTL_SECONDS` | config validation error at boot (the process does not start) | None — the boot check exists so a customer never pays for expired seats |
| F-13 | **api SIGTERM'd while holding locks** (deploy, scale-in, host replacement) | A customer mid-checkout on that instance loses their hold and re-selects. In-flight requests finish within the drain | shutdown log lines: drain start, N keys released, exit | **None.** Only holds that never became bookings are released; compare-and-delete never frees another customer's lock |
| F-14 | api SIGKILL'd before the release (stop timeout shorter than deregistration delay + drain) | Those seats look held for up to 180 s, then free themselves | no release log line; the task stopped | None. Expiry is the guarantee; release only shortened the window |
| F-15 | **A deploy during a rush** (one instance, minimum-healthy 0) | The site errors for the whole replacement window; anyone mid-checkout loses their hold (F-13) | deployment events; readiness 503 then 200 on the new task | **None** — every confirm either committed before the stop or rolled back. A confirm whose response was lost is replayed by its `Idempotency-Key` |
| F-16 | **The seat-map poll loop fails silently** (browser tab backgrounded, a JavaScript error, a network drop) | The map stops updating while looking live; a seat they pick may be gone → `409 SEAT_UNAVAILABLE` at hold, naming the seat. The countdown keeps running from `expires_at` | nothing server-side — a poll that never arrives leaves no trace | **None.** Staleness is caught at the hold (Redis) and at the confirm (the constraint) |
| F-17 | **The worker's loop wedges** (running, not polling) or crash-loops | Receipts stop arriving after booking; reset emails stop | **no health endpoint on the worker** (`FR-ADR-055`): a wedged worker looks healthy. Outbox rows age `pending`; `queue_depth` rises on the worker's own `/metrics` that nothing scrapes | None while messages stay within retention; F-01's entry risk accrues per booking |
| F-18 | A container exceeds its memory limit | The site or the worker vanishes for the restart | a task restart with **no application log line** explaining it | None — every write is transactional; a killed confirm rolls back |
| F-19 | Receipts DLQ fills (F-01 sustained) | As F-01, for every booking in the period | nothing, unless someone reads the DLQ | None to data; entry risk to every affected customer |

## Notes on what AWS does — all reasoning

- [AWS-08-01] For F-03 and F-05, the load balancer polls `/health/ready`, sees 503 for its unhealthy-threshold count, marks the only api target unhealthy, and answers `/api/*` itself with an error, so the browse-only degradation lasts only until the threshold is reached. *(reasoned, not observed)*
- [AWS-08-02] For F-01, an SES account still in the sandbox rejects any recipient address that has not been verified, so every real customer's receipt fails until the account leaves the sandbox (prep-queue row 10). *(reasoned, not observed)*
- [AWS-08-03] For F-08, a receipt message older than the receipts queue's retention period is deleted by SQS unreceived, and because its outbox row is already `sent` nothing re-creates it. *(reasoned, not observed)*
- [AWS-08-04] For F-15 and F-18, the only alarm that exists is running-task-count below one (`FR-ADR-068`); a restart that completes between alarm evaluations may never fire it. *(reasoned, not observed)*
- [AWS-08-05] For F-17, ECS restarts a worker whose process exits but does nothing for a worker process that is alive and not polling, because the worker has no health check to fail. *(reasoned, not observed)*
- [AWS-08-07] For F-04, a single-node ElastiCache cluster without persistence returns empty after a restart or replacement, which is what drops every live hold at once. *(reasoned, not observed)*
- [AWS-08-06] For F-14, ECS sends SIGKILL once the container stop timeout expires after SIGTERM, regardless of what the process is doing. *(reasoned, not observed)*

## What nobody is watching (`FR-ADR-068`, `P-XCT-14`)

The receipts DLQ · the worker's liveness beyond "process exists" · `/metrics` on both processes
(nothing scrapes them) · SES bounces · RDS storage growth toward 20 GB (nothing is deleted) · the
CloudWatch Logs 5 GB allowance. Each is an accepted gap in `for_humans/03`.

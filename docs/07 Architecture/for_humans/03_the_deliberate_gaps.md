# 03 — The deliberate gaps

> **compressed per SRC-004 R-1.** What this architecture knowingly does **not** do, why that was
> acceptable, and what it would take to close each one. This is not a defect list: each item was
> chosen, or forced by the free tier, and is written down so it is a decision and not a surprise.
> Statements about how AWS behaves carry an `[AWS-H3-nn]` id and are reasoning only.

## G-1 · No TLS until `OPEN-TLS-01` is ruled

**What is missing.** The load balancer listens on plain HTTP. The session cookie's `Secure` flag is off
(`COOKIE_SECURE=false`). Passwords, session cookies and reset links cross the internet unencrypted.

**Why accepted.** TLS needs a certificate, a certificate needs a domain, and you are still sourcing one.
`FR-ADR-069` defers it, and Art VIII.14 keeps the environment from being called by the name a real
service would have. **No real customer data goes into it** (`P-XCT-29`).

**What closes it.** A domain, an ACM certificate on the listener, `COOKIE_SECURE=true`, `PUBLIC_BASE_URL`
on `https://`. Setting the flag true *before* TLS exists means no browser sends the cookie and nobody
can stay signed in.

- [AWS-H3-01] An ACM public certificate attached to a load balancer listener has no charge of its own, so the domain is the only cost of closing this gap. *(reasoned, not observed)*

## G-2 · One Redis node, no replica, no failover

**What is missing.** Redis exists once. If that node restarts, every live hold is lost (AWS-H3-04
below) and every customer mid-checkout starts again. While it is down, nobody can hold or buy.

**Why accepted.** The free tier has one `cache.t3.micro` (`SRC-002 §5.2.3`). More importantly, the
design makes Redis loss **safe**: the database refuses any double sale, and the code refuses to fall
back to the database for holding seats (`SRC-002 §7.9`). A visible outage was chosen over an invisible
correctness risk.

- [AWS-H3-04] An ElastiCache node without a replica or persistence comes back from a restart empty, so every hold key, cache entry and rate-limit bucket is gone at once. *(reasoned, not observed)*

**What closes it.** A replica with automatic failover — outside the free tier. Even then, holds written
just before a failover can be lost; the database guard is still what keeps that safe.

## G-3 · One EC2 instance: every deploy is a downtime window

**What is missing.** No rolling deploy, no second instance, so every api deploy is a window with no
api running (the ordering is AWS-H3-05 below). Anyone mid-checkout loses their hold.

**Why accepted.** One `t3.micro` is what the free tier covers, and two api tasks do not fit both a fixed
host port and the memory budget. `AWS_PREP_QUEUE` row 18 makes the downtime a configured choice rather
than a deploy that hangs. No booking is corrupted by it: a confirm either committed or rolled back, and
a retried confirm with the same `Idempotency-Key` returns the original result.

- [AWS-H3-05] With minimum-healthy-percent 0 on one instance, ECS stops the running api task before the replacement passes its health check, so the gap lasts at least the new task's start time plus the load balancer's healthy-threshold checks. *(reasoned, not observed)*

**What closes it.** A second instance (and a second public IPv4 address), dynamic host ports, and
deploy settings that start the new task before stopping the old.

- [AWS-H3-02] The free-tier 750 hours a month cover one instance running all month, so a second instance doubles the hours and is billed. *(reasoned, not observed)*

## G-4 · The seat map polls every 3 seconds; it is not pushed

**What is missing.** A customer can see a seat as free for up to about 13 seconds after someone else
took it (3 s poll + 10 s cache). They find out when they try to hold it.

**Why accepted.** `FR-ADR-045`. Polling needs no extra process, no open connection per viewer and no
WebSocket support in the load balancer path — all of which cost memory on a 1 GB host. Staleness is
caught at the hold and the confirm, so it costs a customer a retry, never a double sale.

**What closes it.** Server-sent events or WebSockets from the api, and the memory to hold a connection
per viewer.

## G-5 · The payment provider is simulated, permanently

**What is missing.** No money moves. `PAYMENT_PROVIDER=simulated` is the only accepted value, and the
health endpoint reports it so nobody mistakes the site for a shop.

**Why accepted.** `SRC-003 OPEN-PAY-01`: no real provider, ever. The interface is real so the confirm
transaction, its idempotency and its crash recovery are exercised as if it were.

**What closes it.** A new client ruling; it would be a new provider behind the same interface, and the
crash window between capture and commit would then need a real provider's idempotency key, because a
real capture does not roll back with the database.

## G-6 · Nobody watches the receipt dead-letter queue, the worker's liveness, or `/metrics`

**What is missing.** A receipt that fails for good ends in the DLQ (AWS-H3-07) and nobody sees it. A worker that is running but
stuck looks healthy. `/metrics` exists on both processes and nothing collects it.

**Why accepted.** `FR-ADR-068`: one alarm (running task count) and an honest list of what is not
watched. Managed Grafana is forbidden (`SRC-002 §5.3`); every extra alarm is your configuration and your
cost decision.

- [AWS-H3-07] A receipt message received more times than the redrive policy's maximum is moved by SQS to the dead-letter queue and stays there until that queue's retention period deletes it; nothing in this design reads the dead-letter queue. *(reasoned, not observed)*

**What closes it.** A CloudWatch alarm on the DLQ's visible-message count and on the age of the oldest
message in the receipts queue — tied to `OPEN-EMAILFAIL-01`.

## G-7 · A reset email can be lost and cannot be retried (`SRC-004 R-3`)

**What is missing.** If the api cannot reach the queue at the instant someone asks for a reset, that
reset email is never sent, and the person is not told — they see the same sentence as always.

**Why accepted.** It follows from your ruling that the token is never stored anywhere the system could
re-read it. The build session accepted it under `SRC-004 R-6` (`JC-R6-01`, closing `PROPOSED-ARCH-01`);
you may reverse it.

**What closes it.** Storing the token encrypted under a key held in SSM, or accepting the re-request.

## G-8 · The check character does nothing at the door

**What is missing.** The new check character (`SRC-004 R-5`) rejects mistyped references wherever
software reads them. At the door a person reads the reference aloud and compares by eye; nothing
computes the check.

**Why accepted.** There is no scanner and no validation endpoint (`SRC-003`). How the door verifies a
reference at all is `OPEN-DOORVERIFY-01`. The narrower alphabet (no `Z S B G`) does help at the door,
because those were the look-alike pairs.

## G-9 · No email verification, no bounce handling

**What is missing.** A typo in an email address sends the receipt to nobody, or to a stranger, and the
system records it as sent.

**Why accepted.** `FR-ADR-050`: a verification step would add an SES dependency to registration and a
second interruption to checkout. The address is shown back on the confirmation screen and the reference
is always on screen. Linked to `OPEN-EMAILOWN-01` and `OPEN-EMAILFAIL-01`.

## G-10 · Redis loss takes the whole site out, even though browsing could survive it

**What is missing.** With Redis down the api could still serve browsing from PostgreSQL, but readiness
reports 503, and with one target the load balancer then has nowhere to send traffic (AWS-H3-03 below).

**Why accepted.** `SRC-002 §7.4` and `FR-ADR-028`: you asked to see the failure, not have it hidden by
a softened health check.

- [AWS-H3-03] With a single api target, once the load balancer marks it unhealthy there is nothing else to route to, so every `/api/*` request fails until Redis returns. *(reasoned, not observed)*

## G-11 · One availability zone for everything

**What is missing.** The instance, the database and Redis each exist once, in one zone. Losing that
zone is a full outage (AWS-H3-08).

**Why accepted.** The free tier covers one of each. Recovery from data loss is the rehearsed RDS restore
(`FR-ADR-070`).

- [AWS-H3-08] An availability-zone outage stops every resource placed in that zone, and with one EC2 instance, a single-AZ RDS instance and one ElastiCache node all in it, nothing is left to serve any request. *(reasoned, not observed)*

- [AWS-H3-06] An RDS point-in-time restore creates a new instance with a new endpoint, so `DATABASE_URL` changes and the api and worker must be redeployed to use it. *(reasoned, not observed)*

## G-12 · Local development cannot exercise poster upload without AWS

**What is missing.** There is no local S3 stand-in (`FR-ADR-061`); posters need a real bucket and your
credentials, or the local site runs without posters.

**Why accepted.** A MinIO container is a new dependency and more memory; `SRC-002 §13.1` requires asking
first, and nobody has asked for it.

## G-13 · The memory budget is unmeasured

**What is missing.** Every figure in `../for_llm/04_deployment.md` is an estimate. The worst case leaves
109 MiB spare while a migration runs; if the api needs 120 MiB more than estimated, that case does not
fit.

**Why accepted.** Nothing has run yet. Phase 1 measures and replaces every figure, and **if it does not
fit you are told the number** (`SRC-002 §13.6`) — no limit gets shaved to make a table balance.

## G-14 · Storage only grows

**What is missing.** Nothing is ever deleted (`SRC-003 OPEN-OPS-02`, `FR-ADR-012`): bookings,
idempotency records, outbox rows (including permanently-pending reset rows, G-7), audit rows, old
posters. Nothing watches RDS free storage.

**Why accepted.** It is your ruling, and at this scale the 20 GB will last a long time — *estimated,
not measured*.

**What closes it.** A storage alarm, and, if ever wanted, a retention ruling — which is reserved: legal.

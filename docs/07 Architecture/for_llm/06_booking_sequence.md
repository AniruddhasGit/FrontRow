# 06 — Request flows: hold, confirm, receipt, resend, password reset

> **compressed per SRC-004 R-1.** Sequences only; the rules behind each step are in `03` and in the
> PRD rows cited. `C` = browser, `A` = api, `R` = Redis, `P` = PostgreSQL, `Q` = queue, `W` = worker,
> `S` = SES.

## 1. Seat map read (guest or signed in) — `EP-BRW-06`, `FR-ADR-030`, `FR-ADR-045`

```
C ─GET /api/showtimes/{s}/seatmap───────────────► A
A ─GET cache:seatmap:{s}────────────────────────► R      hit → return (≤ 10 s stale)
  miss → SET cache:seatmap:{s}:rebuild NX PX 2000
         won  → read P (showtime_seat ⨝ seat ⨝ booking_seat) + MGET lock:seat:{s}:* for the set
                → SET cache:seatmap:{s} EX 10 → return
         lost → wait briefly, re-read cache; second miss → read P directly, do not queue
  Redis down → read P directly; held seats render "available" (bounded wrong, never oversold)
C repeats every SEATMAP_POLL_INTERVAL_SECONDS (3). Rate limit: 120/min per IP.
```

The response carries **objective** states (`available`, `held`, `sold`); the client derives
`held_by_me` from its own hold token. The four on-screen states and their non-colour cues are
`FR-ADR-045`.

## 2. Hold — `EP-HLD-01`, `P-HLD-01`

```
C ─POST /api/showtimes/{s}/holds {seat_ids}─────► A    router: require_role(customer, manager, admin) + rate limit
A  validate · cap via SMEMBERS holds:user:{u}:showtime:{s} · cut-off (injected clock)
A ─resolve token (reuse live hold or mint)──────► R
A ─SET lock:seat:{s}:{id} tok NX PX 180000  ×n, ascending──► R
     any nil and not mine → Lua release of won seats → 409 SEAT_UNAVAILABLE {lost seat ids}
A ─SELECT booking_seat for those seats──────────► P    any row → treat as lost (same 409)
A  price new seats (integer half-up per seat) → HSET hold:{tok} …; SADD index + instance registry
A ─DEL cache:seatmap:{s}────────────────────────► R
A ─201 {hold_token, expires_at (UTC), seats[{id, price_paise}], total_paise}──► C
C  stores hold_token in sessionStorage; countdown = expires_at − now; warns at 60 s
```

Release one seat (`EP-HLD-03`) or all (`EP-HLD-04`): Lua compare-and-delete per seat, update the hold
record and index, `DEL cache:seatmap:{s}`. Read back after a reload: `EP-HLD-02`.

## 3. Confirm — `EP-PAY-01`, `P-PAY-10`

```
C ─POST /api/bookings {hold_token, showtime_id}  Idempotency-Key: k──► A   router: current_user + rate limit
A ─BEGIN──────────────────────────────────────────────────────────────► P
   1  INSERT idempotency_record(k)          duplicate → P-PAY-09's three outcomes
   2  re-validate hold ───────────────────► R   gone 409 · not owned 403 · down 503
   3  SELECT showtime FOR UPDATE
   4  read showtime (no cut-off re-check)
   5  sum stored seat prices
   6  payment pending→authorized→captured (simulated, PAYMENT_SIMULATED_DELAY_MS)   failed → 402
   7  INSERT booking (reference: 7 random + 1 check char = 8, ≤ 5 draws) + booking_seat ×n
          unique violation on (showtime_id, seat_id) → 409 SEAT_UNAVAILABLE (the guard working)
   8  (no audit row — not privileged)
   9  INSERT receipt_dispatch(dispatch_seq=1, 'pending')
  10  INSERT outbox_message('receipt.send', {booking_id, dispatch_seq, request_id, message_version})
  11  UPDATE idempotency_record → completed + response_body
  12 COMMIT
A ─Lua release locks · DEL hold:{tok} · SREM index/registry──► R
A ─DEL cache:seatmap:{s}──────────────────────────────────────► R
A ─SendMessage(receipts, payload) ≤ QUEUE_SEND_TIMEOUT_MS──────► Q   ok → UPDATE outbox SET status='sent'
A ─201 {reference, seats, prices, total, "receipt on its way to <email>"}──► C
```

Worst-case wait ≈ 1.56 s transaction + 2.0 s queue timeout ≈ 3.56 s (`P-PAY-10`). The reference is on
the confirmation screen **independently of the email** (`P-TKT-03`).

## 4. Receipt — worker, `P-TKT-04`, `P-TKT-05`, `FR-ADR-031`, `FR-ADR-032`

```
loop forever (no timer — this is the process's main loop):
  backlog relay:  SELECT … FROM outbox_message
                   WHERE status='pending' AND topic='receipt.send'
                     AND created_at < :now − OUTBOX_RELAY_MIN_AGE_SECONDS
                   ORDER BY created_at LIMIT OUTBOX_RELAY_BATCH_SIZE
                   FOR UPDATE SKIP LOCKED
                  → SendMessage(receipts) → mark 'sent'
  receive:        ReceiveMessage(receipts, wait 20 s) ; ReceiveMessage(resets, wait short)
  per message:    bind request_id → branch on topic
    receipt.send:
      UPDATE receipt_dispatch SET status='sending', claimed_at, attempts+1
        WHERE booking_id AND dispatch_seq AND (pending | failed | sending-and-stale) RETURNING id
      0 rows → DeleteMessage, stop          (another delivery owns it, or it is done)
      read booking from P → render SCR-TKT-02 → SES SendEmail ≤ SES_SEND_TIMEOUT_MS
      ok   → status='sent', sent_at, ses_message_id → DeleteMessage
      fail → status='failed', last_error → leave the message (redelivery retries; DLQ after maxReceiveCount)
    unknown topic → log ERROR, do NOT delete (it reaches the DLQ as evidence)
  occasionally:   bounded SCAN to reconcile the seat_locks_held gauge (P-XCT-22)
```

**`topic='receipt.send'` in the backlog relay is new and required by `SRC-004 R-3`** — see §6. The
seed writes `receipt_dispatch` rows `suppressed`, which the claim never matches.

Resend (`EP-TKT-02`, `P-TKT-07`): in one transaction, increment `dispatch_seq`, return the row to
`pending`, insert a new `receipt.send` outbox row naming the new `dispatch_seq`; then the same fast
path. A stale message from an earlier `dispatch_seq` matches zero rows and is deleted.
Limited per booking by `RECEIPT_RESEND_MIN_INTERVAL_SECONDS`.

## 5. Sign-in (for completeness) — `EP-ACC-02`

bcrypt verify in the 2-thread pool (never on the event loop), dummy hash for an unknown address,
JWT in an `HttpOnly`, `SameSite=Lax` cookie with `Secure` from `COOKIE_SECURE` (off until
`OPEN-TLS-01`), carrying `password_version`.

## 6. Password reset under `SRC-004 R-3` — `EP-ACC-05`, `EP-ACC-06`, `P-ACC-07`, `P-TKT-12`

**The ruling:** the plaintext token rides **in the queue message only** — short retention, never
logged, never in the database. PostgreSQL holds `token_sha256` only. **No column — including
`outbox_message.payload` — ever holds the plaintext.** What follows is the shape that satisfies all
three clauses at once; the PRD rows still say "the token never travels in the queue" and need amending
by their owning lane.

### Request — `POST /api/auth/password-reset/request {email}`

```
A  rate limit (5/hour per IP) · normalise email · look up user (timing-equal for unknown)
   unknown address → do nothing else → 202 (identical body)
A  token = secrets.token_urlsafe(32)                 43 chars, held in a local variable only
A ─BEGIN──────────────────────────────────────────────────────────► P
     INSERT password_reset_token(user_id, token_sha256=sha256(token).hex, expires_at=now+1800)
     INSERT outbox_message('password_reset.send',
                           {user_id, reset_token_id, request_id, message_version})   ← NO token
  COMMIT
A ─SendMessage(resets, {…the outbox payload…, "reset_token": token}) ≤ QUEUE_SEND_TIMEOUT_MS──► Q
     ok → UPDATE outbox_message SET status='sent'
     fail/timeout → leave 'pending'; the token is now unrecoverable (see "the cost" below)
A  del token ; 202 {the one shared sentence}
```

### Worker — `password_reset.send`

```
read message body → reset_token (never logged; the formatter redacts the key anyway)
read password_reset_token by reset_token_id
verify sha256(reset_token).hex == row.token_sha256      mismatch → log ERROR (no token), DeleteMessage, stop
verify row.used_at IS NULL and row.expires_at > now      expired/used → DeleteMessage, stop (no email)
claim: UPDATE … SET email_claimed_at WHERE email_sent_at IS NULL AND (unclaimed OR stale) RETURNING id
       0 rows → DeleteMessage, stop
render link PUBLIC_BASE_URL + "/reset?token=" + reset_token → SES ≤ SES_SEND_TIMEOUT_MS
ok   → email_sent_at → DeleteMessage
fail → leave the message; redelivery retries until the queue's retention (≤ token lifetime) drops it
```

- [AWS-06-01] SQS removes a message once its retention period passes even if it was never successfully processed, which is what bounds the life of a failing reset message to the `resets` queue's retention. *(reasoned, not observed)*

**Why the worker re-hashes.** The message is the only place the token exists, so the worker checks it
against the row before mailing it. A message whose token does not match its row is never turned into
an email — it would be a link that cannot work, or a message somebody else put on the queue.

### Confirm — `POST /api/auth/password-reset/confirm {token, new_password}`

Hash the presented token, look up by `token_sha256`, conditional `UPDATE … SET used_at WHERE used_at
IS NULL AND expires_at > now`, set the new bcrypt hash, increment `password_version` (every live
session dies). Errors are `400 RESET_TOKEN_INVALID` for not-found / used / expired / lost race.

### Where the plaintext exists, exhaustively

| Place | Holds the plaintext? | For how long |
|---|---|---|
| api process memory, between generation and `SendMessage` | yes | one request |
| `resets` queue message body | **yes — by the ruling** | until deleted, or the queue's retention (≤ 1800 s) |
| worker process memory, while rendering | yes | one job |
| the email | yes | that is its purpose |
| `password_reset_token` | **no** — `token_sha256` only | — |
| `outbox_message.payload` | **no** — `reset_token_id` only, enforced by the payload-keys CHECK | — |
| any log line, at any `LOG_LEVEL` | **no** — formatter redaction + SDK loggers pinned at `WARNING` | — |
| a dead-letter queue | **no** — `resets` has none (`[JUDGMENT CALL]`, below) | — |
| the 202 response | **no** | — |

**`[JUDGMENT CALL]` no dead-letter queue on `resets`.** A dead-letter queue is a second at-rest copy of
the credential, kept for its own retention and watched by nobody (`P-TKT-11`). Without one, a reset
message that keeps failing is dropped when the queue's retention runs out — which is no later than the
token's own expiry, after which the link would not work anyway. The alternative is a DLQ with the same
short retention; it adds evidence of failed resets and a second copy of a live token. Reversible.

**The cost of this design, stated rather than hidden.** The backlog relay **cannot** send a pending
`password_reset.send` row: the token exists nowhere it can read. So if the request's own `SendMessage`
fails, **that reset email is never sent**, the outbox row stays `pending` forever (nothing is deleted,
`FR-ADR-012`), and the customer — who was shown the same 202 sentence either way — must request again.
That is why the relay filters on `topic='receipt.send'`. The client chose this ruling for its small
blast radius; this consequence is put in front of them in `for_humans/02_decisions_owed.md` as a new
question, not decided here.

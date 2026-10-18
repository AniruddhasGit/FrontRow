# 07 — State machines

> **compressed per SRC-004 R-1.** Every stateful thing, its states, the only transitions that exist,
> and who makes each one. **A transition not in a table here is a defect.** The seat machine's
> normative, machine-readable form is `P-HLD-01`'s `transition` block in
> `docs/03 PRD/sections/E2_seat_hold.md`; this file summarises it and adds the rest.

## Seat, per showtime (client view) — `E2` transition block

States: `available` · `held_by_me` · `held_by_me_paying` · `held_by_other` · `sold`.

| From | Event | To | Decided by |
|---|---|---|---|
| available | hold OK | held_by_me | Redis `SET NX` |
| available | another customer's hold | held_by_other | Redis |
| held_by_me | confirm starts | held_by_me_paying | client |
| held_by_me / held_by_me_paying | TTL expires, release, SIGTERM drain | available | Redis key gone |
| held_by_me_paying | commit | sold | PostgreSQL `booking_seat` row |
| held_by_me_paying | unique violation | held_by_other or sold | PostgreSQL |
| held_by_other | their TTL / release | available | Redis |
| held_by_other | they commit | sold | PostgreSQL |
| sold | anything | sold | **terminal.** No cancellation in v1 (`FR-ADR-013`) |

The server publishes only `available` / `held` / `sold`; `held_by_me*` is derived by the client from
its own token. **The sales cut-off changes no seat's state** — it makes `available` seats unholdable.

## Hold (Redis only — no table)

```
(none) ──hold OK──► live ──confirm commits──► consumed (keys deleted after commit)
                     │ ├─TTL 180 s──────────► gone
                     │ ├─release (all)──────► gone
                     │ └─SIGTERM drain──────► gone
                     └─partial release──────► live (fewer seats, same token, same expires_at)
```

`expires_at` never moves. Adding seats to a live hold reuses token and expiry (`P-HLD-01` step 4).

## `idempotency_record.status` — `FR-ADR-020`, `P-PAY-09`

`in_progress` → `completed` (step 11, same transaction as the booking). **Never expired, never
deleted.** A rolled-back confirm leaves no row (the insert was inside the transaction), so a retry with
the same key starts clean.

## `payment.state` — `FR-ADR-041`, `P-PAY-07`

`pending` → `authorized` → `captured`, or `pending`/`authorized` → `failed`. All inside the confirm
transaction; a rollback removes the row. **No reverse transition, no refund** (`P-PAY-12`, reserved:
money).

## `booking.status` — `FR-ADR-013`

Written once: `confirmed`. `cancelled_at` exists, is always null in v1, and no endpoint writes it.
`SELECT DISTINCT status FROM booking` returns one row.

## `receipt_dispatch.status` — `FR-ADR-032`, `P-TKT-05`, `P-TKT-07`

```
pending ──claim──► sending ──SES ok──► sent      (terminal for this dispatch_seq)
   ▲                 │  └──SES fail──► failed ──claim on redelivery──► sending
   │                 └──stale (claimed_at older than 900 s)──claim──► sending
   └──resend (dispatch_seq + 1)── sent | failed
suppressed   (seed only; never claimed)
```

`sent` means SES accepted the message, not that it arrived. Nothing revises it.

## `outbox_message.status` — `FR-ADR-031`

`pending` → `sent`. Two members only. **Under `SRC-004 R-3` a `password_reset.send` row whose fast-path
send failed stays `pending` permanently**, because nothing can reconstruct its token; the backlog relay
selects `topic='receipt.send'` only. A permanently-pending reset row is a record that a reset was
requested and its email was never handed to the queue.

## `password_reset_token` — `P-ACC-07`, `P-ACC-08`, `P-TKT-12`

Three timestamps, three questions (`GOTCHAS.md`): `email_claimed_at` (a worker holds the send),
`email_sent_at` (SES accepted it), `used_at` (the token was redeemed).

```
issued ──worker claims──► claimed ──SES ok──► emailed ──confirm──► used      (terminal)
  │                          └─stale─► re-claimable
  └─ expires_at passes at any point ──► expired (derived, not stored)   confirm → 400
```

## Readiness — `FR-ADR-055`

`ready` ⇄ `not_ready(postgres|redis)`, recomputed at most every `READINESS_CACHE_TTL_SECONDS`.
`/health/live` has no states: it is 200 or the process is gone.

## Process lifecycle — api, `FR-ADR-033`

`starting` (config validated; crash on any missing value) → `serving` → SIGTERM → `draining`
(deregistration delay, then ≤ `SHUTDOWN_DRAIN_TIMEOUT_SECONDS`) → `releasing` (instance registry) →
exit. Worker: `polling` → SIGTERM → finish current message and any relay batch → exit.

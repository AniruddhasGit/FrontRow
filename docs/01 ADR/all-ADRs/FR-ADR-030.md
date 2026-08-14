# The seat-map cache: cache-aside, deleted after commit, and stampede-guarded

```
ADR id ............ FR-ADR-030
Pack .............. PACK-CONC
Decision type ..... JUDGMENT_CALL
Decision owner .... build session
Decision status ... APPROVED
Decision outcome .. ADOPTED
Decided by ........ build session (Art III.9)
Decision date ..... 2026-08-14
Source ............ SRC-002 §8.2.1; SRC-002 §8.2.2; SRC-002 §8.2.3; SRC-002 §8.6.1; SRC-001 §3.3; SRC-001 §7.3
Constitution ...... frontrow-constitution@0.1.0
```

## Context

`SRC-002 §8.2.1` requires the seat map to be cached per showtime with a short TTL, invalidated on any
booking or lock change, using cache-aside. `§8.2.2` requires the movie and showtime lists to be cached
too. `§8.2.3` requires the places a cache stampede could happen to be documented **in code**, with how
it was prevented.

This is the highest-traffic read in the product. The seat map is polled every three seconds
(`§8.6.1`), so every viewer of a busy showtime fetches it twenty times a minute, and a 220-seat hall
makes it the largest payload too.

Two races are undetermined. Whether invalidation happens inside or outside the booking transaction —
inside is impossible, since Redis does not roll back, but "outside" has a window. And the classic
cache-aside read-then-write race, where a slow reader writes a stale value over a fresh invalidation.

## Decision

**Cache-aside, with `DEL` on change rather than write-through.**

**Key:** `cache:seatmap:{showtime_id}`. **TTL: 10 seconds.** Short enough that a missed invalidation
self-corrects inside one poll cycle plus a few seconds; long enough that a busy showtime is served
from cache for most of its polls.

**Invalidation is a `DEL` issued after the booking transaction commits, and after the Redis locks are
released.** Not a write of the new value.

- `DEL` rather than `SET`: a writer that computes and writes the new map can lose to a slower reader
  that computed an older map first, which is the read-then-write race. Deleting cannot write a stale
  value, because it writes nothing.
- After commit: deleting before commit opens a window where a reader rebuilds from a database that
  does not yet have the booking, and caches that.

**A hold or a release also invalidates**, because a held seat is a distinct state on the map
(`SRC-001 §5.2.2`).

**If the `DEL` fails, nothing is retried and nothing is rolled back.** The entry expires within 10
seconds. `SRC-001 §3.3` requires availability to be accurate "within a few seconds", and 10 seconds is
the worst case for a failed delete against a 3-second poll — a bounded, stated staleness rather than
an unbounded one.

**Stampede prevention: a per-key rebuild lock.** On a miss, one caller acquires
`cache:seatmap:{id}:rebuild` with `SET NX PX 2000` and rebuilds. Callers that do not get it wait
briefly and re-read the cache, and on a second miss they read from PostgreSQL directly rather than
queueing. Nobody blocks on a lock they cannot get.

This is the specific place `§8.2.3` is about, and the code carries a comment saying so, naming the
scenario: the TTL expires on a popular Friday showtime and every in-flight poller rebuilds the map at
once.

**Movie and showtime lists** are cached the same way with a **60-second TTL**, because they change
only when an admin acts. They are invalidated on the admin write that changes them.

**A cache outage is a cache miss** (`FR-ADR-028`). Reads fall through to PostgreSQL.

## Alternatives rejected

**Write-through: compute the new map and `SET` it on every change.** Rejected on the read-then-write
race above, and because it does work on the write path that most of the time nobody reads.

**No TTL, relying purely on invalidation.** Rejected. Every missed `DEL` — a Redis blip, a crash
between commit and delete — becomes permanent staleness, and a permanently stale seat map sells a
seat that is gone.

**Invalidate inside the transaction.** Impossible in the sense that matters: Redis does not
participate in the rollback, so a rolled-back transaction would have already deleted, and a committed
one would have deleted too early.

**A transactional outbox for cache invalidation.** Rejected as disproportionate. The TTL already
bounds the failure at 10 seconds; an outbox to guarantee a delete that expires anyway is machinery
with no gain.

**Lock and wait on a stampede.** Rejected. Under a 3-second poll a queue of waiters is a queue that
refills faster than it drains. Falling through to PostgreSQL is slower for those callers and does not
build a backlog.

**Cache the seat map per user, including their own held seats.** Rejected. It multiplies the cache by
the number of viewers and destroys the hit rate. The cached map carries objective state — available,
held, sold — and the caller's own holds are overlaid from their hold token at render time.

## Source

`SRC-002 §8.2.1` (cache-aside, short TTL, invalidated on booking or lock change) ·
`§8.2.2` (movie and showtime lists) · `§8.2.3` (document the stampede in code) ·
`§8.6.1` (3-second polling) · `SRC-001 §3.3` (accurate within a few seconds) · `§7.3` (seat maps must
not lag).

TTL values, `DEL`-not-`SET`, and the rebuild-lock shape are the build session's under Art III.9.

## Consequences

The customer's view of the seat map can be up to about 13 seconds stale in the worst case — a 10-second
TTL plus a 3-second poll interval. `SRC-001 §3.3` asks for "within a few seconds" and this is at the
edge of that. It is stated rather than rounded down, and it is the number to revisit if the client
finds the map feels wrong.

**Staleness never causes an oversell.** A customer who clicks a seat the map showed as available loses
at the Redis lock or at the unique constraint, and is told (`SRC-001 §5.2.6`). The cache affects what
someone sees, never what they get.

The rebuild lock is a second use of Redis locking with different semantics from the seat lock — short,
uncontended, and safe to lose. Sharing the seat lock's code for it would import the token machinery for
no reason.

`§8.2.3`'s "document it in code" is a deliverable that a reviewer must check for, not a comment style.

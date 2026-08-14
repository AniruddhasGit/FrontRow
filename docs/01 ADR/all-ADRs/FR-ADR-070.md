# Backups: RDS automated snapshots at the free-tier maximum, and a restore that has been rehearsed

```
ADR id ............ FR-ADR-070
Pack .............. PACK-OPS
Decision type ..... JUDGMENT_CALL
Decision owner .... build session
Decision status ... APPROVED
Decision outcome .. ADOPTED
Decided by ........ build session (Art III.9)
Decision date ..... 2026-08-14
Source ............ SRC-003 OPEN-OPS-02; SRC-002 §5.2.2; SRC-002 §6.3.7; SRC-002 §6.4.2; SRC-001 §7.5; SRC-001 §7.6; SRC-002 §12.8
Constitution ...... frontrow-constitution@0.1.0
```

## Context

`SRC-003 OPEN-OPS-02` says booking records are kept forever. `SRC-001 §7.6` requires the system to
answer who booked a seat, for any seat, at any time.

Neither is satisfied by retention alone. **A record kept forever in a database with no backup is a
record kept until the first disk failure or the first mistaken `DELETE`.** `FR-ADR-012` removes the
second by removing deletion from the design, and it does nothing about the first.

No frozen source mentions backups. That is the gap: forever retention was ruled and the mechanism that
makes it true was not.

## Decision

**RDS automated backups, enabled, with retention set to the free-tier maximum.**

RDS's free tier includes backup storage up to the size of the provisioned database — 20 GB
(`§5.2.2`) — so retention costs nothing until the backups exceed the database's own size. **Retention
of 7 days.** More would begin to cost against a zero budget and would not change what is recoverable
in the failure modes this project actually has.

**Automated backups also enable point-in-time recovery**, which is the more useful capability of the
two: it recovers to any second inside the window, not just to a nightly snapshot. That is what makes a
mistake at 14:00 recoverable to 13:59.

**A manual snapshot before every migration.** `FR-ADR-062` makes migrations an explicit step the client
runs, and taking a snapshot immediately before it is one more command in the same procedure. Manual
snapshots persist beyond the automated retention window and are the only thing that makes a bad
migration recoverable after seven days.

**The backup window is set outside the cinema's busy period** — Friday and Saturday evenings
(`SRC-001 §7.2`) — because a `db.t3.micro` has no read replica and backup I/O competes with live
traffic on one small instance. *(reasoned, not observed.)*

**Redis is not backed up and does not need to be.** It holds locks and cache (`FR-ADR-025`,
`FR-ADR-030`), both of which are reconstructible or expendable. Losing the node loses live holds and
nothing else, which `FR-ADR-028` already treats as a visible partial outage by design.

**S3 posters are not backed up.** S3's own durability is the mechanism, versioning is not enabled, and
the objects are re-uploadable by the admin. Nothing is deleted (`FR-ADR-061`), so an overwrite cannot
lose one.

**A restore is rehearsed, and the rehearsal is what makes this real.** Restoring to a new instance,
pointing a local application at it, and confirming that a known booking is present and correct.
**Until that has been done once, this record describes a backup and not a recovery.** It is a Phase 7
runbook deliverable (`§12.8`) with a recorded outcome and a recorded date.

**Enabling the backups, setting the window and running the restore are all Zone C** — they are `aws`
commands that create and modify infrastructure (`§6.3.7`), and `FR-ADR-003` gives the build session no
write access. What is owed is the specification (`§6.4.2`): the retention value, the window, the
pre-migration snapshot step, the restore procedure, and its acceptance criterion.

**Two things the specification must warn about**, because both are common and both are silent:

- **A restore creates a new RDS instance with a new endpoint.** It does not restore in place. The
  application's `DATABASE_URL` has to be repointed, which means the recovery procedure includes a
  configuration change and a deploy (`FR-ADR-054`).
- **Deleting an RDS instance deletes its automated backups** unless a final snapshot is taken. A
  cleanup that removes a database also removes the ability to recover it. *(reasoned, not observed.)*

## Alternatives rejected

**No backups, relying on RDS's durability.** Rejected. Durability protects against hardware failure and
not against a bad migration, and `OPEN-OPS-02`'s forever retention would be a claim nothing supports.

**Longer retention, say 35 days.** Rejected on cost once backups exceed the database size. Manual
pre-migration snapshots cover the case that longer retention would.

**A scheduled `pg_dump` to S3.** Rejected on two grounds. It needs a schedule and **nothing in this
system runs on a schedule** (`FR-ADR-005`). And it would be a fourth process or a cron container inside
a 1 GB budget.

**Enable S3 versioning on the poster bucket.** Rejected as protection against a deletion that cannot
happen — nothing deletes posters, and a new poster is a new key.

**Back up Redis.** Rejected: nothing in it is worth recovering.

**Skip the restore rehearsal because the mechanism is AWS's.** Rejected. Art IV.5's reasoning applies
beyond the concurrency guard — **a recovery nobody has performed is decoration.** The parts that fail
are the endpoint change and the configuration, not AWS's snapshot.

## Source

`SRC-003 OPEN-OPS-02` (kept forever) · `SRC-002 §5.2.2` (`db.t3.micro`, 20 GB) ·
`§6.3.7` (`aws` commands that create infrastructure are Zone C) · `§6.4.2` (the specification is owed)
· `SRC-001 §7.5` (recoverability) · `§7.6` (auditability) · `SRC-002 §12.8` (Phase 7, the runbook).

No frozen clause rules backups. This is a technical decision under Art III.9 and the client may
reverse it.

## Consequences

**Forever retention and a 7-day backup window are different guarantees**, and the difference is worth
stating: the data is kept forever, and it is recoverable for seven days after a mistake. A corruption
discovered in week three is not recoverable from an automated backup — only from a manual snapshot
that happened to be taken.

Storage grows without bound (`FR-ADR-012`), and backup storage grows with it. Once the database exceeds
20 GB, backups start to cost. That is far away at six halls and it belongs in the runbook as a figure
to watch.

**The restore rehearsal is a dated, recorded event.** An undated claim that it was performed is not
evidence (Art VII.1), the same standard the red-proof drill is held to (`FR-ADR-034`).

Enabling backups is a prep-queue item with a *needed by* stage of Phase 2 — the first phase that
creates data worth losing — announced now under Art VIII.4.

# Nothing is ever deleted: no retention window, no pruning job, no destructive cascade

```
ADR id ............ FR-ADR-012
Pack .............. PACK-DATA
Decision type ..... CLIENT_RULING
Decision owner .... client
Decision status ... APPROVED
Decision outcome .. ADOPTED
Decided by ........ Aniruddha Jathar (SRC-003)
Decision date ..... 2026-08-14
Source ............ SRC-003 OPEN-OPS-02; SRC-001 §7.6; SRC-003 OPEN-PROC-01; SRC-002 §5.2.2
Constitution ...... frontrow-constitution@0.1.0
```

## Context

`SRC-001 §10.29` asked how long booking records must be kept. It was raised as `OPEN-OPS-02` and
classed reserved: legal, because a retention floor is a legal question and a retention ceiling is a
storage cost. The client answered: "for now forever we'll change that later if i ask."

That is a real answer and it binds. It also has consequences that reach much further than a retention
policy, because it removes deletion from the design vocabulary entirely.

`SRC-001 §7.6` already requires the system to answer "who booked this seat and when" for any seat, at
any time. Forever retention is what makes that sentence true rather than aspirational.

## Decision

**Nothing in this system is ever deleted.**

- **No pruning job and no retention window.** There is nothing to schedule one on in any case —
  `FR-ADR-005` deletes the scheduler.
- **No foreign key uses `ON DELETE CASCADE` on any path that can reach a booking.** The default for
  every relationship is `ON DELETE RESTRICT`. A cascade is a delete that happens without anyone
  writing the word delete.
- **Entities that stop being current are withdrawn, not removed.** A movie that is no longer shown
  falls outside its display window. A screen that is retired is marked inactive. A showtime that is
  withdrawn keeps its row. In each case the historical bookings still resolve to a real parent row.
- **The customer-facing surface has no delete anywhere.** No cancel button (`SRC-001 §E E-2`), no
  account deletion.

**Where this rule does not reach.** Rows that carry no history are current state and may be removed:
a manager-to-screen assignment (`FR-ADR-011`), an expired Redis lock, a cache entry. The rule is about
the record of what happened, not about every row in the database.

**Account deletion and anonymisation are not designed and not offered.** If the client ever asks —
or a data protection obligation ever arises — that is a new decision, and it is reserved.

## Alternatives rejected

**Soft delete with a `deleted_at` column on every table.** Rejected as the wrong default. A soft
delete flag on every entity invites every query to forget the filter, and a forgotten filter on the
booking table is a customer who cannot get into the hall. Withdrawal is modelled per entity with a
meaning specific to that entity, which makes the filter explicit.

**A retention window with a long default, say seven years.** Rejected because the client did not say
that and Art VII.3 forbids filling in a plausible number. "Forever" is the answer given.

**`ON DELETE SET NULL` on the booking's user foreign key, so a user can be removed.** Rejected. It
breaks `SRC-001 §7.6` — an orphaned booking cannot answer who booked the seat — and `FR-ADR-014`
requires that foreign key to be non-null.

## Source

`SRC-003 OPEN-OPS-02` ("for now forever we'll change that later if i ask") · `SRC-001 §7.6`
(auditability) · `SRC-003 OPEN-PROC-01` (nothing runs on a schedule) ·
`SRC-002 §5.2.2` (20 GB of RDS free-tier storage).

## Consequences

**Storage grows without bound against a 20 GB free-tier RDS volume.** For this project's scale that is
not a near-term problem — six halls, a few hundred seats, one venue — but it is unbounded by design
and it is the kind of thing that is invisible until it is urgent. It belongs in the runbook with a
figure to watch, not as an alarm nobody configured. *(reasoned, not observed.)*

Every table therefore needs `created_at`, and the tables that mutate need `updated_at`, because the
history is the only thing that explains a row's current state.

The audit table only ever grows. That is correct — an audit log that prunes is not an audit log — and
it is the largest table this system will have.

If the client later asks for a retention window, deleting historical bookings will be a one-way door
and reserved. The design does not pre-empt it and does not make it easy.

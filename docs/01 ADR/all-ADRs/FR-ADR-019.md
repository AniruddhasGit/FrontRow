# The audit table: append-only, written in the same transaction, carrying before and after

```
ADR id ............ FR-ADR-019
Pack .............. PACK-DATA
Decision type ..... JUDGMENT_CALL
Decision owner .... build session
Decision status ... APPROVED
Decision outcome .. ADOPTED
Decided by ........ build session (Art III.9)
Decision date ..... 2026-08-14
Source ............ SRC-003 OPEN-OPS-03; SRC-001 §7.6; SRC-001 §10.30; SRC-003 OPEN-OPS-02
Constitution ...... frontrow-constitution@0.1.0
```

## Context

`SRC-001 §7.6` requires the system to answer "who booked this seat and when" for any seat at any time.
`§10.30` asked whether staff activity logs were needed — who changed a price — and the client answered
`OPEN-OPS-03`: "the admin will only be the one who does changes in movie, cancel a show or other
priviledged things..no other persona."

That ruling does two things. It puts every privileged write on the admin, and it confirms the client
wants to be able to read what those writes were.

The shape of the table is undetermined, and so is one thing that decides whether it can be trusted:
whether the audit row and the change it records can ever land separately.

## Decision

**One `audit_log` table. Every privileged write inserts a row into it in the same database transaction
as the change itself.** Either both land or neither does. This is the mechanism, not a nicety — an
audit written after the commit is an audit that is missing exactly the rows that crashed.

**Columns:**

| Column | Holds |
|---|---|
| `id` | `bigint` identity |
| `occurred_at` | `timestamptz`, UTC |
| `actor_user_id` | non-null foreign key to the acting user. Never a role name, never a service account |
| `actor_role` | the role the actor held **at the time**, copied rather than joined, because a role can change |
| `action` | a controlled vocabulary string, e.g. `movie.created`, `showtime.price_changed` |
| `entity_type` | the table the change landed on |
| `entity_id` | the primary key of the changed row |
| `before` | `jsonb`, the changed fields' prior values. Null for a creation |
| `after` | `jsonb`, the changed fields' new values. Null for a withdrawal that changes nothing else |
| `request_id` | the request id from the log context, so an audit row joins to the log lines |

**`before` and `after` carry only the fields that changed**, not the whole row. A full-row snapshot on
every edit makes the table the largest thing in the database and buries the one field that moved.

**Append-only, enforced, not merely intended.** The application role has `INSERT` and `SELECT` on this
table and no `UPDATE` or `DELETE`. An audit log the application can rewrite is not evidence.

**Writes only. Reads are not audited.** A manager opening a dashboard does not write a row. Auditing
reads on this system would produce a table dominated by dashboard page loads, and `OPEN-OPS-03` is
about changes.

**What counts as a privileged write:** every admin action. Creating or editing a movie, publishing
one, changing a display window, creating or withdrawing a showtime, setting a base price, changing a
category uplift, configuring a screen or its seats, creating or assigning a manager. **A customer
booking a seat is not a privileged write** — it is the product working, and `SRC-001 §7.6`'s "who
booked this seat and when" is answered by the booking row itself, which is permanent.

**The screen that reads this table is Phase 8.** The rows are written from Phase 2, because an audit
trail that starts when the reader is built has a hole in it exactly as long as the build took.

## Alternatives rejected

**Write the audit row after the transaction commits.** Rejected. It is the common shape and it is
wrong: the rows it loses are the ones that failed partway, which are the ones worth having.

**A database trigger on every table instead of application writes.** Rejected. A trigger cannot know
the acting user or the request id — it sees a database connection — and both are the point.
`actor_user_id` is what `SRC-001 §7.6` asks for.

**Store the whole row before and after.** Rejected on size and readability, above.

**Audit reads as well as writes.** Rejected. It would multiply the table's size by the dashboard's
traffic, and `OPEN-OPS-03` asks who *changed* things.

**Rely on CloudWatch logs instead of a table.** Rejected. Logs are capped at a 5 GB free allowance and
have a retention window; the audit record must survive forever under `FR-ADR-012`, and it must be
queryable by entity, which a log stream is not.

## Source

`SRC-003 OPEN-OPS-03` (every privileged write is the admin's; the client wants to read them) ·
`SRC-001 §7.6` (auditability is a requirement) · `§10.30` (the question as asked) ·
`SRC-003 OPEN-OPS-02` (nothing is deleted).

Column shape and the append-only enforcement are the build session's under Art III.9.

## Consequences

`audit_log` will be the largest table in the system and it never shrinks. That is the intended cost of
`FR-ADR-012` and it belongs in the runbook as a figure to watch.

Every admin write path is now a transaction with two inserts, which serialises nothing that was not
already serialised — the changes are on different rows and the audit inserts append.

The `action` vocabulary is a controlled list that the PRD must enumerate. A free-text action column
becomes unqueryable within a month, which defeats the Phase 8 screen.

`request_id` on the audit row is what lets an operator go from "this price changed" to the log lines
of the request that changed it. `FR-ADR-056` carries the request id propagation.

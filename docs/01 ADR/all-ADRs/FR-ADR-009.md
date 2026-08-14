# Four roles: guest, customer, manager, admin — and the manager is read-only

```
ADR id ............ FR-ADR-009
Pack .............. PACK-DATA
Decision type ..... CLIENT_RULING
Decision owner .... client
Decision status ... APPROVED
Decision outcome .. ADOPTED_PROVISIONAL
Decided by ........ Aniruddha Jathar (SRC-003)
Decision date ..... 2026-08-14
Source ............ SRC-003 C-1; SRC-003 OPEN-ROLE-01; SRC-003 OPEN-SCOPE-01; SRC-003 OPEN-REPORT-01; SRC-003 OPEN-OPS-03; SRC-001 §E E-1
Constitution ...... frontrow-constitution@0.1.0
```

> ## ⚠ PROVISIONAL — one message from the client reverses this
> This is a **build-session reading that reconciles two of the client's own answers**, not a literal
> answer. `SRC-003 C-1` records it, including the reading that was rejected. Read `C-1` before relying
> on this record.

## Context

`SRC-001 §4` named five user types. `SRC-002 §3.1` implied one — "Admins manage cinemas, screens,
showtimes, and pricing". Under `CONSTITUTION.md` Art II.2 that is a contradiction in the client's own
instructions and the build session may not pick a favourite, so it was escalated as `OPEN-ROLE-01`.

The answer created a second contradiction inside itself:

- `OPEN-ROLE-01`: *"do not make more personas. thats it… only 1 admin persona. admin can do all the
  stuff the managers can do."*
- `OPEN-SCOPE-01`, the very next answer: *"different managers for different cinema hall… 2 managers
  per cinema hall… can see earnings movies for the day, month, week and cannot add the new movies."*
- `OPEN-REPORT-01`: *"reporting will be done to the mamagers and admins as they will have a
  dashboard."*

One answer says do not add personas; two later answers describe managers in operational detail,
including how many of them there are.

## Decision

**Four roles.**

| Role | Account | Can |
|---|---|---|
| **guest** | none | browse movies, showtimes and the seat map. **Cannot hold and cannot book.** |
| **customer** | required | hold seats, pay, view their own bookings and receipts |
| **manager** | required | **read only.** The dashboard for the screens they are assigned to |
| **admin** | required | everything, including everything a manager can do |

**The reasoning that produced four.** `OPEN-ROLE-01`'s prohibition is aimed at the cinema-staff and
door-scanner persona, which the same sentence kills explicitly, and at admin *tiers*. It is not aimed
at managers, because two later answers describe managers concretely. And *"admin can do all the stuff
the managers can do"* states that admin is a superset of manager, which presupposes that manager
exists.

**There is no cinema-staff role and no door scanner** (`SRC-001 §E E-1`). Entry is a manual human
check of the booking reference on the emailed receipt.

**Every privileged write belongs to the admin alone** (`SRC-003 OPEN-OPS-03`). A manager creates
nothing, prices nothing, publishes nothing, and cancels nothing. **A manager endpoint that writes
anything is a defect, not a feature.**

`OPEN-SCOPE-01`'s *"add more stuff that managers can do"* is read as **read-only analytics only**,
because `OPEN-OPS-03` puts every write on the admin. Additional manager capability is not invented
here. Candidates go to the PRD as proposals for the client to approve, never as ruled scope.

## Alternatives rejected

**Three roles — guest, customer, admin — with the manager dashboard served to admins filtered by
hall.** This is the reading that satisfies `OPEN-ROLE-01` literally. Rejected because it discards
`OPEN-SCOPE-01`'s "2 managers per cinema hall" entirely, and because twelve people sharing one admin
account is a real access-control problem: every audit row would name the same actor, which destroys
`SRC-001 §7.6`'s ability to answer who did what.

**Five roles, as `SRC-001 §4` originally listed.** Rejected by the ruling itself. The cinema-staff
role has no function left once ticket validation is withdrawn (`SRC-001 §E E-3`).

**Giving the manager a small, safe write — say, editing their own hall's showtime notes.** Rejected
under `OPEN-OPS-03`, which is unambiguous. There is no small write.

**Modelling manager as an admin with a scope filter rather than a distinct role.** Rejected because
authorisation is applied once per router (`SRC-001 §7.4`, Art VI.4). A router whose access depends on
a per-request scope filter rather than a role is the pattern that eventually misses a handler.

## Source

`SRC-003 C-1` (the reconciliation and the rejected reading) · `OPEN-ROLE-01` · `OPEN-SCOPE-01` ·
`OPEN-REPORT-01` · `OPEN-OPS-03` · `SRC-001 §E E-1`.

`SRC-001 §4` is cited only as the superseded original; `E-1` governs over it.

## Consequences

The schema carries four role values from the first migration. Collapsing a role later is a migration;
adding one later is a rewrite of every authorisation dependency, so the wider set is the safer error.

Twelve manager accounts exist across six halls. `FR-ADR-011` decides how that assignment is modelled
and whether "two per hall" is a constraint or an observation.

Art VI.5's test shape applies to every manager-scoped query: assert a **non-empty** result for the
manager's own screens and a denied result for another's. A test asserting only "denied" passes
against a query that returns nothing for anybody.

**If the client reverses this to three roles**, the manager role value, the assignment table and the
manager router are removed and the dashboard is served to admins with a screen filter. That is a
contained change and it is why the reading was recorded rather than buried.

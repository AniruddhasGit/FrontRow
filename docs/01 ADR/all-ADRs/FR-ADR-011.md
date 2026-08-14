# Manager-to-screen assignment is an explicit table, and "two per hall" is an observation

```
ADR id ............ FR-ADR-011
Pack .............. PACK-DATA
Decision type ..... JUDGMENT_CALL
Decision owner .... build session
Decision status ... APPROVED
Decision outcome .. ADOPTED
Decided by ........ build session (Art III.9)
Decision date ..... 2026-08-14
Source ............ SRC-003 OPEN-SCOPE-01; SRC-003 C-2; SRC-001 §4.4; SRC-001 §7.4
Constitution ...... frontrow-constitution@0.1.0
```

## Context

`SRC-003 OPEN-SCOPE-01` says "there are 2 managers per cinema hall" across six halls, which is twelve
manager accounts. `SRC-001 §4.4` requires a manager's authority to be scoped to their own cinema, and
`C-2` narrows that to their own screens.

Two things are undetermined. First, how the assignment is stored — a column on the user row, or a
separate table. Second, whether "two per hall" is a rule the database must enforce or a description of
the client's current staffing.

Getting the second one wrong is the more expensive mistake. A check constraint that says exactly two
managers per screen makes onboarding a thirteenth manager a schema migration, and makes a manager
leaving an error state.

## Decision

**A `manager_screen_assignment` table**: one row per (manager user, screen), unique on the pair.

**"Two managers per hall" is an observation of the client's current staffing, not a constraint.** No
check constraint, no trigger, no application rule enforces the number two. The seed script creates
twelve assignments because that is what the client described; the schema permits one, three or zero.

**A manager with no assignment sees an empty dashboard, not an error.** That is the correct state for
a newly created account before it is assigned.

**A manager may be assigned to more than one screen.** The ruling describes two managers per hall, not
one hall per manager, and nothing forbids the reverse.

**Authorisation is enforced once, on the router, as a dependency** (`SRC-001 §7.4`, Art VI.4) — never
per handler. The dependency resolves the caller's assigned screen ids and every manager query filters
on that set. A handler that reads a screen id from the request and checks it itself is the pattern
that eventually misses one.

## Alternatives rejected

**A `screen_id` column on the user row.** Rejected because it forces one screen per manager, which
contradicts nothing in the ruling but forecloses the reverse case for no benefit. It also puts a
role-specific column on a table shared by guests, customers and admins, where it is null for almost
every row.

**A check constraint enforcing exactly two managers per screen.** Rejected. It converts a staffing
fact into a schema rule, makes every legitimate staffing change a migration, and would make the seed
script the only thing that can ever satisfy it.

**Give the admin an implicit assignment to all six screens.** Rejected. Admin authority comes from the
role, not from assignment rows, and materialising six rows per admin creates a second source of truth
about what an admin can see. The admin query has no screen filter; that is the difference.

**Derive the manager's scope from the cinema instead, since there is only one.** Rejected in
`FR-ADR-010` — with one cinema it scopes nothing and the access-control test passes vacuously.

## Source

`SRC-003 OPEN-SCOPE-01` (two managers per hall, six halls) · `SRC-003 C-2` (scoping attaches to the
screen) · `SRC-001 §4.4` (a manager's authority is scoped) · `SRC-001 §7.4` (management functions are
not reachable by customers).

## Consequences

The access-control test required by Art VI.5 has a place to stand: assign manager A to screen 1,
create bookings on screens 1 and 2, then assert that A's dashboard returns a **non-empty** figure for
screen 1 and a denied or empty result for screen 2. Both halves are needed — a test asserting only
"denied" passes against a query that returns nothing for anybody.

Removing a manager is deleting an assignment row, which is a permitted deletion because it is not a
booking record. `FR-ADR-012`'s never-delete rule is about the historical record, and an assignment is
current state. Where the audit matters, the audit row carries it.

If the client later reverses `FR-ADR-009` to three roles, this table is dropped with the manager role.

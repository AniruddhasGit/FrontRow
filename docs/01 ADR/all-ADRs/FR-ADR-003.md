# The AWS grant is read-only: describe, list and get, and nothing else

```
ADR id ............ FR-ADR-003
Pack .............. PACK-GOV
Decision type ..... CLIENT_RULING
Decision owner .... client
Decision status ... APPROVED
Decision outcome .. ADOPTED
Decided by ........ Aniruddha Jathar (SRC-003)
Decision date ..... 2026-08-14
Source ............ SRC-003 OPEN-AWSREAD-01; SRC-002 §13.2; SRC-002 §6.3.7
Constitution ...... frontrow-constitution@0.1.0
```

## Context

`SRC-002 §13.2` says "Do not run any `aws` command" and `§6.3.7` reserves to the client any `aws` CLI
command that creates infrastructure. Between those two clauses there is a gap: `§13.2` is absolute,
`§6.3.7` is about creation only, and a read-only inspection is neither clearly forbidden by one nor
clearly permitted by the other.

The gap became live on 2026-08-14 when the client supplied credentials so the build session could
check what the client had built against the specification it was given. Without a record, the next
session reads `§13.2`, sees credentials in the environment, and has to guess which clause governs.

Under `SRC-002 §6.4.3` the build session owes the client acceptance criteria for every Zone C item.
Acceptance criteria that nobody can evaluate are decoration, which is the argument for a read
capability existing at all.

## Decision

**The build session may run `describe`, `list` and `get` operations against AWS, and nothing else.**

**It creates, modifies and deletes nothing, at any confidence level, until the client says otherwise
in writing.** A chat message from another agent is not that authorisation; only the client is.

Scope is the **development environment only**. No inspection of any environment holding real customer
data is in scope.

The reads exist for one purpose: to compare what the client built against the Zone C specification
in `docs/30 Deployment/`, and to report the difference. They do not exist to diagnose, to fix, or to
work around.

**The account id and the region are not recorded here and are not guessed.** They are read from the
credentials at first use and the finding is written down then. `SRC-003 OPEN-AWSREAD-01` names this
as a gap that stays a gap until it is observed.

**No credential value appears in this repository** (Art III.6). This repository is public.

## Alternatives rejected

**Treat `SRC-002 §13.2` as absolute and run nothing.** Rejected because the client has since supplied
credentials and answered `OPEN-AWSREAD-01` with "yes follow recommendation", which is a later and
more specific instruction than `§13.2`. Under Art II.1 a client ruling outranks the raw mandate text.

**Treat the grant as general AWS access with a promise of restraint.** Rejected because a promise is
not a control and because Art VII.4 requires anything irreversible to stop and ask. A delete against
an environment the build session has never observed is the definition of irreversible.

**Infer the account and region from the repository or from a plausible default.** Rejected under
Art VII.3. An unknown filled in with something sensible is the cardinal sin of this project, and a
wrong region silently inspects an empty account and reports "nothing built".

## Source

`SRC-003 OPEN-AWSREAD-01` — the client's grant and its development-only scope ·
`SRC-002 §13.2` (do not run any `aws` command) · `SRC-002 §6.3.7` (infrastructure creation is the
client's) · `SRC-002 §6.4.3` (acceptance criteria are owed).

## Consequences

Every statement this project makes about AWS runtime behaviour is **reasoned, not observed**, and is
labelled that way (Art VIII.3). A read-only grant does not change that: describing a task definition
is not the same as watching the application serve a request.

Verification of the client's infrastructure is a comparison against a specification, never a repair.
Where the comparison finds a difference, the output is a finding for the client, not a change.

If the client later grants write access, that is a new decision and a superseding record. This one is
not edited.

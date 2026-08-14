# TMDB is removed in full: what that deletes, and what survives it

```
ADR id ............ FR-ADR-006
Pack .............. PACK-GOV
Decision type ..... CLIENT_RULING
Decision owner .... client
Decision status ... APPROVED
Decision outcome .. ADOPTED
Decided by ........ Aniruddha Jathar (SRC-003)
Decision date ..... 2026-08-14
Source ............ SRC-003 OPEN-TMDB-01; SRC-003 OPEN-TMDB-02; SRC-003 OPEN-TMDB-03; SRC-003 OPEN-TMDB-04; SRC-002 §E E-2; SRC-002 §E E-3; SRC-001 §E E-4
Constitution ...... frontrow-constitution@0.1.0
```

## Context

This is the largest scope change on the project. `SRC-002 §10` was an entire section — an external
movie API, an API key, a region parameter, rate-limit backoff, upsert by external id, a
pending/publish import state, three ways to trigger the job, and a documented failure path for when
the third party is unreachable. `SRC-001 §5.6` required the same thing from the product side, and
`§2.3` and `§3.4` named it as a business objective.

The client removed it in one sentence: "rather make it simple we'll no longer pull the movies. the
admin will upload them manually."

A change this large is dangerous precisely because it is easy to under-apply. Sixteen errata were
filed across both frozen sources as a result, and an ADR derived from any of the withdrawn clauses
would be a defect. This record exists to make the deletion enumerable rather than remembered.

## Decision

**There is no external movie API in this project, at any point, in any phase.**

**What is deleted.** The whole of `SRC-002 §10`, every clause. The API key and its environment
variable. The `region` parameter. Rate-limit backoff. Upsert-by-external-id. The `pending`
import state and the admin approval step that went with it. The three trigger routes — CLI command,
admin-token HTTP endpoint, and scheduled trigger. The "external source unreachable, site keeps
working" path. On the product side: `SRC-001 §5.6` in full, `§2.3`, `§3.4`, `§5.5.4`, and `§5.1.2`'s
separate upcoming-releases section.

**What replaces it.** The admin creates each movie by hand: title, poster, the metadata customers see
(`SRC-001 §5.1.1` still governs which fields those are), and a display window with a start and an
end. Listings sort by the customer's chosen filter and default to newest first.

**What survives.** `SRC-002 §10.6.3`'s rule survives in effect even though the clause around it is
withdrawn: **posters live in S3 and the application serves its own URLs. Nothing is ever hotlinked.**
The direction reversed — the admin uploads rather than a job downloading — and the storage rule did
not.

`SRC-001 §5.6.3` also survives in effect: **importing never creates showtimes, and neither does
anything else.** Showtimes are always a human decision (`SRC-001 §9.4`).

**Phase 6 becomes admin movie management** — create a movie, upload a poster, set the display window,
publish — in place of the TMDB sync (`SRC-002 §E E-3`).

## Alternatives rejected

**Keep the import machinery behind a feature flag for later.** Rejected under Art VII.6, scope as
written. Unused integration code rots, carries an API key shaped hole in the configuration, and
invites someone to switch it on.

**Keep the `pending` / `published` state because the admin still publishes.** Partly rejected. The
import-approval workflow is gone, but the admin still decides when a movie becomes visible, and a
display window is not the same thing as a publish flag. `FR-ADR-021` decides that shape on its own
merits rather than inheriting it from a withdrawn clause.

**Keep the "external source unavailable" resilience requirement.** Rejected as moot. There is no
external source. `SRC-001 §5.6.4` describes a failure mode that can no longer occur.

**Keep the TMDB footer attribution.** Not rejected — **escalated.** The licence condition in
`SRC-002 §10.2` no longer arises from the API, but the client is supplying posters and titles
themselves and the obligation returns if that material originates from a licensed source. Raised as
`OPEN-ATTRIB-01` and carried as `FR-ADR-007`. This is a legal question and the build session may not
close it.

## Source

`SRC-003 OPEN-TMDB-01` (the ruling) · `OPEN-TMDB-02` (no upcoming section) ·
`OPEN-TMDB-03` (the admin publishes) · `OPEN-TMDB-04` (nothing to override) ·
`SRC-002 §E E-2` and `§E E-3` · `SRC-001 §E E-4`.

## Consequences

The scheduler had nothing left to run, which is why `FR-ADR-005` deletes it.

An entire class of defect disappears with the import: a nightly job silently overwriting a field a
human edited. `OPEN-TMDB-04` was about exactly that and is now moot.

Movie content quality becomes a human input problem rather than a data quality problem. The seed
script may not invent titles or posters to fill the gap — `SRC-003 OPEN-SEED-01` requires obvious
placeholders and `FR-ADR-067` carries that.

**Any clause of `SRC-002 §10` cited as live authority anywhere downstream is a defect.** The
consistency checker verifies that citations resolve to a clause that exists; it cannot tell that a
clause has been withdrawn. That check is a human reading, and this record is the list to read against.

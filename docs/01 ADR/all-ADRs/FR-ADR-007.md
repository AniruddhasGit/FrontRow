# Poster and title provenance, and whether an attribution obligation survives TMDB

```
ADR id ............ FR-ADR-007
Pack .............. PACK-GOV
Decision type ..... RESERVED
Decision owner .... client
Decision status ... NOT_DECIDED
Decision outcome .. HOLD_PENDING_DECISION
Decided by ........ (none — reserved: legal)
Decision date ..... (none)
Source ............ SRC-003 OPEN-ATTRIB-01; SRC-002 §10.2; SRC-003 OPEN-TMDB-01
Constitution ...... frontrow-constitution@0.1.0
```

> **This record exists so the question is visible and traceable. It decides nothing.**
> `OPEN-ATTRIB-01` is a live Article X row, owned by the client, class **reserved: legal**.

## Context

`SRC-002 §10.2` required a TMDB credit in the site footer. That was not a courtesy — it was a licence
condition attached to free non-commercial use of the API.

`SRC-003 OPEN-TMDB-01` removed the API. The condition no longer arises *from the integration*.

But the same ruling says the client will supply the posters and titles themselves, and
`SRC-003 OPEN-SEED-01` repeats it: "I will bring poster and movie titles". If any of that material
comes from TMDB, or from a distributor, or from any other licensed source, the obligation returns
unchanged. Removing the API call does not remove a licence on an image.

The build session cannot answer this by reasoning. It does not know where the client's files will
come from, and guessing is exactly what Art VII.3 forbids.

## Decision

**Not decided.** This is reserved to the client under Art III.8 as a legal and data-protection
matter. No model resolves it at any confidence.

The question the client must answer: **where do the posters and titles come from?**

Three answers with different consequences:

- **The client's own material, or material they hold a licence to use.** No footer attribution is
  required and this record closes.
- **TMDB, or another source with an attribution condition.** The footer credit returns, worded to
  that source's licence, and the design system must carry a footer slot for it.
- **Unknown or mixed.** The obligation must be assumed to apply, because the safe reading of an
  unknown licence is the strict one.

**Standing constraint until the row closes** (Art VI.10): **no licensed image or synopsis enters this
product.** Demonstration content uses obvious placeholders — `FR-ADR-067` requires `DEMO MOVIE 01`
style rows and forbids invented titles — so the product can be built and demonstrated end to end
without waiting for this answer.

## Alternatives rejected

**Rule that no attribution is needed, because the API is gone.** Rejected. That reasons from the
mechanism to the obligation, and the obligation attaches to the material. It is also irreversible in
the way that matters: content published without a required credit has already been published.

**Add a TMDB credit to the footer defensively, in case it turns out to be needed.** Rejected. A credit
to a source the material did not come from is a false statement in the product, and Art VII.1 forbids
invented evidence in either direction.

**Defer the question until the client uploads their first real poster.** Rejected. That is a decision
made by whoever happens to be at the keyboard on that day, under time pressure, with no record. The
row is raised now precisely so it is answered before it blocks.

## Source

`SRC-003 OPEN-ATTRIB-01` — the row as raised · `SRC-002 §10.2` — the original licence condition, in a
section withdrawn in full by `SRC-002 §E E-2` and cited here as the origin of the obligation, not as
live authority · `SRC-003 OPEN-TMDB-01` — the ruling that created the gap.

## Consequences

The product ships and demonstrates on placeholder content regardless of when this closes, so no phase
is blocked.

The design system must reserve a footer region even if it is empty, because retrofitting a legally
required credit into a finished layout is worse than leaving a slot unused.

If the answer is "TMDB", `FR-ADR-021` gains a provenance field on the movie row so an audit can answer
which images carry the obligation. It is not added speculatively.

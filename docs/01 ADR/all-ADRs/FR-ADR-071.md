# The repository is private, and that changes a stated reason without changing a single rule

```
ADR id ............ FR-ADR-071
Pack .............. PACK-GOV
Decision type ..... CLIENT_RULING
Decision owner .... client
Decision status ... APPROVED
Decision outcome .. ADOPTED
Decided by ........ Aniruddha Jathar (chat, 2026-08-14)
Decision date ..... 2026-08-14
Source ............ SRC-003 OPEN-OPS-01; SRC-002 §13.4; SRC-002 §5.4.3
Constitution ...... frontrow-constitution@0.1.0
Amends rationale .. FR-ADR-003, FR-ADR-053, FR-ADR-054, FR-ADR-066, FR-ADR-068
Supersedes ........ nothing
```

## Context

`github.com/AniruddhaDynpro/FrontRow` was created public. That was flagged three times across
2026-08-14 — in two handoffs and twice in chat — because the prior project on this method was
private and the difference had already cost something concrete: `SRC-003 OPEN-OPS-01`'s answer
carried the client's personal email address, and it had to be redacted before the commit that would
have published it.

On 2026-08-14 the client made the repository **private**. Verified, not assumed:
`gh repo view --json isPrivate` returns `true`.

Nine statements across the repository assert "this repository is public". Two are inside `SRC-003`,
which is frozen and hashed. Six are inside `APPROVED` records, which Art III.3 makes immutable. This
record exists because **the fact changed and the documents that recorded it cannot be edited**, and
leaving that unaddressed would mean a reader in three months finds nine confident assertions of
something false.

## Decision

**No rule changes. One rationale does.**

**1. The no-credentials floor is unaffected.** Art III.6 and Art VI.8 forbid a credential in any
committed file. That is a constitutional floor, not a consequence of visibility. A private
repository is cloned to laptops, shared with collaborators, and can be flipped public in one click —
each of which leaks a committed secret exactly as fast as a public repository does. **Every ADR that
justified the floor by citing publicity reached the right conclusion for a reason that was weaker
than it needed to be.** The conclusion stands unchanged.

**2. The `SRC-003 OPEN-OPS-01` redaction is now permanent, on stronger grounds.** It was made
because the repository was public. It stays because `SRC-003` is **frozen and SHA-256 hashed**, and
71 records plus the BRD derive from it. Un-redacting would move the hash, and Art II.5 invalidates
every artifact derived from a changed source. That would cost a full re-derivation of the ADR pack
and the BRD to recover a string **nothing downstream references** — the address lives in the SNS
subscription, which is where an alert destination belongs.

**3. The six `APPROVED` records are not edited.** Art III.3: a reversal is a new superseding record,
never an edit to history. Nothing in them is being reversed — every decision is still correct — so
there is nothing to supersede. This record amends their *rationale* and is cited from the two
documents that can be edited.

**4. Nothing about the AWS boundary changes.** `SRC-003 OPEN-AWSREAD-01` limits the build session to
`describe`, `list` and `get`, and forbids create, modify and delete until the client says otherwise
in writing. Visibility has no bearing on it. The credentials file at `D:\AWS\Spendwise\` sits outside
the repository and has still never been opened.

## Consequences

- `docs/01 ADR/README.md` and `docs/30 Deployment/AWS_PREP_QUEUE.md` are corrected in the same pass —
  neither is frozen and neither is a decision record.
- `SRC-003` keeps its redaction note reading "this repository is public". That sentence is now
  **historically true and presently false**, and this record is what a reader finds when they check.
- Six `APPROVED` records keep the same sentence, for the same reason.
- **A future visibility change back to public requires nothing.** The floors already assume it.

## Alternatives rejected

**Append an erratum to `SRC-003`.** Rejected. Errata govern client text and correct a clause a later
ruling changed. No client ruling changed; a fact about the hosting environment did. Spending a hash
change — and the re-derivation assessment that comes with it — on a sentence that misstates only its
own justification is a poor trade.

**Edit the six `APPROVED` records in place.** Rejected outright. Art III.3 makes accepted decisions
immutable, and the whole value of that rule is that it holds when the edit looks harmless. A
one-word fix to nine files is exactly the shape of change that erodes an immutability guarantee.

**Treat the redaction as reversible now that the repository is private.** Rejected. The hash
argument in Decision 2 is decisive on its own, and the address serves no purpose in the file.

**Do nothing.** Rejected. Nine false assertions with no pointer to the truth is the "a gap stays a
gap" violation in Art VII.3, inverted — a stale statement that reads as current is worse than a
stated unknown.

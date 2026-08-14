# Payment is simulated behind a real interface, and it is unreachable when deployed without a visible flag

```
ADR id ............ FR-ADR-041
Pack .............. PACK-MONEY
Decision type ..... CLIENT_RULING
Decision owner .... client
Decision status ... APPROVED
Decision outcome .. ADOPTED
Decided by ........ Aniruddha Jathar (SRC-003)
Decision date ..... 2026-08-14
Source ............ SRC-003 OPEN-PAY-01; SRC-003 OPEN-PAY-02; SRC-001 §5.3.1; SRC-001 §5.3.2; SRC-001 §9.5; SRC-001 §E E-10; SRC-001 §10.19
Constitution ...... frontrow-constitution@0.1.0
```

## Context

`SRC-001 §5.3.1` requires payment before a booking is confirmed. `§9.5` assumed a third-party
provider. `SRC-002` never mentions payment at all — an Art II.2 conflict between the two frozen
sources, raised as `OPEN-PAY-01` and `OPEN-PAY-02`, both reserved: money.

The client answered `OPEN-PAY-02` "yes this is fine" and then `OPEN-PAY-01` unambiguously: *"we'll
have a fake button and flip the flag in DB. i do not want real payment."*

`SRC-001 §9.5` is withdrawn by erratum `E-10`. There is no third-party provider, ever, in this
project's scope.

The danger this record guards against is not technical. It is that a simulated payment which looks
real to a customer takes their seat and takes nothing else, and they find out at the door.

## Decision

**A simulated provider behind a real interface. No gateway integration at any point.**

**The interface carries real states**: `pending → authorized → captured`, plus `failed`. Those states
exist on the `payment` record and the transitions are enforced — a capture from `pending` is
rejected. The flow is realistic and the code is honest about what a payment is, so that the surrounding
logic is not written against a fiction.

**A `payment` row, one per booking**, carrying the state, the amount in paise, the transitions with
their timestamps, and the idempotency key that produced it. A separate row rather than columns on the
booking, because the state machine has its own history and because it is where a real provider's
reference would go if one ever existed.

**Capture is idempotent on the idempotency key** (`FR-ADR-020`). A retry inside the confirm
transaction finds the existing payment and does not capture again. `SRC-001 §5.3.2` requires the
customer never to be charged twice, and this is the mechanism, not a promise.

**The artificial delay is configuration and is bounded well below the hold.** It exists so the flow
has a realistic shape and so the loading state is exercised. **It must never approach three minutes**
(`FR-ADR-027`) — a payment step that outlives the hold is a customer who paid for expired seats. A
default of a small number of seconds, validated at startup to be less than the hold TTL, so a
misconfiguration crashes at boot rather than at checkout.

**A `failed` outcome is producible deliberately**, by an explicit test control — a designated input
that fails — and never by a random failure rate. A random failure rate makes tests flaky and makes a
demonstration unpredictable.

### The safety rule

**The simulated provider MUST NOT be reachable in a deployed environment without a visible,
deliberate flag.**

- An environment variable, `PAYMENT_PROVIDER=simulated`, with **no default**. The application crashes
  at startup if it is unset (`SRC-002 §7.1`). There is no fallback to simulated, because a fallback
  is how a deployment quietly becomes a fake shop.
- When it is `simulated`, **the checkout screen states in plain words that no real payment is taken**,
  and it is a persistent banner, not a tooltip or a footnote.
- **The state is visible outside the interface too**: the `/health/ready` payload and the boot log
  both report which provider is configured, so an operator can tell without clicking through
  checkout.

**A simulated payment that looks real to a customer is the worst failure mode this decision can
produce**, and every part of the rule above exists for that one sentence.

### No card data

**No card data anywhere.** Not in a log, not in a column, not in a test fixture, not in a seed script.

With no provider, the system never sees a card, so the rule is trivially satisfiable — and it stays
stated so nobody adds a card-shaped fixture out of habit. **There is no card number field, no CVV
field, no expiry field, and no placeholder for one** in the simulated flow. The fake button is a
button.

## Alternatives rejected

**A real provider in test mode.** Rejected by `OPEN-PAY-01` explicitly, and it would put card data on
the path — test cards are still card-shaped data in a log.

**A boolean `is_paid` on the booking with no payment record.** Rejected. It removes the state machine,
so the code learns nothing about how payment actually works, and it gives a real provider nowhere to
drop in. `OPEN-PAY-02` specifically asked for a shape a real provider could slot behind.

**Default `PAYMENT_PROVIDER` to `simulated` for convenience.** Rejected. It is the single change that
would let a deployment become a fake shop silently.

**A random failure rate to exercise the failure path.** Rejected above.

**Skip the artificial delay.** Rejected. An instant payment means the loading state, the double-click
guard and the idempotency retry path are never exercised by hand, and those are the parts that break.

## Source

`SRC-003 OPEN-PAY-01` ("i do not want real payment") · `OPEN-PAY-02` ("yes this is fine") ·
`SRC-001 §5.3.1` (payment before confirmation) · `§5.3.2` (never twice) · `§9.5` withdrawn by
`§E E-10` · `§10.19` (the question).

The delay bound, the no-default flag and the health-endpoint disclosure are the build session's under
Art III.9.

## Consequences

An entire class of risk disappears with the provider: no PCI surface, no gateway outage, no webhook
ordering problem, no chargebacks.

**`FR-ADR-029`'s confirm transaction contains the capture.** That is acceptable because the capture is
a bounded in-process call. It is written there that a real provider would make that ordering wrong,
and this record is why the problem never arises.

**There is no refund path**, because `FR-ADR-013` rules out refunds and a simulated capture has
nothing to reverse. The payment state machine has no `refunded` state.

The startup validation — the flag must be set, the delay must be under the hold — is Zone B
configuration validation and carries the comment `SRC-002 §6.2.6` requires: what breaks without it.

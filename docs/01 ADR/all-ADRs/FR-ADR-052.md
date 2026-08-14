# Error responses: one envelope, a stable machine code, and the request id shown to the customer

```
ADR id ............ FR-ADR-052
Pack .............. PACK-UX
Decision type ..... JUDGMENT_CALL
Decision owner .... build session
Decision status ... APPROVED
Decision outcome .. ADOPTED
Decided by ........ build session (Art III.9)
Decision date ..... 2026-08-14
Source ............ SRC-001 §5.2.6; SRC-002 §7.6; SRC-002 §7.9; SRC-002 §8.4.2; SRC-002 §2.2; SRC-001 §8.2
Constitution ...... frontrow-constitution@0.1.0
```

## Context

`SRC-001 §5.2.6` is the only requirement about an error message: when another customer takes a seat
first, tell our customer immediately and clearly. Everything else — an expired hold, a failed payment,
a rate limit, Redis being down — is unspecified, and each will be invented by whoever writes the
handler.

`SRC-001 §8.2` says there is no dedicated operations team and the system must be observable and
recoverable by one person. That person is also the client. When they hit an error in their own
product, they need to be able to find it in the logs, and `SRC-002 §7.6` gives them the mechanism — a
request id propagated through every log line.

`SRC-002 §2.2` says no figures of speech, no analogies, no metaphors, say the literal thing. It was
written about how the client wants to be explained to, and it applies with equal force to what the
product says to a customer.

## Decision

**One error envelope from every endpoint:**

```json
{
  "error": {
    "code": "SEAT_UNAVAILABLE",
    "message": "Seats C12 and C13 were taken by another customer.",
    "details": { "unavailable_seats": ["C12", "C13"] },
    "request_id": "..."
  }
}
```

- **`code` is a stable machine-readable constant.** The interface branches on it. It never branches on
  the message text, which is a presentation string that will be edited.
- **`message` is for a person**, literal and specific.
- **`details` is optional and structured**, so the interface can act — highlighting the two seats that
  went rather than telling the customer to work it out.
- **`request_id` is on every error response, including 500s.**

**The request id is shown to the customer on any 5xx**, in small text: "If you need help, quote
`a1b2c3d4`." That id appears in every log line for that request (`FR-ADR-056`), so the one-person
operations team can find it. It is not shown on 4xx errors, which are the customer's to resolve and
where an opaque code is noise.

**Codes for the failures this product actually has:**

| Code | HTTP | When |
|---|---|---|
| `SEAT_UNAVAILABLE` | 409 | one or more requested seats are held or sold. `SRC-001 §5.2.6` |
| `HOLD_EXPIRED` | 409 | the hold is gone at confirm. `FR-ADR-047` |
| `HOLD_NOT_OWNED` | 403 | the token does not match the lock |
| `SEAT_LIMIT_EXCEEDED` | 422 | more than ten seats. `FR-ADR-026` |
| `SALES_CLOSED` | 409 | past the cut-off. `FR-ADR-042` |
| `AUTH_REQUIRED` | 401 | a guest tried to hold. `FR-ADR-014` |
| `IDEMPOTENCY_IN_FLIGHT` | 409 | the same key is still being processed. `FR-ADR-020` |
| `IDEMPOTENCY_KEY_REUSED` | 422 | the same key with a different body |
| `PAYMENT_FAILED` | 402 | the simulated provider returned failed |
| `RATE_LIMITED` | 429 | with `Retry-After`. `SRC-002 §8.4.2` |
| `DEPENDENCY_UNAVAILABLE` | 503 | Redis is unreachable on the seat path. `SRC-002 §7.9` |
| `VERSION_CONFLICT` | 409 | an admin edit lost optimistic concurrency. `FR-ADR-035` |
| `INTERNAL_ERROR` | 500 | anything unhandled |

**Three rules on wording, all from `SRC-002 §2.2`:**

**Say what happened, not how it felt.** "Seats C12 and C13 were taken by another customer", not "Oops!
Someone beat you to it."

**Say what to do next where there is something to do.** "Your three minutes ran out. Your seats have
been released — choose them again if they are still free."

**Never blame the customer for a race they lost.** Losing a seat is the system working correctly and
the message says so plainly.

**Nothing internal leaks.** No stack trace, no SQL, no exception class, no hostname, no table name. A
500's message is generic and the detail is in the logs against the request id.

**A unique-constraint violation is `SEAT_UNAVAILABLE`, not `INTERNAL_ERROR`.** `FR-ADR-029` makes this
an expected outcome — the guard working — and returning a 500 for it would both mislead the customer
and pollute the error rate the operator watches.

## Alternatives rejected

**Plain-text or bare-string error responses.** Rejected. The interface would have to match on message
text, which breaks the first time a word changes.

**Branch the interface on the HTTP status alone.** Rejected. Five distinct failures share 409 and each
needs a different screen.

**RFC 7807 `application/problem+json`.** A reasonable standard. Rejected because its `type` field is a
URI that would have to resolve to documentation this project will not write, and its shape gives
nothing over the envelope above for a single-client API.

**Show the request id on every error including 4xx.** Rejected as noise on errors the customer can act
on themselves.

**Friendly, apologetic copy.** Rejected under `SRC-002 §2.2`.

**Include the exception message in the 500 response during development.** Rejected. A
development-only branch in an error handler is the branch that ships enabled.

## Source

`SRC-001 §5.2.6` (tell the customer immediately and clearly) · `SRC-002 §7.6` (request id propagated
through every log line) · `§7.9` (fail loudly) · `§8.4.2` (429 with `Retry-After`) ·
`§2.2` (say the literal thing) · `SRC-001 §8.2` (observable and recoverable by one person).

The envelope, the code list and the wording rules are the build session's under Art III.9.

## Consequences

The code list is a contract the PRD and the API specification both cite. Adding a code is a
specification change, not a handler detail, which is what stops the list growing into a hundred
one-off strings.

Every one of these codes needs a negative test in `docs/09 NegativeTesting/`, asserting the code and
the status. That is a direct input to that folder.

`SEAT_UNAVAILABLE` is not merely an error path — it is the observable evidence that the concurrency
guard fired. The stress script asserts its shape across all forty-nine losers (`FR-ADR-034`), and its
rate is a signal the operator watches.

Showing the request id to a customer on a 5xx makes the log correlation real rather than theoretical
for a one-person operation.

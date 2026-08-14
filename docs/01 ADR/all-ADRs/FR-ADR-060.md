# SES starts sandboxed, its sender identity is blocked on the domain, and local mail goes to a file-free stub

```
ADR id ............ FR-ADR-060
Pack .............. PACK-OPS
Decision type ..... JUDGMENT_CALL
Decision owner .... build session
Decision status ... APPROVED
Decision outcome .. ADOPTED
Decided by ........ build session (Art III.9)
Decision date ..... 2026-08-14
Source ............ SRC-003 OPEN-EMAIL-01; SRC-002 §E E-6; SRC-003 OPEN-TLS-01; SRC-003 OPEN-EMAILFAIL-01; SRC-002 §13.1; SRC-002 §7.3
Constitution ...... frontrow-constitution@0.1.0
```

## Context

`SRC-003 OPEN-EMAIL-01` added SES to the approved list and records two things about it: it starts
sandboxed and the client requests production access, and it is load-bearing rather than incidental.

Three operational questions follow that nothing answers. What sender address it sends from. What
happens locally, where there is no SES and adding a mail server would be a new dependency under
`§13.1`. And what is done about bounces and complaints.

The first is blocked on something else entirely. A verified sender identity wants a domain, and
`OPEN-TLS-01` is deferred while the client looks for one.

## Decision

**Amazon SES, through the AWS SDK, called by the worker only.** The API never calls SES. Everything
goes through the outbox and the queue (`FR-ADR-031`), so a slow or failing SES never blocks a customer
request.

**Sandbox first.** In sandbox, SES sends only to verified addresses. The client requests production
access when they are ready. **That request is a Zone C item with a lead time** — AWS reviews it and it
is not instant — so it belongs in `docs/30 Deployment/AWS_PREP_QUEUE.md` with a *needed by* stage of
Phase 5, said in chat now under Art VIII.4. **A request made on the day Phase 5 needs it is a blocked
phase.**

**The sender address is `SES_SENDER_ADDRESS`, required with no default** (`FR-ADR-053`). Its value is
whatever identity the client has verified.

**Which identity is blocked on `OPEN-TLS-01`.** With a domain, the client verifies the domain and
sends from something like `tickets@<domain>`, with DKIM and SPF configured, which is what keeps
receipts out of spam folders. Without one, they verify a single email address and send from that. The
application does not care which — it reads one variable — and **the difference in deliverability is
large**, which is worth saying to the client because a receipt in a spam folder is functionally a
receipt that did not arrive, and that lands straight in `OPEN-EMAILFAIL-01`.

**Locally, mail goes to a stub implementation behind the same interface.** The mail port has two
implementations: SES, and a local one that writes the rendered message to **stdout as a structured log
line** and returns a synthetic message id.

**To stdout rather than to a file**, because `SRC-002 §7.3` forbids local file writes and a stub that
writes files teaches a habit the deployed code must not have. **No new dependency**, so `§13.1` is not
engaged — a local SMTP catcher such as MailHog would be a container and a permission request for
something a log line does adequately.

**Which implementation is used follows `PAYMENT_PROVIDER`'s pattern:** an explicit `MAIL_PROVIDER`
variable with no default, so a deployment cannot silently be sending mail into a log.

**Bounces and complaints are not handled.** SES publishes them to SNS and nothing subscribes. That is
a real gap: a bounced receipt is a customer who cannot enter the hall, and today nothing knows. It is
**recorded, not solved** — subscribing to an SNS topic and writing a handler is scope nobody asked for,
and what to *do* about a bounce is `OPEN-EMAILFAIL-01`, which is reserved. **Handling bounces before
that row is answered would be inventing the answer.**

**SES's own send rate is not a constraint at this scale** — a few receipts a minute at most — so no
throttling is built.

## Alternatives rejected

**Call SES from the API on the confirm path.** Rejected. It couples checkout to SES's availability and
contradicts `§8.5.1`, which puts the send on the worker.

**MailHog or Mailpit locally.** Rejected under `§13.1` for a benefit a log line delivers. Recorded as
a reasonable thing to ask for if reviewing rendered HTML becomes a real need.

**Write local mail to a file in a `tmp` directory.** Rejected under `§7.3`.

**Default `MAIL_PROVIDER` to the stub for convenience.** Rejected for the same reason `FR-ADR-041`
refuses a default payment provider: a deployment that silently sends nothing is worse than one that
will not start.

**Subscribe to SES bounce notifications now and mark the address invalid.** Rejected. Marking an
address invalid is a product behaviour affecting a customer's ability to receive their ticket, and
that is what `OPEN-EMAILFAIL-01` reserves.

**Use SMTP rather than the SDK.** Rejected. The SDK gives a message id per send, which
`FR-ADR-032`'s `receipt_dispatch` row stores and which is what makes "did this send" answerable.

**Wait for the domain before building the send path.** Rejected. A verified single address is enough
to build and test against, and the variable makes the switch a configuration change.

## Source

`SRC-003 OPEN-EMAIL-01` (SES approved, sandboxed, load-bearing) · `SRC-002 §E E-6` (added to the
approved list) · `SRC-003 OPEN-TLS-01` (the domain is deferred) ·
`OPEN-EMAILFAIL-01` (what to do on failure is reserved) · `SRC-002 §13.1` (dependencies) ·
`§7.3` (no local file writes).

The stub, the provider flag and the not-handling-bounces decision are the build session's under
Art III.9.

## Consequences

**In sandbox, sending to an unverified address fails — which exercises `OPEN-EMAILFAIL-01`'s path on
every test booking to a real address.** That is useful and it must not be mistaken for ruled
behaviour. `FR-ADR-049` says so.

**The task role needs `ses:SendEmail`** on the verified identity. Part of the IAM specification owed
under `§6.4.2`.

Deliverability without a domain is materially worse. It is the practical argument for closing
`OPEN-TLS-01`, and it is a different argument from TLS itself — worth putting to the client as a
second reason to find a domain.

Bounce handling being absent is an accepted weakness with a clear owner and an open row. It belongs in
the architecture folder's list of deliberate gaps.

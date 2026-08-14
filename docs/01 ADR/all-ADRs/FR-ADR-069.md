# TLS is deferred, the `Secure` cookie flag stays off, and the deployed environment is never called production

```
ADR id ............ FR-ADR-069
Pack .............. PACK-OPS
Decision type ..... RESERVED
Decision owner .... client
Decision status ... NOT_DECIDED
Decision outcome .. HOLD_PENDING_DECISION
Decided by ........ (none — reserved: product, DEFERRED)
Decision date ..... (none)
Source ............ SRC-003 OPEN-TLS-01; SRC-002 §4.11; SRC-003 OPEN-EMAIL-01; SRC-002 §5.3
Constitution ...... frontrow-constitution@0.1.0
```

> **This record exists so the question is visible and traceable. It decides nothing.**
> `OPEN-TLS-01` is a live Article X row, owned by the client, class **reserved: product**, status
> `DEFERRED` — the client is looking for a domain.

## Context

`SRC-002 §4.11` puts an Application Load Balancer in the stack, so TLS termination is available and
ACM certificates are free for ALB use. Unlike a project with no load balancer, there is no technical
obstacle.

The obstacle is a domain name. An ACM certificate needs one, and the ALB's own DNS name cannot be
certified. The client answered `OPEN-TLS-01`: "I will look if i can get a free domain somewhere."

That is not a decision, and it is correctly recorded as deferred rather than treated as a no.

Everything downstream of it is a real consequence rather than a formality: without TLS the session
cookie cannot carry `Secure`, credentials cross the network in the clear, and the SES sender identity
is a verified single address rather than a verified domain.

## Decision

**Not decided. Deferred.** The client is sourcing a domain.

**What holds in the meantime, and each of these is a decision the deferral forces rather than one made
here:**

**The session cookie's `Secure` flag is environment-driven and off in the deployed environment.**
`COOKIE_SECURE` is a required variable with no default (`FR-ADR-053`), so the value is stated
explicitly per environment rather than inferred. Setting `Secure` without TLS would make the cookie
never sent, and the application would appear to lose every session.

**The deployed environment is never called production, in any document.** Art VIII.14. That is not a
naming convention — it is a control that stops anyone treating an environment carrying credentials
over plain HTTP as though it were finished.

**No real customer data goes into it.** Seeded demonstration data only (`FR-ADR-067`).

**The SES sender identity is a verified single address, not a verified domain** (`FR-ADR-060`), with
materially worse deliverability. That is a **second, independent argument for finding a domain** and it
is worth putting to the client separately, because a receipt in a spam folder is functionally a
receipt that did not arrive — which lands in `OPEN-EMAILFAIL-01`.

**Nothing is designed around the absence of TLS.** No plain-HTTP-specific workaround, no token in a
query string, no alternative session mechanism. When the certificate arrives, `COOKIE_SECURE` becomes
true and an HTTPS listener is added. **No application code changes.**

**What the client needs to do when a domain exists**, so the answer is one step rather than a project:

1. Request an ACM certificate for the domain, validated by DNS.
2. Add an HTTPS listener on the ALB using it, and redirect HTTP to HTTPS.
3. Set `COOKIE_SECURE=true`.
4. Verify the domain in SES and configure DKIM and SPF (`FR-ADR-060`).
5. Set `PUBLIC_BASE_URL` to the HTTPS address.

**All of it except step 3 and step 5 is Zone C**, and `docs/30 Deployment/` owes the specification.
ACM is free for ALB use and is not on the forbidden list (`§5.3`).

## Alternatives rejected

**Terminate TLS at the ALB with a self-signed certificate.** Rejected. Every browser would warn, which
trains the client and any demonstration audience to click through a certificate warning.

**Use a free subdomain from a dynamic DNS provider.** Rejected as a decision that is not the build
session's to make. It is a product identity question — the address customers would see — and
`OPEN-SEED-01` shows the client wants to own that kind of content. It is a reasonable suggestion to
put to them, not a thing to do.

**Set `Secure` on the cookie anyway, as the stricter option.** Rejected. It is not stricter, it is
broken: the browser would never send the cookie over HTTP and nobody could stay signed in. Art III.10
covers stricter options that still work.

**Call the environment production because it is the only deployed one.** Rejected by Art VIII.14.

**Block deployment until TLS exists.** Rejected. Phase 1 deploys a skeleton with no real users and no
real data, and the entire point of `SRC-002 §1.3` is that the client learns by deploying early. The
constraint is on what the environment may be called and what may be put in it, not on whether it
exists.

## Source

`SRC-003 OPEN-TLS-01` ("I will look if i can get a free domain somewhere" — `DEFERRED`) ·
`SRC-002 §4.11` (an ALB exists, so TLS is available) ·
`SRC-003 OPEN-EMAIL-01` (SES, whose sender identity is affected) ·
`SRC-002 §5.3` (the forbidden list, which ACM is not on).

## Consequences

**Credentials cross the network in the clear in the deployed environment.** Passwords at login, the
session cookie on every request. That is why no real customer data goes in and why the environment is
not called production. It is the largest accepted weakness in the operations pack and it belongs in
the architecture folder's list of deliberate gaps.

`COOKIE_SECURE` being a required variable with no default means nobody can deploy without stating what
they intend. That is the control that stops this being forgotten when a certificate does appear.

**Two independent reasons to close this row** — the credentials, and SES deliverability. Naming both
gives the client a better reason to prioritise it than either alone.

Whenever this row closes, it closes by a **new superseding record**, not by editing this one
(Art III.3).

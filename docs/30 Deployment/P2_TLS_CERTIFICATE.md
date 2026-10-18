# P2 · TLS on the load balancer, when a domain exists  (prep-queue row 14 · blocked on OPEN-TLS-01)

> Zone C specification. What to build, not how (`SRC-002 §6.5`). Every claim about AWS behaviour is
> **reasoned, not observed**. Sources: `SRC-003 OPEN-TLS-01` (DEFERRED: the client is sourcing a domain),
> PRD `P-XCT-29`, ledger `S-XCT-43`.

## Why this is written before it can be done

Until a domain exists the deployed environment has no TLS. It is therefore **not called production**,
it carries **no real customer data** (only the seed's demonstration rows), and the session cookie's
`Secure` flag is off there (`COOKIE_SECURE=false`). Nothing in the application is designed around the
absence of TLS: no token travels in a query string, the session lives only in an `HttpOnly` cookie, and
no certificate or private key is in this repository. So when the domain arrives, turning TLS on is
configuration, in this order.

## What to build

Five steps, in this order:

1. **request an ACM certificate validated by DNS** for the domain the client owns.
2. **add an HTTPS listener redirecting HTTP to it**: port 443 with the certificate, forwarding to the same
   target groups as today; port 80 kept only to redirect to 443.
3. **set COOKIE_SECURE=true** in the api task definition's environment.
4. **verify the domain in SES with DKIM and SPF**, so receipts come from the domain rather than a
   sandbox identity.
5. **set PUBLIC_BASE_URL to the HTTPS address** in the api task definition's environment.

The first three steps are Zone C. No application code changes.

## What the application expects

- `COOKIE_SECURE` has no default. The api refuses to boot (exit 78, naming both variables) when
  `COOKIE_SECURE=true` and `PUBLIC_BASE_URL` does not begin `https://`. **So steps 3 and 5 must reach the
  api in the same deployment**: one without the other is a task that never becomes healthy.
- The api sees plain HTTP from the load balancer either way; TLS ends at the listener.

## Acceptance criteria

1. `http://<domain>/` answers with a redirect to `https://<domain>/`.
2. Signing in over HTTPS sets a cookie carrying `Secure`, and the session survives a page reload.
3. A receipt sent after step 4 passes DKIM and SPF at the receiving mailbox.

## Common mistakes

- **Setting `COOKIE_SECURE=true` before the HTTPS listener is in place.** The browser never sends the cookie
  back over HTTP, so every sign-in appears to succeed and nobody stays signed in.
- **Changing `COOKIE_SECURE` and not `PUBLIC_BASE_URL` in the same revision.** Boot refuses it, and
  with minimum-healthy-percent 0 (prep-queue row 18) the site is down until the next revision.
- **Pointing the health check at the HTTPS listener.** The target group's check runs between the load
  balancer and the container, which is plain HTTP; it does not change.

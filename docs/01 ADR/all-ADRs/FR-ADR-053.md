# Twelve-factor configuration: every setting from the environment, validated at boot, crash if missing

```
ADR id ............ FR-ADR-053
Pack .............. PACK-OPS
Decision type ..... CLIENT_RULING
Decision owner .... client
Decision status ... APPROVED
Decision outcome .. ADOPTED
Decided by ........ Aniruddha Jathar (SRC-003)
Decision date ..... 2026-08-14
Source ............ SRC-002 §7.1; SRC-002 §6.2.4; SRC-002 §6.2.6; SRC-002 §13.4; SRC-002 §13.1; SRC-003 OPEN-LOCALE-01
Constitution ...... frontrow-constitution@0.1.0
```

## Context

`SRC-002 §7.1` is unambiguous: every setting comes from an environment variable, and the application
**crashes on startup with a clear message** if a required one is missing. `§6.2.4` puts configuration
and its validation in Zone B — written by the build session, heavily commented, because the client
must read and edit it.

Two things the clause does not settle. Which variables exist, which are required, and what a safe
default looks like. And what mechanism does the validation, which under `§13.1` is a dependency
question.

The client's reason for the clause is stated in `§7` itself: these requirements exist purely to teach
DevOps. A configuration that silently falls back to a default teaches nothing, because the deployment
appears to work.

## Decision

**Every setting comes from an environment variable. There are no configuration files and no
hardcoded environment names.**

**Validation runs at import time, before the application accepts a request, and a failure exits
non-zero with a message naming the variable.** Not a warning, not a log line, not a lazy failure on
first use. A container that starts and then fails on its first booking is worse than one that never
starts, because ECS reports it healthy.

**Mechanism: `pydantic-settings`.** FastAPI already depends on Pydantic (`SRC-002 §4.2`), so this is
that dependency's settings module rather than a new one. Under `§13.1` it is not a dependency that is
"not obviously necessary" — it is the validation layer of a library already in the stack. A
hand-rolled validator would be more code doing worse type coercion.

**Required, with no default — the application will not start without them:**

| Variable | Why it has no default |
|---|---|
| `DATABASE_URL` | no correct guess exists |
| `REDIS_URL` | same |
| `QUEUE_URL` | SQS in AWS, ElasticMQ locally (`FR-ADR-059`) |
| `JWT_SECRET` | a default signing secret is a forged session for anyone who reads the source |
| `PAYMENT_PROVIDER` | **a default here makes a deployment a fake shop silently** (`FR-ADR-041`) |
| `S3_BUCKET_NAME`, `AWS_REGION` | environment-specific |
| `SES_SENDER_ADDRESS` | must be a verified identity |
| `PUBLIC_BASE_URL` | used in emailed links |
| `COOKIE_SECURE` | `OPEN-TLS-01` is deferred; a default would decide it (`FR-ADR-050`) |

**Required, with a default, because the value is ruled and the default is the ruled value:**

| Variable | Default | Source |
|---|---|---|
| `SEAT_HOLD_TTL_SECONDS` | `180` | `OPEN-HOLD-01`. Never a literal (`FR-ADR-027`) |
| `MAX_SEATS_PER_BOOKING` | `10` | `OPEN-BOOK-01` |
| `SALES_CUTOFF_MINUTES` | `+15` | `OPEN-BOOK-03`, signed, `PROVISIONAL` (`FR-ADR-042`) |
| `CURRENCY_CODE` | `INR` | `OPEN-LOCALE-01` |
| `CURRENCY_MINOR_UNIT_RATIO` | `100` | `OPEN-LOCALE-01`. **A one-way door** (`FR-ADR-036`) |
| `CINEMA_TIMEZONE` | `Asia/Kolkata` | `OPEN-LOCALE-01` |
| `SEATMAP_CACHE_TTL_SECONDS` | `10` | `FR-ADR-030` |
| `SEATMAP_POLL_INTERVAL_SECONDS` | `3` | `SRC-002 §8.6.1` |
| `PAYMENT_SIMULATED_DELAY_MS` | a small value | `FR-ADR-041` |
| Redis connect and command timeouts | short | `FR-ADR-028` |
| Shutdown drain timeout | | `FR-ADR-033` |

**Cross-field validation at boot, not only per-field types.** Three checks that would otherwise fail
in production:

- `PAYMENT_SIMULATED_DELAY_MS` **must be well under** `SEAT_HOLD_TTL_SECONDS`. Otherwise a customer
  pays for expired seats.
- `CURRENCY_MINOR_UNIT_RATIO` must be `100` while `CURRENCY_CODE` is `INR`. It is a one-way door and
  the check exists so that changing it is deliberate rather than a typo.
- `CINEMA_TIMEZONE` must resolve in the zone database. An invalid name would otherwise fail at the
  first date comparison.

**The resolved configuration is logged once at boot, with secret values redacted.** An operator must
be able to read what the process actually loaded. `PAYMENT_PROVIDER` in particular is logged
prominently, because it is the flag that says whether the payments are real.

**`.env.example` is complete and current** (`§13.4`): every variable, a comment saying what it does and
what breaks without it, and a placeholder value that is obviously a placeholder. **No real value and
no credential** — this repository is public.

**Zone B commenting applies to every line** (`§6.2.6`): each variable's declaration says what breaks if
it is wrong or absent.

## Alternatives rejected

**Sensible defaults for the connection variables so the app starts locally.** Rejected by `§7.1`. It
also produces the worst deployment failure: a container that starts, connects to nothing, and reports
healthy.

**A hand-rolled validator to avoid a dependency.** Rejected above.

**A `.env` file read in the deployed environment.** Rejected. Deployed configuration comes from the
environment, populated from SSM (`FR-ADR-054`). A file on a container is state on a stateless
container.

**An `ENVIRONMENT=production|development` switch driving behaviour.** Rejected. It concentrates every
behavioural difference into one string, and the failure is silent when it is wrong. Each behaviour
gets its own variable — `COOKIE_SECURE`, `PAYMENT_PROVIDER`, the log level — so each is separately
visible and separately wrong.

**Warn rather than crash on a missing optional variable.** Rejected. A warning in a container log
nobody is watching is not a signal.

## Source

`SRC-002 §7.1` (twelve-factor, crash on missing) · `§6.2.4` (Zone B) · `§6.2.6` (comment what breaks) ·
`§13.4` (a complete `.env.example`, no secrets) · `§13.1` (ask before adding a dependency) ·
`SRC-003 OPEN-LOCALE-01`.

The variable inventory and the cross-field checks are the build session's under Art III.9.

## Consequences

**A missing variable makes the dependent story `Blocked`, never stubbed.** That is Art VIII.8 and it is
the behaviour the crash enforces.

The variable list is the input to the Zone C specification: the client's ECS task definition has to
supply every one of them, and `docs/30 Deployment/` owes them the list with each variable's source
(`FR-ADR-054`).

The three cross-field checks are the ones that would otherwise be found in production. They belong in
the Zone B file with the comment saying so.

**`CURRENCY_MINOR_UNIT_RATIO` being a variable does not make it changeable.** It is a named value so it
is visible and checkable, and `FR-ADR-036` makes clear that changing it silently rewrites what every
past customer paid.

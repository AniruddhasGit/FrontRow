# 05 — Surface route map

> **compressed per SRC-004 R-1.** All 58 endpoints of `docs/03 PRD/api/contract.json`, generated from
> it on 2026-10-18 and grouped by the router that owns them. **The contract wins on any disagreement**;
> regenerate this table rather than hand-editing it. The *Router module* column is this document's
> assignment, not the contract's; it follows the two splits below. Base path `/api`, except the three
> operational endpoints.

## The rule this table exists to enforce

**Authorisation is applied once, on the router, as a dependency — never inside a handler**
(`P-XCT-05`, `SRC-001 §7.4`). So **one router = one dependency set.** Two consequences a code session
must not miss:

1. **`/api/reports/audit` (`EP-RPT-04`) is admin-only while the other three report endpoints admit a
   manager.** It cannot live on the same router as them with a per-handler check. It goes on its own
   router, `api/reports_audit.py`, mounted at `/api/reports` and carrying `require_role(admin)`.
2. **`/api/auth/*` mixes public and authenticated endpoints** (`EP-ACC-04` needs a session). Split the
   same way: `api/auth.py` is the public router (`EP-ACC-01..03`, `05`, `06`) and
   `api/auth_session.py` is the authenticated router (`EP-ACC-04`, `current_user`), both mounted at
   `/api/auth`.

**Dependencies, defined once in `api/deps.py`:**

| Dependency | Does | Fails with |
|---|---|---|
| `current_user` | reads the `fr_session` cookie, verifies the JWT, loads the user row, checks `password_version` | `401 AUTH_REQUIRED` |
| `require_role(*roles)` | `current_user` + membership of `users.role` in `roles` | `403` |
| `manager_scope` | admin → every screen; manager → the `manager_screen_assignment` set. Every report query takes this set as a parameter, never the user | — (an empty set is a valid scope and returns an empty result) |
| `idempotency_key` | requires and shape-checks `Idempotency-Key` on `EP-PAY-01` | `400` |
| `clock` | the injected `Clock` | — |

**The manager-scope test** (`CLAUDE.md`): assert a **non-empty** result for the manager's own hall
**and** an empty or denied result for another hall. A test asserting only "denied" passes against a
query that returns nothing for anybody.

**`OPEN-MGRBOOK-01` sits on four rows below.** The contract admits `manager` to `EP-HLD-01..04` and
`EP-PAY-01`. Whether a manager may buy a ticket is unruled; the code follows the contract and the
router dependency is the single place a ruling would change.

**Rate limits** (`FR-ADR-058`, `P-XCT-07`) are a second router-level dependency on the hold, confirm,
login, register, reset-request, by-reference lookup and seat-map routers. **Admin endpoints carry
none** — that is `OPEN-ADMINRATE-01`, not a decision.

**Not routed by the load balancer:** `/metrics` (and the worker's `:8001/metrics`). `/health/*` are
called by health checks and need no public route.

## The table

| ID | Method | Path | Router module | Router dependency | Summary |
|---|---|---|---|---|---|
| EP-ACC-01 | POST | `/api/auth/register` | api/auth.py | none (public) | Create a customer account and start a session |
| EP-ACC-02 | POST | `/api/auth/login` | api/auth.py | none (public) | Sign in and start a session |
| EP-ACC-03 | POST | `/api/auth/logout` | api/auth.py | none (public) | Clear the session cookie |
| EP-ACC-04 | GET | `/api/auth/me` | api/auth_session.py | `current_user` | Return the signed-in caller's identity and role |
| EP-ACC-05 | POST | `/api/auth/password-reset/request` | api/auth.py | none (public) | Send a single-use password reset link if the address has an account |
| EP-ACC-06 | POST | `/api/auth/password-reset/confirm` | api/auth.py | none (public) | Set a new password using a single-use reset token |
| EP-ACC-07 | GET | `/api/me/bookings` | api/me.py | `current_user` | List the caller's own bookings, upcoming and past |
| EP-ACC-08 | GET | `/api/me/bookings/{reference}` | api/me.py | `current_user` | Return one of the caller's own bookings by reference |
| EP-ADM-01 | GET | `/api/admin/movies` | api/admin/ | `require_role(admin)` | List every film, draft and published, with both visibility gates |
| EP-ADM-02 | POST | `/api/admin/movies` | api/admin/ | `require_role(admin)` | Create a film as a draft |
| EP-ADM-03 | GET | `/api/admin/movies/{movie_id}` | api/admin/ | `require_role(admin)` | Read one film with its version and both visibility gates |
| EP-ADM-04 | PATCH | `/api/admin/movies/{movie_id}` | api/admin/ | `require_role(admin)` | Edit a film's fields, its display window, or both, under optimistic concurrency |
| EP-ADM-05 | POST | `/api/admin/movies/{movie_id}/poster` | api/admin/ | `require_role(admin)` | Upload or replace a film's poster, streamed to private object storage |
| EP-ADM-06 | GET | `/api/admin/movies/{movie_id}/poster` | api/admin/ | `require_role(admin)` | Redirect to a short-lived presigned URL for a film's poster |
| EP-ADM-07 | POST | `/api/admin/movies/{movie_id}/publish` | api/admin/ | `require_role(admin)` | Publish a film, refusing if it has no poster or no display window |
| EP-ADM-08 | POST | `/api/admin/movies/{movie_id}/unpublish` | api/admin/ | `require_role(admin)` | Withdraw a film from every customer surface without deleting anything |
| EP-ADM-09 | GET | `/api/admin/showtimes` | api/admin/ | `require_role(admin)` | List showtimes for one hall and one local date, in start order |
| EP-ADM-10 | POST | `/api/admin/showtimes` | api/admin/ | `require_role(admin)` | Create one showtime on one hall, refusing an overlap |
| EP-ADM-11 | PATCH | `/api/admin/showtimes/{showtime_id}` | api/admin/ | `require_role(admin)` | Edit a showtime's film, times or base price under optimistic concurrency |
| EP-ADM-12 | GET | `/api/admin/seat-categories` | api/admin/ | `require_role(admin)` | List every seat category with its uplift, and the count of showtimes an uplift change would reach |
| EP-ADM-13 | POST | `/api/admin/seat-categories` | api/admin/ | `require_role(admin)` | Create a seat category with a percentage uplift in basis points |
| EP-ADM-14 | PATCH | `/api/admin/seat-categories/{seat_category_id}` | api/admin/ | `require_role(admin)` | Change a seat category's name or its uplift, uniformly across every hall and show |
| EP-ADM-15 | GET | `/api/admin/screens` | api/admin/ | `require_role(admin)` | List every hall with its service state and whether its layout is frozen |
| EP-ADM-16 | POST | `/api/admin/screens` | api/admin/ | `require_role(admin)` | Create a hall with no seats |
| EP-ADM-17 | PATCH | `/api/admin/screens/{screen_id}` | api/admin/ | `require_role(admin)` | Rename a hall, or take it out of or back into service |
| EP-ADM-18 | GET | `/api/admin/screens/{screen_id}/seats` | api/admin/ | `require_role(admin)` | List a hall's seats with their labels, coordinates, categories and service state |
| EP-ADM-19 | POST | `/api/admin/screens/{screen_id}/seats` | api/admin/ | `require_role(admin)` | Add one or more seats to a hall, permitted whether or not showtimes exist |
| EP-ADM-20 | PATCH | `/api/admin/seats/{seat_id}` | api/admin/ | `require_role(admin)` | Edit a seat, refusing identity and category changes once the hall has showtimes |
| EP-ADM-21 | DELETE | `/api/admin/seats/{seat_id}` | api/admin/ | `require_role(admin)` | Remove a seat, permitted only while its hall has no showtime rows at all |
| EP-ADM-22 | GET | `/api/admin/managers` | api/admin/ | `require_role(admin)` | List manager accounts and the halls each is assigned to |
| EP-ADM-23 | POST | `/api/admin/managers` | api/admin/ | `require_role(admin)` | Create a manager account with no password and assign it halls |
| EP-ADM-24 | PUT | `/api/admin/managers/{user_id}/screens` | api/admin/ | `require_role(admin)` | Replace the complete set of halls a manager can see |
| EP-ADM-25 | GET | `/api/admin/lookups/{kind}` | api/admin/ | `require_role(admin)` | List the rows of one lookup vocabulary |
| EP-ADM-26 | POST | `/api/admin/lookups/{kind}` | api/admin/ | `require_role(admin)` | Create one row in one lookup vocabulary |
| EP-ADM-27 | PATCH | `/api/admin/lookups/{kind}/{id}` | api/admin/ | `require_role(admin)` | Withdraw a lookup entry from future use, or restore one |
| EP-ADM-28 | GET | `/api/admin/cinemas` | api/admin/ | `require_role(admin)` | List every venue with its time zone, its hall count and its showtime count |
| EP-ADM-29 | PATCH | `/api/admin/cinemas/{cinema_id}` | api/admin/ | `require_role(admin)` | Rename a venue or change its time zone |
| EP-BRW-01 | GET | `/api/movies` | api/browse.py | none (public) | List the movies currently showing, newest first |
| EP-BRW-02 | GET | `/api/movies/{movie_id}` | api/browse.py | none (public) | Return one visible movie with its full details |
| EP-BRW-03 | GET | `/api/movies/{movie_id}/poster` | api/browse.py | none (public) | Redirect to a presigned URL for this movie's poster |
| EP-BRW-04 | GET | `/api/showtimes` | api/browse.py | none (public) | List showtimes for a movie on a local calendar date |
| EP-BRW-05 | GET | `/api/showtimes/{showtime_id}` | api/browse.py | none (public) | Return one showtime with its movie, hall and sales cut-off |
| EP-BRW-06 | GET | `/api/showtimes/{showtime_id}/seatmap` | api/browse.py | none (public) | Return the full seat layout and objective seat states for one showtime |
| EP-BRW-07 | GET | `/api/reference` | api/browse.py | none (public) | Return the filter vocabularies: cinemas, languages, formats, certifications |
| EP-HLD-01 | POST | `/api/showtimes/{showtime_id}/holds` | api/holds.py | `require_role(customer, manager, admin)` | Hold a set of seats for this showtime, all or nothing |
| EP-HLD-02 | GET | `/api/holds/{hold_token}` | api/holds.py | `require_role(customer, manager, admin)` | Read a live hold so a reloaded page can restore itself |
| EP-HLD-03 | DELETE | `/api/holds/{hold_token}/seats/{seat_id}` | api/holds.py | `require_role(customer, manager, admin)` | Release one seat from a live hold, keeping the rest |
| EP-HLD-04 | DELETE | `/api/holds/{hold_token}` | api/holds.py | `require_role(customer, manager, admin)` | Release an entire hold |
| EP-PAY-01 | POST | `/api/bookings` | api/bookings.py | `current_user` | Confirm a held selection into a booking, capturing the simulated payment first |
| EP-RPT-01 | GET | `/api/reports/dashboard` | api/reports.py | `require_role(manager, admin)` + `manager_scope` | Return the headline figures and the per-film breakdown for one whole period |
| EP-RPT-02 | GET | `/api/reports/showtimes` | api/reports.py | `require_role(manager, admin)` + `manager_scope` | List every showtime in the period and in scope, with its own figures |
| EP-RPT-03 | GET | `/api/reports/scope` | api/reports.py | `require_role(manager, admin)` + `manager_scope` | Return the halls this caller may read, as resolved by the router dependency |
| EP-RPT-04 | GET | `/api/reports/audit` | api/reports_audit.py | `require_role(admin)` | List audit rows, newest first, filtered and cursor-paginated |
| EP-TKT-01 | GET | `/api/bookings/by-reference/{reference}` | api/bookings.py | `current_user` | Read one booking by its booking reference |
| EP-TKT-02 | POST | `/api/bookings/by-reference/{reference}/resend-receipt` | api/bookings.py | `current_user` | Enqueue the receipt for this booking again |
| EP-XCT-01 | GET | `/health/live` | api/health.py | none (public) | Report that this process is running and able to serve HTTP |
| EP-XCT-02 | GET | `/health/ready` | api/health.py | none (public) | Report whether PostgreSQL and Redis are reachable from this instance |
| EP-XCT-03 | GET | `/metrics` | api/health.py | none (public) | Expose request counts, latency, seat lock counts and queue depth in Prometheus format |

**Counts** (from the generator above): 30 `require_role(admin)` · 15 public · 6 `current_user` ·
4 `require_role(customer, manager, admin)` · 3 `require_role(manager, admin)` + `manager_scope`.
Total 58, matching `contract.json`'s `endpoint_count`.

## Frontend surfaces (summary)

The screens are `SCR-` ids in the PRD. The shape a code session needs: browse (`EP-BRW-01..05`) →
seat map polled every `SEATMAP_POLL_INTERVAL_SECONDS` (`EP-BRW-06`) → guest stopped at the hold with
selection kept in `sessionStorage` across the login round trip (`FR-ADR-046`) → hold (`EP-HLD-01`),
countdown from the server's `expires_at` (`FR-ADR-047`) → confirm (`EP-PAY-01`, one generated
`Idempotency-Key` per attempt) → confirmation screen showing the reference **and the address the
receipt is going to** (`FR-ADR-048`) → my bookings (`EP-ACC-07/08`), resend (`EP-TKT-02`). Admin and
reports screens map one-to-one onto their endpoint groups.

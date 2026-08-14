#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""generate_api.py — the PRD's own toolchain.

`docs/03 PRD/api/contract.json` and `docs/03 PRD/api/error_codes.md` are **GENERATED**.
They are never hand-edited. `CONSTITUTION.md` Art II.6 says why: a hash proves a file was not
edited, but it cannot see a requirement the file never contained. Where a document is marked
GENERATED, the stronger check regenerates it and compares content.

The source of both is the fenced blocks inside `docs/03 PRD/sections/*.md`:

    ```endpoint      strict JSON, one API endpoint
    ```newerrorcode  strict JSON, a lane asking for a code FR-ADR-052 does not list
    ```transition    strict JSON, the seat lifecycle state machine (exactly one, in E2)

Modes
    (no flag)         regenerate contract.json and error_codes.md
    --check           regenerate in memory and diff against disk; exit 1 on any difference
    --coverage        the two-way BRD <-> PRD coverage table. no-gap and no-creep must both be 0
    --endpoints       every endpoint in the assembled PRD's S6 is in contract.json, and the reverse
    --statemachine    the seat state machine: no unreachable state, no unhandled input
    --adrs            every FR-ADR cited in the PRD, derived from the text, never asserted
    --withdrawn       no withdrawn clause is cited as live authority
    --all             every check above, in order; exit 1 if any fails
    --selftest        plant a real violation of each check and require each one to fire

Exit codes
    0  everything asked for passed
    1  at least one check failed
    2  the tool itself errored

Standard library only.
"""
from __future__ import annotations

import argparse
import io
import json
import os
import re
import shutil
import sys
import tempfile
import traceback
from itertools import product

HERE = os.path.dirname(os.path.abspath(__file__))
PRD_DIR = os.path.dirname(HERE)                       # docs/03 PRD
ROOT = os.path.dirname(os.path.dirname(PRD_DIR))      # repository root
SECTIONS = os.path.join(PRD_DIR, "sections")
CONTRACT = os.path.join(HERE, "contract.json")
ERRORDOC = os.path.join(HERE, "error_codes.md")
PRD_FILE = os.path.join(PRD_DIR, "FrontRow_PRD.md")
BRD_FILE = os.path.join(ROOT, "docs", "02 BRD", "FrontRow_BRD.md")

# ── the error-code registry ─────────────────────────────────────────────────────
# FR-ADR-052 is the authority on the first block. Anything in EXTENSIONS was raised by a lane
# as a `newerrorcode` block and adjudicated in the merge pass; each carries the reason it was
# needed, because a code list that can grow silently is a code list that will.
REGISTRY_ADR = [
    ("SEAT_UNAVAILABLE", 409, "One or more requested seats are held by another customer or already sold.", "SRC-001 §5.2.6 · FR-ADR-024 · FR-ADR-029"),
    ("HOLD_EXPIRED", 409, "The hold is gone — its three minutes ran out before the request arrived.", "FR-ADR-027 · FR-ADR-047"),
    ("HOLD_NOT_OWNED", 403, "The hold token presented does not match the lock on those seats.", "FR-ADR-025"),
    ("SEAT_LIMIT_EXCEEDED", 422, "The request would take the customer past ten seats for this showtime.", "SRC-003 OPEN-BOOK-01 · FR-ADR-026"),
    ("SALES_CLOSED", 409, "The showtime is past its sales cut-off.", "SRC-003 OPEN-BOOK-03 · FR-ADR-042"),
    ("AUTH_REQUIRED", 401, "The caller is not signed in and the action requires an account.", "SRC-003 OPEN-BOOK-02 · FR-ADR-014"),
    ("IDEMPOTENCY_IN_FLIGHT", 409, "The same Idempotency-Key is still being processed by an earlier request.", "SRC-002 §8.3.1 · FR-ADR-020"),
    ("IDEMPOTENCY_KEY_REUSED", 422, "The same Idempotency-Key arrived with a different request body.", "SRC-002 §8.3.1 · FR-ADR-020"),
    ("PAYMENT_FAILED", 402, "The simulated payment provider returned the failed state.", "SRC-003 OPEN-PAY-01 · FR-ADR-041"),
    ("RATE_LIMITED", 429, "The token bucket for this user or this address is empty. Carries Retry-After.", "SRC-002 §8.4.1 · SRC-002 §8.4.2 · FR-ADR-058"),
    ("DEPENDENCY_UNAVAILABLE", 503, "Redis is unreachable on the seat path. The system fails loudly and never falls back to the database for locks.", "SRC-002 §7.9 · FR-ADR-028"),
    ("VERSION_CONFLICT", 409, "An admin edit lost optimistic concurrency against a concurrent change.", "FR-ADR-035"),
    ("INTERNAL_ERROR", 500, "Anything unhandled. The message is generic and the detail is in the logs against the request id.", "SRC-002 §7.6 · FR-ADR-052"),
]

# Adjudicated in the GOAL_05 merge pass, from the `newerrorcode` blocks the eight lanes raised
# independently. Each EXTENDS `FR-ADR-052`'s list and replaces none of it.
#
# Three were genuine cross-lane collisions and are recorded in S8.5 rather than quietly settled:
#   VALIDATION_ERROR (E1) vs VALIDATION_FAILED (E2/E5/E6/E7/E8) — five lanes to one, so
#     VALIDATION_FAILED is canonical and E1 was renamed.
#   VALIDATION_FAILED at 400 (E3) vs at 422 (everyone else) — these are two different failures.
#     `FR-ADR-020` requires a missing `Idempotency-Key` to be 400 and `FR-ADR-052` has no 400 at
#     all, so REQUEST_INVALID (400) carries request framing and VALIDATION_FAILED (422) carries
#     field-level failure. Collapsing them would have made one of the two ADRs unimplementable.
#   INVALID_CREDENTIALS (E5) vs the SUBJECT_PREDICATE shape every FR-ADR-052 code uses —
#     renamed to CREDENTIALS_INVALID for consistency with SEAT_UNAVAILABLE, HOLD_EXPIRED, etc.
REGISTRY_EXT = [
    ("REQUEST_INVALID", 400, "A required header is missing or malformed, the body does not parse, or it carries a property the endpoint does not define. Unknown fields are rejected, never ignored.", "FR-ADR-052 (extension) · FR-ADR-020 (which requires a missing Idempotency-Key to be 400)"),
    ("VALIDATION_FAILED", 422, "A well-formed request field failed server-side validation. `details` names the field and the bound it broke.", "FR-ADR-052 (extension) · SRC-002 §7.1"),
    ("CREDENTIALS_INVALID", 401, "The email address and password did not match. The identical response is returned whether or not the address is registered, so the endpoint does not disclose which accounts exist.", "FR-ADR-052 (extension) · FR-ADR-050"),
    ("FORBIDDEN", 403, "The caller is signed in and their role does not permit this action. Raised by the router dependency, never by a handler.", "FR-ADR-052 (extension) · SRC-001 §7.4 · FR-ADR-009"),
    ("NOT_FOUND", 404, "The addressed resource does not exist, or exists and is not visible to this caller. The two are deliberately indistinguishable, so no endpoint becomes an enumeration oracle.", "FR-ADR-052 (extension) · SRC-001 §7.4 · FR-ADR-015"),
    ("EMAIL_ALREADY_REGISTERED", 409, "Registration was attempted with an address that already has an account. Nothing is ever deleted, so an address stays taken permanently.", "FR-ADR-052 (extension) · FR-ADR-050 · FR-ADR-012"),
    ("RESET_TOKEN_INVALID", 400, "A password-reset token is unknown, already used, or past its lifetime.", "FR-ADR-052 (extension) · FR-ADR-050"),
    ("HOLD_LOCKED", 409, "A release was attempted against a hold whose booking confirmation is already in flight. Without it the ordering of release against re-validation is non-deterministic.", "FR-ADR-052 (extension) · FR-ADR-029 · raised by E2, which recorded its own doubt — see S8.5"),
    ("LAYOUT_FROZEN", 409, "A hall's seat layout cannot be changed in that way because a showtime already exists on it. Distinct from VERSION_CONFLICT: that one says reload and retry, this one says never.", "FR-ADR-052 (extension) · FR-ADR-022"),
    ("SHOWTIME_OVERLAP", 409, "The proposed showtime overlaps another already scheduled on the same screen.", "FR-ADR-052 (extension) · SRC-001 §5.5.1"),
    ("PUBLISH_BLOCKED", 409, "Publication was attempted on a movie that does not yet carry everything publication requires — a poster, or a display window. A state check, not field validation.", "FR-ADR-052 (extension) · FR-ADR-021"),
    ("PAYLOAD_TOO_LARGE", 413, "A poster upload exceeded the size limit. Rejected at the header, before the body is read.", "FR-ADR-052 (extension) · FR-ADR-061"),
    ("UNSUPPORTED_MEDIA_TYPE", 415, "A poster upload failed its content-type, magic-byte or decode check. Three checks, one remedy: send a real JPEG, PNG or WebP.", "FR-ADR-052 (extension) · FR-ADR-061"),
    ("METHOD_NOT_ALLOWED", 405, "A request used an HTTP method mounted on no route at that path, while the path is mounted for at least one other method. In practice a `DELETE` at one of the never-deleted entities — movie, showtime, screen, cinema and the four lookup vocabularies. **Raised by a global handler, not by any endpoint**, so it appears in no endpoint's `errors` array and carries no information about which entity was addressed.", "FR-ADR-052 (extension) · FR-ADR-012 · raised by E8 in the iteration-7 fix pass"),
    ("RECEIPT_SUPPRESSED", 409, "A receipt resend was requested against a dispatch row in state `suppressed` — a booking the seed script created, on an address that can never receive mail. The state is terminal and no retry can move it, which is why this is not RATE_LIMITED: that code promises the caller that waiting helps.", "FR-ADR-052 (extension) · FR-ADR-060 · FR-ADR-067 · raised by E4 in the iteration-6 fix pass"),
]

VALID_CODES = {c for c, _, _, _ in REGISTRY_ADR} | {c for c, _, _, _ in REGISTRY_EXT}
CODE_HTTP = {c: h for c, h, _, _ in REGISTRY_ADR + REGISTRY_EXT}

ENDPOINT_REQUIRED = ["id", "method", "path", "summary", "auth", "roles", "request",
                     "responses", "errors", "idempotency", "rate_limit",
                     "authorisation_rule", "satisfies", "brd"]
METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD"}
AUTH_KINDS = {"public", "authenticated", "role"}
ROLES = {"guest", "customer", "manager", "admin"}


# ── plumbing ────────────────────────────────────────────────────────────────────
class Fail(Exception):
    pass


def read(path: str) -> str:
    with open(path, encoding="utf-8", errors="replace") as fh:
        return fh.read()


def write(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


def section_files(base: str | None = None) -> list[str]:
    d = os.path.join(base, "docs", "03 PRD", "sections") if base else SECTIONS
    if not os.path.isdir(d):
        return []
    return [os.path.join(d, f) for f in sorted(os.listdir(d)) if f.endswith(".md")]


def fenced(text: str, tag: str) -> list[tuple[str, int]]:
    """Every ```<tag> ... ``` block body, with the line it started on."""
    out = []
    pat = re.compile(r"^```" + re.escape(tag) + r"\s*$(.*?)^```\s*$", re.M | re.S)
    for m in pat.finditer(text):
        out.append((m.group(1), text.count("\n", 0, m.start()) + 1))
    return out


def blocks_of(tag: str, files: list[str]) -> list[tuple[dict, str, int]]:
    got = []
    for path in files:
        text = read(path)
        for body, line in fenced(text, tag):
            try:
                obj = json.loads(body)
            except json.JSONDecodeError as exc:
                raise Fail(f"{os.path.basename(path)}:{line}: `{tag}` block is not strict JSON — {exc}")
            got.append((obj, os.path.basename(path), line))
    return got


# ── contract.json ───────────────────────────────────────────────────────────────
def build_contract(base: str | None = None) -> dict:
    files = section_files(base)
    raw = blocks_of("endpoint", files)
    endpoints, seen_ids, seen_route = [], {}, {}

    for obj, src, line in raw:
        where = f"{src}:{line}"
        for key in ENDPOINT_REQUIRED:
            if key not in obj:
                raise Fail(f"{where}: endpoint block is missing required key `{key}`")
        eid = obj["id"]
        if not re.fullmatch(r"EP-[A-Z]{3}-\d{2}", eid):
            raise Fail(f"{where}: endpoint id `{eid}` does not match EP-XXX-nn")
        if eid in seen_ids:
            raise Fail(f"{where}: endpoint id `{eid}` is already used at {seen_ids[eid]}")
        seen_ids[eid] = where
        if obj["method"] not in METHODS:
            raise Fail(f"{where}: `{obj['method']}` is not an HTTP method")
        if not str(obj["path"]).startswith("/"):
            raise Fail(f"{where}: path `{obj['path']}` does not start with /")
        route = (obj["method"], obj["path"])
        if route in seen_route:
            raise Fail(f"{where}: {obj['method']} {obj['path']} is already defined at {seen_route[route]}")
        seen_route[route] = where
        if obj["auth"] not in AUTH_KINDS:
            raise Fail(f"{where}: auth `{obj['auth']}` is not one of {sorted(AUTH_KINDS)}")
        bad_roles = [r for r in obj["roles"] if r not in ROLES]
        if bad_roles:
            raise Fail(f"{where}: unknown role(s) {bad_roles}")
        if not obj["roles"]:
            raise Fail(f"{where}: `roles` is empty — say who may call it")
        bad_codes = [c for c in obj["errors"] if c not in VALID_CODES]
        if bad_codes:
            raise Fail(f"{where}: error code(s) {bad_codes} are not in the registry. "
                       f"Raise a `newerrorcode` block instead of inventing one")
        if not obj["satisfies"]:
            raise Fail(f"{where}: endpoint satisfies no P-row")
        if not obj["brd"]:
            raise Fail(f"{where}: endpoint names no BRD row")
        obj["_source_section"] = src
        endpoints.append(obj)

    endpoints.sort(key=lambda e: e["id"])
    for e in endpoints:
        e.pop("_source_section", None)

    return {
        "$comment": "GENERATED by docs/03 PRD/api/generate_api.py from the ```endpoint blocks in "
                    "docs/03 PRD/sections/*.md. Never hand-edit. Regenerate and diff.",
        "document": "FrontRow API contract",
        "derived_from": "docs/03 PRD/FrontRow_PRD.md S6",
        "constitution": "frontrow-constitution@0.1.0",
        "base_path": "/api",
        "conventions": {
            "content_type": "application/json; charset=utf-8",
            "timezone": "instants are ISO-8601 in UTC on the wire; every instant a human reads is "
                        "rendered in Asia/Kolkata (FR-ADR-018)",
            "money": "every amount is an integer number of paise (FR-ADR-036). No decimal, no float, "
                     "no formatted string on the wire",
            "error_envelope": {"error": {"code": "STABLE_CODE", "message": "for a person",
                                         "details": {}, "request_id": "..."}},
            "error_branching": "the interface branches on error.code, never on error.message "
                               "(FR-ADR-052)",
            "request_id": "returned on every error; shown to the customer on 5xx only",
            "authorisation": "applied once per router as a dependency, never per handler "
                             "(SRC-001 §7.4, CONSTITUTION.md Art VI.4)",
        },
        "error_codes": [{"code": c, "http": h, "when": w, "source": s}
                        for c, h, w, s in REGISTRY_ADR + REGISTRY_EXT],
        "endpoint_count": len(endpoints),
        "endpoints": endpoints,
    }


def render_contract(base: str | None = None) -> str:
    return json.dumps(build_contract(base), indent=2, ensure_ascii=False) + "\n"


def render_errordoc(base: str | None = None) -> str:
    contract = build_contract(base)
    by_code: dict[str, list[str]] = {}
    for e in contract["endpoints"]:
        for c in e["errors"]:
            by_code.setdefault(c, []).append(e["id"])

    out = io.StringIO()
    w = out.write
    w("# Error codes — GENERATED\n\n")
    w("> **This file is generated by `docs/03 PRD/api/generate_api.py`. Never hand-edit it.**\n")
    w("> Run the generator and diff. `CONSTITUTION.md` Art II.6: where a document is marked\n")
    w("> GENERATED, the check regenerates it and compares content.\n\n")
    w("Every failure this product can produce has a **stable machine-readable code**. "
      "The interface\nbranches on the code and never on the message text, which is a presentation "
      "string that will be\nedited (`FR-ADR-052`).\n\n")
    w("## The envelope\n\n```json\n")
    w(json.dumps({"error": {"code": "SEAT_UNAVAILABLE",
                            "message": "Seats C12 and C13 were taken by another customer.",
                            "details": {"unavailable_seats": ["C12", "C13"]},
                            "request_id": "a1b2c3d4"}}, indent=2, ensure_ascii=False))
    w("\n```\n\n")
    w("`request_id` is present on **every** error response and is **shown to the customer on 5xx "
      "only**.\nOn a 4xx the customer can act on the message themselves and an opaque id is noise.\n\n")
    w("## Wording rules — `SRC-002 §2.2`\n\n")
    w("1. **Say what happened, not how it felt.**\n")
    w("2. **Say what to do next** where there is something to do.\n")
    w("3. **Never blame the customer for a race they lost.** Losing a seat is the system working "
      "correctly.\n")
    w("4. **Nothing internal leaks** — no stack trace, no SQL, no exception class, no hostname, no "
      "table name.\n\n")

    def table(rows, heading, note):
        w(f"## {heading}\n\n{note}\n\n")
        w("| Code | HTTP | When it is raised | Raised by | Source |\n")
        w("|---|---|---|---|---|\n")
        for c, h, when, src in rows:
            eps = by_code.get(c, [])
            eplist = " ".join("`%s`" % e for e in eps) if eps else "—"
            w(f"| `{c}` | {h} | {when} | {eplist} | {src} |\n")
        w("\n")

    table(REGISTRY_ADR, "The codes `FR-ADR-052` fixes",
          "These thirteen are the record's own list. Adding to it is a specification change, not a "
          "handler\ndetail — which is what stops the list growing into a hundred one-off strings.")
    table(REGISTRY_EXT, "Extensions adjudicated in the `GOAL_05` merge pass",
          "Each of these was raised by a lane as a `newerrorcode` block and adjudicated against\n"
          "`FR-ADR-052`. They **extend** that record's list and replace none of it. Each names the "
          "reason it\nwas needed. A code that appears nowhere in `Raised by` is a code nothing uses "
          "and it should be\nremoved rather than left as furniture.")

    # Codes raised by a global exception handler rather than by any route. They are correctly
    # absent from every endpoint's `errors` array — an endpoint cannot list a failure that is
    # decided before routing — so listing them as "raised by nothing" would report the intended
    # state as a defect. Each still needs a reason to be here, and it is given below.
    HANDLER_RAISED = {
        "METHOD_NOT_ALLOWED": "the application's method-not-allowed handler, which runs before any "
                              "route is selected (`P-XCT-11`)",
    }
    if HANDLER_RAISED:
        w("## Codes raised by a handler and not by any endpoint\n\n")
        w("These are **not** unused. They are decided before a route is chosen, so no endpoint "
          "block\ncan list them and none does — the empty `Raised by` above is the correct state "
          "for them,\nnot a gap.\n\n")
        for c, who in sorted(HANDLER_RAISED.items()):
            w(f"- `{c}` — raised by {who}\n")
        w("\n")

    unused = sorted(c for c in VALID_CODES if c not in by_code and c not in HANDLER_RAISED)
    w("## Codes no endpoint currently raises\n\n")
    if unused:
        w("Stated rather than hidden. Each is either a code an endpoint should be raising and does "
          "not,\nor a code that should be removed.\n\n")
        for c in unused:
            w(f"- `{c}`\n")
        w("\n")
    else:
        w("None. Every code in the registry is raised by at least one endpoint.\n\n")

    w("## Negative testing\n\n")
    w("**Every code above needs a negative test** in `docs/09 NegativeTesting/`, asserting both the\n"
      "HTTP status and the `code` (`FR-ADR-052`). `SEAT_UNAVAILABLE` is not merely an error path — "
      "it is\nthe observable evidence that the concurrency guard fired, and the stress script asserts "
      "its shape\nacross all forty-nine losers (`FR-ADR-034`).\n")
    return out.getvalue()


# ── checks ──────────────────────────────────────────────────────────────────────
LANES = [
    ("E1_browse", "E1", "Browse and discover"),
    ("E2_seat_hold", "E2", "Seat selection and the hold"),
    ("E3_checkout_payment", "E3", "Checkout, money and payment"),
    ("E4_receipt_entry", "E4", "The receipt, the reference and entry"),
    ("E5_account", "E5", "Accounts and the customer's own bookings"),
    ("E6_admin", "E6", "Admin: movies, showtimes, pricing, halls"),
    ("E7_dashboard", "E7", "The manager and admin dashboard"),
    ("E8_crosscutting", "E8", "Cross-cutting floors"),
]
FRONT = [("S1_reading_rules", "S1"), ("S2_scope", "S2"), ("S3_personas_surfaces", "S3")]


def _part(text: str, heading_prefix: str) -> str:
    """The body under `## <prefix> …` up to the next `## `."""
    m = re.search(r"^##\s+" + re.escape(heading_prefix) + r"\b.*?$", text, re.M)
    if not m:
        return ""
    nxt = re.search(r"^##\s", text[m.end():], re.M)
    body = text[m.end(): m.end() + nxt.start()] if nxt else text[m.end():]
    return body.strip("\n")


def _demote(body: str) -> str:
    """Push every heading in a lane body down one level, so lane `###` sit under `###` lane
    headings in the assembled document and the table of contents nests correctly."""
    return re.sub(r"^(#{3,5})(\s)", r"#\1\2", body, flags=re.M)


def _embed_errordoc(base: str | None = None) -> str:
    """The registry, rendered for `S6.0` of the assembled PRD.

    `S1.2.1` case 5 makes this registry the arbiter of a code's status, so a reader given only
    `FrontRow_PRD.md` has to be able to consult it. It is rendered from the same function that
    writes `api/error_codes.md`, never read back from that file, so the two cannot drift and
    `--assemble` does not depend on `error_codes.md` having been written first.

    Two transforms: the standalone file's title and its own GENERATED banner are dropped, because
    the assembled document carries its own and a second one here would name the wrong file; and
    every heading is pushed two levels down so `##` sits under this `## S6.0`.
    """
    body = render_errordoc(base)
    body = re.sub(r"\A#\s+.*?$", "", body, count=1, flags=re.M)          # drop its title
    body = re.sub(r"\A\s*(?:^>.*\n)+", "", body, flags=re.M)             # drop its banner
    body = re.sub(r"^(#{2,4})(\s)", r"#\1\2", body, flags=re.M)          # ## -> ###
    return body.strip("\n")


def assemble(base: str | None = None) -> str:
    d = os.path.join(base, "docs", "03 PRD", "sections") if base else SECTIONS
    out = io.StringIO()
    w = out.write

    w("# FrontRow — Product Requirements\n\n")
    w("> **GENERATED — assembled by `docs/03 PRD/api/generate_api.py --assemble` from the lane\n")
    w("> sections in `docs/03 PRD/sections/`.** Edit a section, then re-assemble. Editing this\n")
    w("> file directly puts it out of step with the sections the API contract is generated from.\n\n")
    w("**This is the document the code is written from.**\n\n")
    w("Eight lanes wrote the eight epics independently and blind, each reading the same frozen\n")
    w("sources, the same BRD rows and the same records, with no sight of another lane's draft. The\n")
    w("merge pass then hunted contradictions **between** them. `S8.5` reports what that found.\n\n")
    w("---\n\n")

    for stem, sid in FRONT:
        p = os.path.join(d, stem + ".md")
        if not os.path.isfile(p):
            raise Fail(f"missing front section {stem}.md")
        body = read(p).strip("\n")
        body = re.sub(r"\A#\s+.*?$", "", body, count=1, flags=re.M).strip("\n")
        w(f"# {sid} — " + {"S1": "Reading rules and the provenance grammar",
                           "S2": "Scope, carried from the frozen BRD",
                           "S3": "Personas, roles, and the surface inventory"}[sid] + "\n\n")
        w(body + "\n\n---\n\n")

    titles = {"S4": "Product specifications, by epic",
              "S5": "UX specification", "S6": "The API contract"}
    for sid in ("S4", "S5", "S6"):
        w(f"# {sid} — {titles[sid]}\n\n")
        if sid == "S6":
            w("Every endpoint below is a `endpoint` block, and **`api/contract.json` is generated\n")
            w("from exactly these blocks**. The two cannot drift: regenerating the contract and\n")
            w("diffing it is a gate (`S8.3`).\n\n")
            w("Conventions, the error envelope and the full code registry are **reproduced in\n")
            w("`S6.0` below**, generated from the same source as `docs/03 PRD/api/error_codes.md`.\n")
            w("They are carried here rather than referenced because `S1.2.1` case 5 makes the\n")
            w("registry the arbiter of a code's status, and a reader given only this file cannot\n")
            w("consult an arbiter that lives in another one.\n\n")
            w("## S6.0 — The error envelope and the code registry\n\n")
            w(_embed_errordoc(base) + "\n\n")
        for stem, lid, name in LANES:
            p = os.path.join(d, stem + ".md")
            if not os.path.isfile(p):
                raise Fail(f"missing lane section {stem}.md")
            body = _part(read(p), sid)
            if not body.strip():
                continue
            w(f"## {sid} / {lid} — {name}\n\n")
            w(_demote(body) + "\n\n")
        w("---\n\n")

    s7 = _part(read(os.path.join(d, "E8_crosscutting.md")), "S7")
    w("# S7 — Cross-cutting floors\n\n")
    w(_demote(s7) + "\n\n---\n\n")

    p8 = os.path.join(d, "S8_merge_report.md")
    if os.path.isfile(p8):
        body = read(p8).strip("\n")
        body = re.sub(r"\A#\s+.*?$", "", body, count=1, flags=re.M).strip("\n")
        w("# S8 — The merge report: what the checks say, and what the lanes disagreed about\n\n")
        w(body + "\n\n---\n\n")

    w("# S9 — What each lane refused to guess\n\n")
    w("Recorded verbatim from the lane returns, because it is the most valuable thing this\n")
    w("document produced. **Every entry below is a place a reasonable specification would have\n")
    w("invented an answer, and did not** (`CONSTITUTION.md` Art VII.3).\n\n")
    for stem, lid, name in LANES:
        body = _part(read(os.path.join(d, stem + ".md")), "Lane notes")
        if not body.strip():
            continue
        w(f"## S9 / {lid} — {name}\n\n{_demote(body)}\n\n")
    return out.getvalue()


def check_regen(base: str | None = None, quiet: bool = False) -> int:
    bad = 0
    for path, want in ((CONTRACT, render_contract(base)), (ERRORDOC, render_errordoc(base))):
        p = path if base is None else path.replace(ROOT, base)
        name = os.path.basename(p)
        if not os.path.isfile(p):
            print(f"FAIL  regenerate  {name} does not exist")
            bad += 1
            continue
        have = read(p)
        if have != want:
            print(f"FAIL  regenerate  {name} on disk differs from what the generator produces")
            hl, wl = have.split("\n"), want.split("\n")
            for i in range(max(len(hl), len(wl))):
                a = hl[i] if i < len(hl) else "<end of file>"
                b = wl[i] if i < len(wl) else "<end of file>"
                if a != b:
                    print(f"      first difference at line {i + 1}")
                    print(f"        on disk:   {a[:120]}")
                    print(f"        generated: {b[:120]}")
                    break
            bad += 1
        elif not quiet:
            print(f"PASS  regenerate  {name} is byte-identical to the generator's output "
                  f"({len(want.splitlines())} lines)")
    return bad


def brd_rows(base: str | None = None) -> list[str]:
    p = BRD_FILE if base is None else BRD_FILE.replace(ROOT, base)
    t = read(p)
    defs = re.findall(r"^\*\*`(R-[A-Z]{3,4}-\d{2})`", t, re.M)
    tbl = re.findall(r"^\|\s*`(R-[A-Z]{3,4}-\d{2})`\s*\|", t, re.M)
    return sorted(set(defs) | set(tbl))


def prd_specs(base: str | None = None) -> dict[str, dict]:
    """Every P-row in the section files, with the SRC and BRD tags it carries."""
    specs: dict[str, dict] = {}
    for path in section_files(base):
        text = read(path)
        heads = list(re.finditer(r"^#{3,4}\s*`(P-[A-Z]{3}-\d{2})`", text, re.M))
        for i, m in enumerate(heads):
            end = heads[i + 1].start() if i + 1 < len(heads) else len(text)
            nxt = re.search(r"^##\s", text[m.end():end], re.M)
            if nxt:
                end = m.end() + nxt.start()
            body = text[m.start():end]
            pid = m.group(1)
            if pid in specs:
                raise Fail(f"{os.path.basename(path)}: P-row `{pid}` is defined twice "
                           f"(also in {specs[pid]['file']})")
            src = re.findall(r"\[SRC:([^\]]*)\]", body)
            brd = re.findall(r"\[BRD:([^\]]*)\]", body)
            specs[pid] = {
                "file": os.path.basename(path),
                "src": " ".join(src).strip(),
                "brd": sorted(set(re.findall(r"R-[A-Z]{3,4}-\d{2}", " ".join(brd)))),
            }
    return specs


def check_coverage(base: str | None = None, verbose: bool = True) -> int:
    rows = brd_rows(base)
    specs = prd_specs(base)
    if not specs:
        print("FAIL  coverage    no P-row was found in docs/03 PRD/sections/")
        return 1

    covered: dict[str, list[str]] = {r: [] for r in rows}
    creep: dict[str, list[str]] = {}
    untagged, unsourced = [], []
    for pid, rec in sorted(specs.items()):
        if not rec["brd"]:
            untagged.append(pid)
        if not rec["src"].strip():
            unsourced.append(pid)
        for r in rec["brd"]:
            if r in covered:
                covered[r].append(pid)
            else:
                creep.setdefault(r, []).append(pid)

    # Every `P-xxx-nn` mentioned anywhere must resolve to a P-row that is actually defined.
    # This exists because S3's capability matrix was written before the lanes ran, and several of
    # its references resolved to a real id that specified something else entirely — a wrongness a
    # spell-check of ids cannot see, and the reason the check compares against DEFINED rows.
    dangling: dict[str, list[str]] = {}
    for path in section_files(base):
        name = os.path.basename(path)
        for pid in sorted(set(re.findall(r"\bP-[A-Z]{3}-\d{2}\b", read(path)))):
            if pid not in specs:
                dangling.setdefault(pid, []).append(name)

    gaps = [r for r in rows if not covered[r]]
    bad = 0
    if verbose:
        print("Two-way coverage — machine-derived from docs/02 BRD/FrontRow_BRD.md and "
              "docs/03 PRD/sections/*.md")
        print(f"  BRD rows       {len(rows)}")
        print(f"  PRD P-rows     {len(specs)}")
        print()
        print("  | BRD row | Covered by |")
        print("  |---|---|")
        for r in rows:
            print(f"  | {r} | {' '.join(covered[r]) if covered[r] else '**GAP**'} |")
        print()
    print(f"{'FAIL' if gaps else 'PASS'}  no-gap      {len(gaps)} BRD row(s) with no P-row"
          + (": " + " ".join(gaps) if gaps else ""))
    print(f"{'FAIL' if creep else 'PASS'}  no-creep    {len(creep)} PRD reference(s) to a BRD row "
          f"that does not exist" + (": " + " ".join(sorted(creep)) if creep else ""))
    print(f"{'FAIL' if untagged else 'PASS'}  brd-tag     {len(untagged)} P-row(s) carry no [BRD:] "
          f"tag" + (": " + " ".join(untagged) if untagged else ""))
    print(f"{'FAIL' if unsourced else 'PASS'}  src-tag     {len(unsourced)} P-row(s) carry no "
          f"[SRC:] tag" + (": " + " ".join(unsourced) if unsourced else ""))
    print(f"{'FAIL' if dangling else 'PASS'}  p-resolve   {len(dangling)} referenced P-row id(s) "
          f"are defined nowhere"
          + ("".join(f"\n      {p} referenced by {' '.join(f)}"
                     for p, f in sorted(dangling.items())) if dangling else ""))
    bad += bool(gaps) + bool(creep) + bool(untagged) + bool(unsourced) + bool(dangling)
    return bad


def check_endpoints(base: str | None = None) -> int:
    """Every endpoint in the ASSEMBLED PRD's S6 is in contract.json, and the reverse."""
    p = PRD_FILE if base is None else PRD_FILE.replace(ROOT, base)
    c = CONTRACT if base is None else CONTRACT.replace(ROOT, base)
    if not os.path.isfile(p):
        print("FAIL  endpoints   docs/03 PRD/FrontRow_PRD.md does not exist")
        return 1
    if not os.path.isfile(c):
        print("FAIL  endpoints   contract.json does not exist")
        return 1
    in_prd = set()
    for body, line in fenced(read(p), "endpoint"):
        in_prd.add(json.loads(body)["id"])
    in_contract = {e["id"] for e in json.loads(read(c))["endpoints"]}
    missing = sorted(in_prd - in_contract)
    extra = sorted(in_contract - in_prd)
    print(f"{'FAIL' if missing else 'PASS'}  prd->contract {len(missing)} endpoint(s) in the PRD's "
          f"S6 and not in contract.json" + (": " + " ".join(missing) if missing else ""))
    print(f"{'FAIL' if extra else 'PASS'}  contract->prd {len(extra)} endpoint(s) in contract.json "
          f"and not in the PRD's S6" + (": " + " ".join(extra) if extra else ""))
    print(f"      {len(in_contract)} endpoints in contract.json · {len(in_prd)} in the assembled PRD")
    return bool(missing) + bool(extra)


def check_statemachine(base: str | None = None, verbose: bool = True) -> int:
    got = blocks_of("transition", section_files(base))
    if len(got) != 1:
        print(f"FAIL  statemachine expected exactly one ```transition block, found {len(got)}")
        return 1
    sm, src, line = got[0]
    states = list(sm["states"])
    inputs = list(sm["inputs"])
    initial = sm["initial"]
    trans = sm["transitions"]
    bad = 0

    if initial not in states:
        print(f"FAIL  statemachine initial state `{initial}` is not in `states`")
        bad += 1

    # 1. every (state, input) pair handled exactly once
    seen: dict[tuple[str, str], int] = {}
    unknown = []
    for t in trans:
        key = (t["from"], t["input"])
        if t["from"] not in states or t["input"] not in inputs or t["to"] not in states:
            unknown.append(f"{t['from']} --{t['input']}--> {t['to']}")
            continue
        seen[key] = seen.get(key, 0) + 1
    missing = [f"{s} --{i}-->" for s, i in product(states, inputs) if (s, i) not in seen]
    dupes = [f"{s} --{i}-->" for (s, i), n in sorted(seen.items()) if n > 1]

    print(f"{'FAIL' if unknown else 'PASS'}  sm-vocabulary {len(unknown)} transition(s) name a "
          f"state or input not declared" + ("\n      " + "\n      ".join(unknown) if unknown else ""))
    print(f"{'FAIL' if missing else 'PASS'}  sm-total      {len(missing)} of "
          f"{len(states) * len(inputs)} (state, input) pair(s) have no handling"
          + ("\n      " + "\n      ".join(missing) if missing else ""))
    print(f"{'FAIL' if dupes else 'PASS'}  sm-once       {len(dupes)} pair(s) handled more than once"
          + ("\n      " + "\n      ".join(dupes) if dupes else ""))
    bad += bool(unknown) + bool(missing) + bool(dupes)

    # 2. every state reachable from initial, following only state-CHANGING transitions
    reach = {initial}
    changed = True
    while changed:
        changed = False
        for t in trans:
            if t["from"] in reach and t["to"] not in reach:
                reach.add(t["to"])
                changed = True
    unreachable = sorted(set(states) - reach)
    print(f"{'FAIL' if unreachable else 'PASS'}  sm-reachable  {len(unreachable)} state(s) "
          f"unreachable from `{initial}`" + (": " + " ".join(unreachable) if unreachable else ""))
    bad += bool(unreachable)

    # 3. every transition says what the user sees
    silent = [f"{t['from']} --{t['input']}--> {t['to']}"
              for t in trans if not str(t.get("user_sees", "")).strip()]
    print(f"{'FAIL' if silent else 'PASS'}  sm-told       {len(silent)} transition(s) do not say "
          f"what the customer is told" + ("\n      " + "\n      ".join(silent) if silent else ""))
    bad += bool(silent)

    # 6. the prose table and the machine-readable block must name the same inputs.
    #
    # The state machine exists twice: once as a `transition` block a machine reads, and once as a
    # markdown table a person reads. They sit in the same section and are edited separately, and
    # NOTHING ELSE IN THIS TOOLCHAIN COMPARES THEM — every check above reads only the block, so an
    # input added to one and not the other passes all five. This check was added after a lane added
    # a 29th input and pointed out that its own cross-check was the only thing that would have
    # caught a mismatch.
    # The grid is the one table whose rows are `| `INPUT` | c | c | ... |` with exactly as many
    # value columns as there are states. Anchoring on the column count is what keeps this from
    # matching the error-code and audit-action tables, whose first cell is also UPPER_SNAKE.
    prose_inputs: set[str] = set()
    row_re = re.compile(r"^\|\s*`([A-Z][A-Z0-9_]{3,})`\s*\|(.+)\|\s*$", re.M)
    for path in section_files(base):
        for m in row_re.finditer(read(path)):
            if len([c for c in m.group(2).split("|")]) == len(states):
                prose_inputs.add(m.group(1))
    declared = set(inputs)
    if prose_inputs:
        only_prose = sorted(prose_inputs - declared)
        only_block = sorted(declared - prose_inputs)
        ok = not only_prose and not only_block
        print(f"{'PASS' if ok else 'FAIL'}  sm-mirror     "
              f"{len(only_prose) + len(only_block)} input(s) named in one representation and not "
              f"the other ({len(prose_inputs)} in the prose table, {len(declared)} in the block)"
              + ("".join("\n      only in the prose table: " + i for i in only_prose))
              + ("".join("\n      only in the `transition` block: " + i for i in only_block)))
        bad += 0 if ok else 1
    else:
        print("SKIP  sm-mirror     no prose transition table found to compare against")

    if verbose:
        print()
        print(f"Transition table — {len(states)} states x {len(inputs)} inputs = "
              f"{len(states) * len(inputs)} pairs, all handled ({src}:{line})")
        print()
        print("| From | Input | To | Guard | What the customer is told |")
        print("|---|---|---|---|---|")
        for t in trans:
            print(f"| `{t['from']}` | `{t['input']}` | `{t['to']}` | {t.get('guard', '')} | "
                  f"{t.get('user_sees', '')} |")
    return bad


# The clauses SRC-003's sixteen errata withdrew or corrected. `FR-ADR-006` says plainly that
# the repository's consistency checker "verifies that citations resolve to a clause that exists;
# it cannot tell that a clause has been withdrawn. That check is a human reading." This is that
# check, made mechanical. A withdrawn clause may still be MENTIONED — the errata tables and
# B7.3 do exactly that — so a citation is a defect only when its line does not mark it as dead.
WITHDRAWN = {
    "SRC-001 §2.3": "E-6 — listings without staff typing them in",
    "SRC-001 §3.4": "E-7 — listings update automatically",
    "SRC-001 §4.3": "E-1 — the cinema-staff user",
    "SRC-001 §5.1.2": "E-5 — upcoming releases shown separately",
    "SRC-001 §5.4.3": "E-2 — a customer cancels a booking",
    "SRC-001 §5.5.3": "E-3 — staff validate tickets at the door",
    "SRC-001 §5.5.4": "E-8 — the administrator approves imported films",
    "SRC-001 §5.6": "E-4 — movie data from a public database (the whole clause)",
    "SRC-001 §5.6.1": "E-4",
    "SRC-001 §5.6.2": "E-4",
    "SRC-001 §5.6.3": "E-4 (substance survives via §9.4)",
    "SRC-001 §5.6.4": "E-4",
    "SRC-001 §9.5": "E-10 — payment handled by a third party",
    "SRC-002 §4.6": "E-4 — a scheduler process or an EventBridge Lambda",
    "SRC-002 §10": "E-2 — the whole TMDB section",
}
CORRECTED = {
    "SRC-001 §5.3.3": "E-9 — a booking reference on an emailed receipt, not a scannable ticket",
    "SRC-002 §8.1.1": "E-1 — the hold is 3 minutes, not 7",
    "SRC-002 §8.5.1": "E-5 — the worker sends the receipt, and generates no QR code",
    "SRC-002 §12.7": "E-3 — Phase 6 is admin movie management",
}
# A line that already marks the clause dead is a correct mention, not a citation.
DEAD_MARKERS = re.compile(
    r"withdraw|supersed|errat|\bE-\d+\b|corrected|dead text|no longer|not live|"
    r"§E\b|removed|is gone|defect|stale", re.I)


def check_withdrawn(base: str | None = None) -> int:
    """No withdrawn or corrected clause is cited as if it were live authority."""
    files = section_files(base)
    p = PRD_FILE if base is None else PRD_FILE.replace(ROOT, base)
    if os.path.isfile(p):
        files = files + [p]
    if not files:
        print("FAIL  withdrawn    no PRD section file to check")
        return 1

    bad_w, bad_c, mentions = [], [], 0
    # Longest first, so `SRC-002 §10.6.3` is matched before `SRC-002 §10`.
    keys = sorted(set(WITHDRAWN) | set(CORRECTED), key=len, reverse=True)
    for path in files:
        name = os.path.basename(path)
        lines = read(path).split("\n")
        for lineno, line in enumerate(lines, 1):
            for k in keys:
                sid, clause = k.split(" §")
                # word-boundary on the clause so §10 does not match §10.6.3
                if not re.search(re.escape(sid) + r"\s*§" + re.escape(clause) + r"(?![0-9.])", line):
                    continue
                mentions += 1
                # A `[SRC:]` tag is not prose — it ASSERTS authority. Naming a withdrawn or
                # corrected clause there is a defect however carefully the surrounding paragraph
                # explains itself, so the tag must carry its own erratum reference or nothing
                # rescues it. This is the case that caught P-SEA-06.
                if "[SRC:" in line:
                    if re.search(r"§E\b|\bE-\d+\b", line):
                        break
                else:
                    # Prose wraps, and a markdown table marks a whole block dead in its header,
                    # so the window is the matched line plus three either side: wide enough for a
                    # wrapped sentence, far too narrow to rescue a genuinely live citation.
                    lo, hi = max(0, lineno - 4), min(len(lines), lineno + 3)
                    if DEAD_MARKERS.search("\n".join(lines[lo:hi])):
                        break
                entry = f"{name}:{lineno}: cites `{k}` as live authority — {WITHDRAWN.get(k) or CORRECTED.get(k)}"
                (bad_w if k in WITHDRAWN else bad_c).append(entry)
                break

    print(f"{'FAIL' if bad_w else 'PASS'}  withdrawn     {len(bad_w)} citation(s) of a WITHDRAWN "
          f"clause with nothing on the line marking it dead"
          + ("\n      " + "\n      ".join(bad_w) if bad_w else ""))
    print(f"{'FAIL' if bad_c else 'PASS'}  corrected     {len(bad_c)} citation(s) of a CORRECTED "
          f"clause with nothing on the line marking it corrected"
          + ("\n      " + "\n      ".join(bad_c) if bad_c else ""))
    print(f"      {mentions} mention(s) of the {len(WITHDRAWN)} withdrawn and "
          f"{len(CORRECTED)} corrected clauses, across {len(files)} file(s)")
    return bool(bad_w) + bool(bad_c)


def check_inventory(base: str | None = None) -> int:
    """S3.8's route inventory names exactly the endpoints the contract carries.

    S3.8 declares itself generated and unable to drift. It drifted anyway — it was written when
    there were 53 endpoints and was not regenerated when three more were added, while still
    printing the sentence that said it could not have happened. A section that claims to be
    generated and is not is worse than one that admits it was typed.
    """
    d = os.path.join(base, "docs", "03 PRD", "sections") if base else SECTIONS
    p = os.path.join(d, "S3_personas_surfaces.md")
    if not os.path.isfile(p):
        print("FAIL  inventory   S3_personas_surfaces.md does not exist")
        return 1
    text = read(p)
    start = text.find("## S3.8")
    body = text[start:text.find("## S3.9", start)] if start >= 0 else ""
    listed = set(re.findall(r"`(EP-[A-Z]{3}-\d{2})`", body))
    real = {e["id"] for e in build_contract(base)["endpoints"]}
    missing, extra = sorted(real - listed), sorted(listed - real)
    print(f"{'FAIL' if missing else 'PASS'}  inv-complete  {len(missing)} endpoint(s) in the contract "
          f"and not in the S3.8 route inventory" + (": " + " ".join(missing) if missing else ""))
    print(f"{'FAIL' if extra else 'PASS'}  inv-real      {len(extra)} endpoint(s) in the S3.8 inventory "
          f"that no longer exist" + (": " + " ".join(extra) if extra else ""))
    print(f"      {len(listed)} listed · {len(real)} in the contract")
    return bool(missing) + bool(extra)


def check_adrs(base: str | None = None) -> int:
    """Derived, never asserted: which FR-ADR ids the PRD actually cites."""
    cited: dict[str, set[str]] = {}
    files = section_files(base)
    p = PRD_FILE if base is None else PRD_FILE.replace(ROOT, base)
    if os.path.isfile(p):
        files = files + [p]
    for path in files:
        for n in set(re.findall(r"\bFR-ADR-(\d{3})\b", read(path))):
            cited.setdefault("FR-ADR-" + n, set()).add(os.path.basename(path))
    adr_dir = os.path.join(base or ROOT, "docs", "01 ADR", "all-ADRs")
    known = {f[:-3] for f in os.listdir(adr_dir) if f.endswith(".md")} if os.path.isdir(adr_dir) else set()
    dangling = sorted(set(cited) - known)
    print(f"{'FAIL' if dangling else 'PASS'}  adr-resolve   {len(dangling)} cited FR-ADR id(s) "
          f"have no record file" + (": " + " ".join(dangling) if dangling else ""))
    print(f"      {len(cited)} of {len(known)} records are cited by the PRD")
    for aid in sorted(cited):
        print(f"      {aid}  {' '.join(sorted(cited[aid]))}")
    return bool(dangling)


# ── selftest ────────────────────────────────────────────────────────────────────
def _copy(root: str, dest: str) -> None:
    shutil.copytree(root, dest, ignore=shutil.ignore_patterns(
        ".git", "node_modules", "__pycache__", ".venv", "venv"))


def _first_section(base: str) -> str:
    fs = section_files(base)
    if not fs:
        raise Fail("no section file to plant into")
    return fs[0]


def _plant_regen(base: str) -> bool:
    p = CONTRACT.replace(ROOT, base)
    if not os.path.isfile(p):
        return False
    write(p, read(p).replace('"endpoint_count"', '"endpoint_kount"', 1))
    return True


def _plant_coverage(base: str) -> bool:
    """Delete one P-row's [BRD:] tag — its BRD row loses its only cover, or the tag goes missing."""
    for f in section_files(base):
        t = read(f)
        m = re.search(r"`\[BRD:[^\]]*\]`", t)
        if m:
            write(f, t[:m.start()] + "`[BRD-REMOVED]`" + t[m.end():])
            return True
    return False


def _plant_endpoints(base: str) -> bool:
    p = PRD_FILE.replace(ROOT, base)
    if not os.path.isfile(p):
        return False
    t = read(p)
    m = re.search(r"^```endpoint\s*$(.*?)^```\s*$", t, re.M | re.S)
    if not m:
        return False
    write(p, t[:m.start()] + t[m.end():])
    return True


def _plant_statemachine(base: str) -> bool:
    for f in section_files(base):
        t = read(f)
        m = re.search(r"^```transition\s*$(.*?)^```\s*$", t, re.M | re.S)
        if not m:
            continue
        sm = json.loads(m.group(1))
        if not sm["transitions"]:
            return False
        sm["transitions"] = sm["transitions"][1:]          # remove one handled pair
        body = json.dumps(sm, indent=2, ensure_ascii=False)
        write(f, t[:m.start()] + "```transition\n" + body + "\n```\n" + t[m.end():])
        return True
    return False


def _plant_adrs(base: str) -> bool:
    f = _first_section(base)
    write(f, read(f) + "\n\nPlanted: this rests on `FR-ADR-994`, which has no record.\n")
    return True


def _plant_inventory(base: str) -> bool:
    p = os.path.join(base, "docs", "03 PRD", "sections", "S3_personas_surfaces.md")
    if not os.path.isfile(p):
        return False
    t = read(p)
    m = re.search(r"\| `(EP-[A-Z]{3}-\d{2})` \|", t)
    if not m:
        return False
    write(p, t[:m.start(1)] + "EP-ZZZ-99" + t[m.end(1):])
    return True


def _plant_withdrawn(base: str) -> bool:
    f = _first_section(base)
    write(f, read(f) + "\n\nMovie data is imported automatically per `SRC-001 §5.6.1`.\n")
    return True


PLANTS = [
    ("regenerate", "contract.json on disk edited away from the generator's output",
     _plant_regen, lambda b: check_regen(b, quiet=True)),
    ("coverage", "one P-row's [BRD:] tag removed",
     _plant_coverage, lambda b: check_coverage(b, verbose=False)),
    ("endpoints", "one endpoint block deleted from the assembled PRD",
     _plant_endpoints, check_endpoints),
    ("statemachine", "one (state, input) pair removed from the transition table",
     _plant_statemachine, lambda b: check_statemachine(b, verbose=False)),
    ("adrs", "a citation of FR-ADR-994, which has no record file",
     _plant_adrs, check_adrs),
    ("withdrawn", "a citation of SRC-001 §5.6.1, withdrawn in full by erratum E-4",
     _plant_withdrawn, check_withdrawn),
    ("inventory", "an endpoint id removed from the S3.8 route inventory",
     _plant_inventory, check_inventory),
]


def selftest() -> int:
    """Red-proof by DELTA, so it still works on a repository that is already red."""
    import contextlib
    def quiet(fn, *a):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            try:
                return fn(*a)
            except Fail:
                return 99
    base_counts = {}
    for name, _, _, run in PLANTS:
        base_counts[name] = quiet(run, None)
    print(f"baseline: " + " · ".join(f"{k}={v}" for k, v in base_counts.items())
          + "   red-proofing by delta")
    print()
    passed = 0
    for name, what, plant, run in PLANTS:
        with tempfile.TemporaryDirectory() as tmp:
            work = os.path.join(tmp, "repo")
            _copy(ROOT, work)
            if not plant(work):
                print(f"  FAIL  {name:<13} the plant was a no-op — it proved nothing")
                continue
            after = quiet(run, work)
            before = base_counts[name]
            if after > before:
                passed += 1
                print(f"  ok    {name:<13} {before} -> {after} failure(s)   planted: {what}")
            else:
                print(f"  FAIL  {name:<13} {before} -> {after} failure(s)   DID NOT FIRE. "
                      f"A check that cannot fail is decoration. Planted: {what}")
    print()
    print(f"{passed}/{len(PLANTS)} checks red-proofed")
    return 0 if passed == len(PLANTS) else 1


# ── main ────────────────────────────────────────────────────────────────────────
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    for flag in ("check", "coverage", "endpoints", "inventory", "statemachine", "adrs",
                 "withdrawn", "assemble", "all", "selftest"):
        ap.add_argument("--" + flag, action="store_true")
    args = ap.parse_args()
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:                                                 # noqa: BLE001
        pass

    if args.selftest:
        return selftest()

    if args.assemble:
        text = assemble()
        write(PRD_FILE, text)
        print(f"wrote FrontRow_PRD.md   {len(text.splitlines())} lines, "
              f"{len(text):,} characters")
        return 0

    bad = 0
    ran = False
    if args.all or args.check:
        ran = True
        bad += check_regen()
    if args.all or args.coverage:
        ran = True
        if args.all:
            print()
        bad += check_coverage(verbose=not args.all)
    if args.all or args.endpoints:
        ran = True
        if args.all:
            print()
        bad += check_endpoints()
    if args.all or args.inventory:
        ran = True
        if args.all:
            print()
        bad += check_inventory()
    if args.all or args.statemachine:
        ran = True
        if args.all:
            print()
        bad += check_statemachine(verbose=not args.all)
    if args.all or args.withdrawn:
        ran = True
        if args.all:
            print()
        bad += check_withdrawn()
    if args.all or args.adrs:
        ran = True
        if args.all:
            print()
        bad += check_adrs()

    if not ran:
        write(CONTRACT, render_contract())
        write(ERRORDOC, render_errordoc())
        n = build_contract()["endpoint_count"]
        print(f"wrote contract.json   {n} endpoints, {len(VALID_CODES)} error codes")
        print(f"wrote error_codes.md")
        return 0

    print()
    print(f"VERDICT: {'FAIL' if bad else 'PASS'} — {bad} check(s) failed")
    return 1 if bad else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Fail as exc:
        print(f"VERDICT: FAIL — {exc}", file=sys.stderr)
        sys.exit(1)
    except Exception:                                                 # noqa: BLE001
        traceback.print_exc()
        print("\nVERDICT: ERROR — the tool itself failed. Exit 2.", file=sys.stderr)
        sys.exit(2)

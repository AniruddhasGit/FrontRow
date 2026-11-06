#!/usr/bin/env python
"""Check datamodel.json against the documents it was derived from.

    py consistency_check.py             run every rule
    py consistency_check.py --selftest  plant one defect per rule and prove
                                        each rule goes red, then restore

generate.py --check proves the GENERATED files match the model.  This proves
the MODEL matches the project: that nothing is uncited, that money is never a
float, that no reserved question has been quietly answered by a constraint,
and - the rule that pays for this file - that every dotted `table.name` the
Bible's 200 acceptance criteria contain resolves to something this model
declares, whether a column or an audit action.

That rule exists because the acceptance criteria were written BEFORE this
schema and contain literal SQL against it.  A rename here does not fail
loudly; it fails 200 tests nobody will run until Phase 1, by which time the
rename looks like a decision somebody made on purpose.

Every rule is red-proofed by --selftest.  A check nobody has watched fail is
decoration.
"""
import argparse
import csv
import io
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
MODEL = os.path.join(HERE, "datamodel.json")
BIBLE = os.path.join(ROOT, "docs", "05 Bible", "FrontRow_Bible.csv")
PRD_SECTIONS = os.path.join(ROOT, "docs", "03 PRD", "sections")
LEDGER = os.path.join(ROOT, "docs", "01 ADR", "ADR_DECISION_RELEASE_LEDGER.tsv")
NL = chr(10)

# Reserved rows the client has RULED, and the one constraint each ruling files.
# name -> (table, exact expression, ruling that must be cited).  SRC-004 R-4 and
# R-5, received 2026-10-18.  OPEN-SEATALPHA-01 ("I allowed") and
# OPEN-RESETTOKEN-01 ("never in the database") are ruled as ABSENCES, so they
# add no entry here and keep their prohibitions in r_reserved_not_decided.
RULED_CHECKS = {
    "ck_seat__row_label_upper": ("seat", "row_label = upper(btrim(row_label))", "SRC-004 R-4"),
    "ck_booking__reference_charset": (
        "booking", "reference ~ '^[23456789ACDEFHJKMNPQRTVWXY]{8}$'", "SRC-004 R-5"),
}

# The fifteen relations the Bible's SQL already names.  This list is INHERITED,
# not chosen: 200 acceptance criteria query these names.  A rename is a
# deliberate act that updates the Bible in the same commit, never a quiet
# improvement - so the rule below fails on a set mismatch in either direction.
INHERITED_TABLES = set("""
users cinema screen seat movie showtime showtime_seat booking booking_seat
payment idempotency_record password_reset_token outbox_message
receipt_dispatch audit_log
""".split())

MONEY_HINTS = ("price", "amount", "total", "paise", "uplift", "fee", "subtotal")
MONEY_OK = ("integer", "bigint")

# Payment is simulated forever and no provider is ever integrated, so this rule
# is trivially satisfiable.  It exists to keep it satisfied - so that nobody
# adds a card-shaped column out of habit later.
CARD_SHAPED = re.compile(
    r"(card_number|cardnumber|\bpan\b|cvv|cvc|expiry_month|expiry_year|"
    r"card_holder|cardholder)", re.I)

# Nothing in this product runs on a schedule and there is no external movie
# API.  A column shaped for either is rot inherited from a deleted design.
DELETED_SCOPE = re.compile(
    r"(next_run_at|cron_expression|schedule_at|tmdb|last_synced_at|sync_status)", re.I)

RESULTS = []


def rule(fn):
    RESULTS.append(fn)
    return fn


def load(path=MODEL):
    with io.open(path, encoding="utf-8") as fh:
        return json.load(fh)


def columns_of(model):
    out = {}
    for t in model["tables"]:
        out[t["name"]] = set(c["name"] for c in t["columns"])
    return out


# ------------------------------------------------------------------ rules

@rule
def r_table_set(model):
    """Every table the Bible queries exists.  Any extra one is declared.

    This began as an equality check against fifteen table names harvested from
    the Bible's dotted references, and that was wrong in a way worth recording:
    the harvest can only see tables whose columns are written `table.column`.
    `seat_category` and `manager_screen_assignment` are required by an APPROVED
    ADR and a NOT NULL foreign key, and neither appeared - so an equality check
    would have demanded the schema drop two tables it cannot exist without.

    A missing table is therefore a failure; an extra table is a failure only if
    the model does not say why it is there.
    """
    have = set(t["name"] for t in model["tables"])
    declared_extra = set(model.get("tables_beyond_bible", {}).keys())
    missing = sorted(INHERITED_TABLES - have)
    undeclared = sorted(have - INHERITED_TABLES - declared_extra)
    msgs = []
    if missing:
        msgs.append("the Bible queries these and the model lacks them: "
                    + ", ".join(missing))
    if undeclared:
        msgs.append("undeclared extra table(s): " + ", ".join(undeclared)
                    + " - add each to tables_beyond_bible with the document requiring it")
    return ("table-set", not msgs,
            "; ".join(msgs) or
            "%d tables: the %d the Bible queries plus %d declared"
            % (len(have), len(INHERITED_TABLES), len(declared_extra)))


@rule
def r_fk_restrict(model):
    """Every foreign key is ON DELETE RESTRICT.

    S-XCT-09 asserts `pg_constraint WHERE contype='f' AND confdeltype <> 'r'`
    returns zero rows, so this is not a preference - it is a test that will be
    run.  A cascade anywhere in this schema would delete a paid booking as a
    side effect of tidying up a parent row.
    """
    bad = []
    for t in model["tables"]:
        for fk in t.get("foreign_keys", []):
            if fk.get("on_delete", "RESTRICT").upper() != "RESTRICT":
                bad.append("%s.%s is ON DELETE %s"
                           % (t["name"], fk.get("name", "?"), fk["on_delete"]))
    return ("fk-restrict", not bad,
            "; ".join(bad) or "every foreign key is ON DELETE RESTRICT")


@rule
def r_no_database_clock(model):
    """No column takes its value from the database's clock.

    FR-ADR-018 draws the line precisely, and it is not "no defaults":

        "created_at and updated_at are timestamptz and default to now() at the
         database... The injected clock governs domain decisions; the database
         clock governs row metadata."

    So row metadata MUST carry the default and a decision-bearing instant MUST
    NOT.  An earlier form of this rule banned every clock default outright and
    would have gone red against a correct schema - the third time in this goal
    that a plausible-sounding rule turned out to fail correct work.

    Why the second half matters: showtime.starts_at, password_reset_token
    .expires_at and payment's instants all decide something.  A database
    default on any of them is unreachable by an injected clock, so a test that
    moves time cannot move that value, and the test passes or fails for reasons
    unrelated to the code.  A DEFAULT on created_at is harmless because it is a
    fallback - the application may still pass a value, and does where a test
    needs determinism.
    """
    METADATA = ("created_at", "updated_at")
    missing, forbidden = [], []
    for t in model["tables"]:
        for c in t["columns"]:
            d = (c.get("default") or "").lower()
            clocked = ("now()" in d or "current_timestamp" in d
                       or "localtimestamp" in d)
            if c["name"] in METADATA:
                if not clocked:
                    missing.append("%s.%s" % (t["name"], c["name"]))
            elif clocked:
                forbidden.append("%s.%s DEFAULT %s"
                                 % (t["name"], c["name"], c["default"]))
    msgs = []
    if forbidden:
        msgs.append("decision-bearing instant(s) defaulting to the database clock: "
                    + "; ".join(forbidden))
    if missing:
        msgs.append("row metadata without the required default: " + ", ".join(missing))
    return ("clock-defaults", not msgs,
            "; ".join(msgs) or
            "row metadata defaults to now(); no decision-bearing instant does")


@rule
def r_uncited(model):
    """Every column, constraint and index cites a document."""
    bad = []
    for t in model["tables"]:
        if not t.get("cite"):
            bad.append(t["name"] + " (table)")
        for c in t["columns"]:
            if not c.get("cite"):
                bad.append("%s.%s" % (t["name"], c["name"]))
        for kind in ("unique", "checks", "foreign_keys", "indexes"):
            for o in t.get(kind, []):
                if not o.get("cite"):
                    bad.append("%s.%s (%s)" % (t["name"], o.get("name", "?"), kind))
    return ("uncited", not bad,
            ("%d uncited: %s" % (len(bad), ", ".join(bad[:6]))) if bad
            else "zero uncited objects")


@rule
def r_money(model):
    """Money is an integer in the minor unit.  Never a float, never NUMERIC."""
    bad = []
    for t in model["tables"]:
        for c in t["columns"]:
            looks_like_money = any(h in c["name"].lower() for h in MONEY_HINTS)
            if looks_like_money and c["type"] not in MONEY_OK:
                bad.append("%s.%s is %s" % (t["name"], c["name"], c["type"]))
    return ("money-integer", not bad,
            "; ".join(bad) or "every money-shaped column is an integer type")


@rule
def r_no_card_data(model):
    """No card data anywhere - not a column, not a comment."""
    bad = []
    for t in model["tables"]:
        for c in t["columns"]:
            blob = c["name"] + " " + (c.get("note") or "")
            if CARD_SHAPED.search(blob):
                bad.append("%s.%s" % (t["name"], c["name"]))
    return ("no-card-data", not bad,
            "; ".join(bad) or "no card-shaped column or comment")


@rule
def r_deleted_scope(model):
    """No column survives from the deleted scheduler or the deleted movie API."""
    bad = []
    for t in model["tables"]:
        for c in t["columns"]:
            if DELETED_SCOPE.search(c["name"]):
                bad.append("%s.%s" % (t["name"], c["name"]))
    return ("deleted-scope", not bad,
            "; ".join(bad) or "no scheduler or external-API residue")


@rule
def r_timestamps(model):
    """A column named _at is an instant, never a naive local timestamp."""
    bad = []
    for t in model["tables"]:
        for c in t["columns"]:
            if c["name"].endswith("_at") and c["type"] != "timestamptz":
                bad.append("%s.%s is %s" % (t["name"], c["name"], c["type"]))
    return ("timestamptz", not bad,
            "; ".join(bad) or "every _at column is timestamptz")


@rule
def r_seat_guarantee(model):
    """The never-waivable constraint exists, on exactly one relation.

    SRC-001 s2.2 and s7.1.  Redis provides the hold; this provides the truth.
    The rule also fails if TWO relations carry it, because the guarantee living
    in two places is how they drift apart and stop agreeing.
    """
    pair = set(["showtime_id", "seat_id"])
    guard = model.get("seat_guarantee") or {}
    want_table, want_name = guard.get("table"), guard.get("constraint")
    if not want_table:
        return ("seat-guarantee", False,
                "the model names no seat_guarantee - the one constraint this "
                "product may not ship without must be declared, not inferred")

    # An earlier form of this rule failed whenever TWO relations carried the
    # pair.  That is wrong here, and the PRD says so in terms: showtime_seat
    # carries the same two columns for a different job, and P-ADM-14 warns
    # "that unique index is not the oversell guard, and nothing may treat it as
    # one - two tables, two constraints, two different jobs".  So the rule
    # checks WHICH relation guards, not how many carry the columns.
    found, others = None, []
    for t in model["tables"]:
        for u in list(t.get("unique", [])) + list(t.get("indexes", [])):
            if set(c.lower() for c in u.get("columns", [])) != pair:
                continue
            if t["name"] == want_table and u.get("name") == want_name:
                found = u
            else:
                others.append("%s.%s" % (t["name"], u.get("name", "?")))

    if found is None:
        return ("seat-guarantee", False,
                "%s.%s does not exist - the oversell guard is missing"
                % (want_table, want_name))
    if found.get("where"):
        return ("seat-guarantee", False,
                "%s.%s is PARTIAL (WHERE %s).  A partial guard frees the pair for "
                "any row the predicate excludes, which is an oversell by design."
                % (want_table, want_name, found["where"]))
    declared = set(model.get("non_guard_seat_pairs", []))
    undeclared = sorted(set(others) - declared)
    if undeclared:
        return ("seat-guarantee", False,
                "%s also carries (showtime_id, seat_id) and is not declared in "
                "non_guard_seat_pairs - say which job it does, so nobody later "
                "mistakes it for the guard" % ", ".join(undeclared))
    return ("seat-guarantee", True,
            "guarded by %s.%s, total (no WHERE)%s"
            % (want_table, want_name,
               ("; %d declared non-guard pair(s)" % len(declared)) if declared else ""))


@rule
def r_reset_token_three_columns(model):
    """password_reset_token keeps claim, sent and used as three columns.

    Collapsing any pair is a defect with a name: reusing email_sent_at as the
    worker's claim sends a SECOND reset link after a redelivery, because it is
    never cleared and a stale check would reclaim a row whose email already
    went out.
    """
    want = set(["email_claimed_at", "email_sent_at", "used_at"])
    cols = columns_of(model).get("password_reset_token", set())
    missing = sorted(want - cols)
    return ("reset-token-three", not missing,
            ("collapsed or missing: " + ", ".join(missing)) if missing
            else "claim, sent and used are three distinct columns")


@rule
def r_reserved_not_decided(model):
    """No reserved question has been answered by a constraint.

    Each of these would look like tidying up and would in fact decide something
    the build session may not decide.
    """
    bad = []
    by_name = dict((t["name"], t) for t in model["tables"])

    # A reserved row the client has RULED may be expressed as a constraint - but
    # only as the exact constraint its ruling files, citing that ruling, on the
    # ruled table.  Any OTHER constraint on the same subject still decides
    # something nobody ruled, and still fails.  Unruled rows are unchanged below.
    for t in model["tables"]:
        for ck in t.get("checks", []):
            expr = ck["expression"].lower()
            subject = None
            # Any CHECK on booking.reference, regex or not (a char_length() bound
            # decides the length as surely as a regex does), and a regex on a
            # reference anywhere else.
            if "reference" in expr and (t["name"] == "booking" or "~" in expr
                                        or "similar to" in expr):
                subject = "booking-reference alphabet (OPEN-REFCHAR-01)"
            elif "row_label" in expr:
                subject = "row_label (OPEN-SEATLABEL-01 / OPEN-SEATALPHA-01)"
            if subject is None:
                continue
            ruled = RULED_CHECKS.get(ck.get("name"))
            if not (ruled and ruled[0] == t["name"] and ruled[1] == ck["expression"]
                    and ruled[2] in (ck.get("cite") or "")):
                bad.append("%s: a CHECK constrains the %s that is not the exact ruled "
                           "constraint" % (ck.get("name", t["name"]), subject))
    for name, (table, expr, ruling) in sorted(RULED_CHECKS.items()):
        have = [ck for ck in by_name.get(table, {}).get("checks", []) if ck.get("name") == name]
        if not have:
            bad.append("%s.%s is missing - %s rules it" % (table, name, ruling))

    # OPEN-HOLDRECOVER-01 - a live hold is Redis-only and has no row.
    for name in by_name:
        if "hold" in name:
            bad.append("%s: holds have no database row (OPEN-HOLDRECOVER-01), and a "
                       "table would put the seat guarantee in two places" % name)

    # OPEN-RESETTOKEN-01 - RULED by SRC-004 R-3: the plaintext rides in the queue
    # message only, and no database column ever holds it.  The ruling makes this
    # check permanent rather than retiring it.
    # On ANY table: the plaintext must not move to the outbox or anywhere else.
    # Only the digest (token_sha256) and a foreign key (*_id) are token-named.
    for t in model["tables"]:
        for c in t["columns"]:
            n = c["name"].lower()
            if ("token" in n or "plaintext" in n) and n != "token_sha256"                     and not n.endswith("_id"):
                bad.append("%s.%s is shaped to store a token itself "
                           "(OPEN-RESETTOKEN-01, SRC-004 R-3: never in the database)"
                           % (t["name"], c["name"]))

    # OPEN-DUPREF-01 - nothing rules what happens when a reference is presented
    # twice, so a redemption column would answer it.
    for c in by_name.get("booking", {}).get("columns", []):
        n = c["name"].lower()
        if "redeem" in n or "redemption" in n or "admitted" in n or "scanned" in n:
            bad.append("booking.%s answers OPEN-DUPREF-01" % c["name"])

    return ("reserved-not-decided", not bad,
            "; ".join(bad) or
            "no unruled reserved question answered by a constraint; %d ruled CHECK(s) "
            "present exactly as filed (%s)"
            % (len(RULED_CHECKS), ", ".join(sorted(RULED_CHECKS))))


# Entity prefixes that appear before a dot in the documents.  This is NOT just
# the table list: the audit vocabulary is keyed on entity names that include the
# lookup tables and `manager`, which is a role and not a table.  An earlier form
# built this from INHERITED_TABLES alone and so could not see
# `certification.created` at all - which made the companion rule report 18
# orphaned actions against a perfectly correct model.
ACTION_PREFIXES = set("""
manager user seat_category certification language genre format movie_genre
manager_screen_assignment
""".split())

DOTTED = re.compile(
    r"\b(" + "|".join(sorted(INHERITED_TABLES | ACTION_PREFIXES,
                             key=len, reverse=True))
    + r")\.([a-z_][a-z0-9_]*)\b")


def bible_references():
    """Every `<table>.<name>` token the acceptance criteria contain.

    Returns {(table, name): [story ids]}.  Deliberately NOT restricted to SQL
    statements: the criteria name columns in prose too, and a column named in
    prose is as much a requirement as one inside a SELECT.
    """
    found = {}
    if not os.path.exists(BIBLE):
        return None
    with io.open(BIBLE, encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            text = row.get("AcceptanceCriteria") or ""
            for tbl, name in DOTTED.findall(text):
                found.setdefault((tbl, name), []).append(row["ID"])
    return found


@rule
def r_bible_references(model):
    """Every `<table>.<name>` in the Bible resolves - as a column OR an action.

    The criteria use the same dotted spelling for two different things:

        booking.user_id        a COLUMN, in SQL and in prose
        'movie.published'      an AUDIT ACTION, a string literal in a WHERE

    An earlier form of this rule checked columns only.  Run against a correct
    schema it failed on about twenty-five references, every one of them an
    audit action or - once - the filename `booking.py`.  That is precisely the
    defect class the Bible census catalogued: a check that fails against a
    correct implementation is worse than no check, because the first person to
    see it red will "fix" the schema to satisfy it.

    So the audit vocabulary is MODELLED rather than guessed at.  datamodel.json
    declares audit_actions, and a reference resolves against either set.  That
    also buys a second guarantee for free: an audit action the Bible expects
    but the model never declares is now a failure rather than a silence.
    """
    found = bible_references()
    if found is None:
        return ("bible-references", False, "Bible not found at " + BIBLE)
    cols = columns_of(model)
    actions = set(model.get("audit_actions", []))
    ignore = set(model.get("bible_reference_exceptions", []))

    bad = {}
    for (tbl, name), stories in found.items():
        token = "%s.%s" % (tbl, name)
        if token in ignore:
            continue
        if tbl in cols and name in cols[tbl]:
            continue
        if token in actions:
            continue
        bad[token] = sorted(set(stories))

    if bad:
        items = sorted(bad.items())
        detail = "; ".join("%s (%s)" % (k, ", ".join(v[:2])) for k, v in items[:8])
        return ("bible-references", False,
                "%d reference(s) resolve to neither a column nor a declared audit "
                "action: %s" % (len(bad), detail))
    return ("bible-references", True,
            "%d distinct references all resolve (%d columns, %d audit actions declared)"
            % (len(found), sum(len(v) for v in cols.values()), len(actions)))


@rule
def r_actions_are_used(model):
    """Every declared audit action is one the documents actually name.

    The mirror of the rule above, and it exists because that rule can be
    satisfied the lazy way: declaring an action for anything that fails.
    A vocabulary nobody cites is a vocabulary somebody invented.
    """
    found = bible_references()
    if found is None:
        return ("actions-cited", False, "Bible not found at " + BIBLE)
    cited = set("%s.%s" % k for k in found)
    # The PRD is where the audit vocabulary is actually decided; the Bible only
    # tests some of it.  Checking the Bible alone would fail an action that is
    # correctly specified and merely untested - which would push the next reader
    # to delete a real action to get the check green.
    for fn in sorted(os.listdir(PRD_SECTIONS)) if os.path.isdir(PRD_SECTIONS) else []:
        if not fn.endswith(".md"):
            continue
        blob = io.open(os.path.join(PRD_SECTIONS, fn), encoding="utf-8").read()
        for tbl, name in DOTTED.findall(blob):
            cited.add("%s.%s" % (tbl, name))
    declared = set(model.get("audit_actions", []))
    orphan = sorted(declared - cited)
    if orphan:
        return ("actions-cited", False,
                "%d declared audit action(s) no criterion names: %s"
                % (len(orphan), ", ".join(orphan[:8])))
    return ("actions-cited", True,
            "every one of the %d declared audit actions is cited" % len(declared))


CARD_DIGITS = re.compile(r"\b(4[0-9]{12}([0-9]{3})?|5[1-5][0-9]{14}|3[47][0-9]{13})\b")


@rule
def r_seed_expectations(model):
    """The seed expectations keep their status, their citations and their place.

    seed_expectations is what generate.py derives seed/expected_summary.json
    from.  Four things can go wrong in it quietly, and each is checked:

      1. An ASSUMED input relabelled as ruled.  Hall sizes are OPEN-SCALE-02
         "pick random", categories OPEN-SEAT-01 "you pick": the client said
         "you pick" on those and nothing else (SRC-003), and an assumption that
         loses its label is how 7 minutes became a requirement once already.
      2. An ASSUMED value hardening into the SCHEMA - a CHECK or a DEFAULT that
         carries a seeded category name, price, uplift, DEMO name or the seed's
         row-letter alphabet.  The seed is demonstration data; the schema must
         accept the client's real halls and real names unchanged.
      3. An uncited expectation, invariant or gap.
      4. Card-shaped data - a field name or a digit run - anywhere in the block.
    """
    se = model.get("seed_expectations")
    if not se:
        return ("seed-expectations", False, "datamodel.json has no seed_expectations block")
    bad = []
    want = [("screens", "ASSUMED", "OPEN-SCALE-02"),
            ("seat_categories", "ASSUMED", "OPEN-SEAT-01"),
            ("lookup_vocabulary", "ASSUMED", "OPEN-ATTRIB-01"),
            ("base_price_paise", "ASSUMED", "P-XCT-30"),
            ("manager_mapping", "PROVISIONAL", "SRC-003 C-1")]
    for key, status, cite in want:
        blk = se.get(key) or {}
        if not str(blk.get("status", "")).startswith(status):
            bad.append("%s.status must start %s" % (key, status))
        if cite not in (str(blk.get("cite", "")) + " " + str(blk.get("status", ""))):
            bad.append("%s must cite %s" % (key, cite))

    tables = set(t["name"] for t in model["tables"])
    te = set(k for k in se.get("table_expectations", {}) if not k.startswith("$"))
    if te != tables:
        bad.append("table_expectations covers %d of %d tables (missing %s, unknown %s)"
                   % (len(te & tables), len(tables), sorted(tables - te)[:3],
                      sorted(te - tables)[:3]))
    for k, e in se.get("table_expectations", {}).items():
        if not k.startswith("$") and not e.get("cite"):
            bad.append("table_expectations.%s is uncited" % k)
    for kind in ("invariants", "unspecified"):
        for i, e in enumerate(se.get(kind, [])):
            if not e.get("cite"):
                bad.append("%s[%d] is uncited" % (kind, i))

    hardened = [c["name"] for c in se.get("seat_categories", {}).get("rows", [])]
    hardened += ["DEMO", se.get("row_letters", {}).get("letters", "") or "\0",
                 str(se.get("base_price_paise", {}).get("value", "\0"))]
    hardened += [str(c["uplift_basis_points"]) for c in
                 se.get("seat_categories", {}).get("rows", []) if c["uplift_basis_points"]]
    # Hall sizes and grid dimensions (OPEN-SCALE-02, ASSUMED).  Bare small numbers
    # collide with unrelated constraints (a {8} in a regex, BETWEEN 1 AND 60), so
    # they are checked only on the tables that describe a hall's geometry.
    geometry = sorted(set([str(lay["seats"]) for lay in se.get("screens", {}).get("layouts", [])]
                          + [str(len(lay["rows"])) for lay in se.get("screens", {}).get("layouts", [])]), key=int)
    for t in model["tables"]:
        blobs = [("CHECK " + ck.get("name", "?"), ck.get("expression", ""))
                 for ck in t.get("checks", [])]
        blobs += [("DEFAULT " + c["name"], str(c.get("default") or ""))
                  for c in t["columns"]]
        for where, text in blobs:
            for v in hardened + (geometry if t["name"] in GEOMETRY_TABLES else []):
                if v and re.search(r"(?<![A-Za-z0-9])" + re.escape(v) + r"(?![A-Za-z0-9])", text):
                    bad.append("%s.%s carries the seeded value %r - ASSUMED never "
                               "hardens into a constraint" % (t["name"], where, v))

    blob = json.dumps(se, ensure_ascii=False)
    if CARD_SHAPED.search(blob) or CARD_DIGITS.search(blob):
        bad.append("card-shaped data in seed_expectations")
    return ("seed-expectations", not bad,
            "; ".join(bad[:5]) or
            "%d table expectations, %d invariants, %d gaps - all cited; ASSUMED labels kept; "
            "seeded names, row letters, base price and uplifts absent from every CHECK and "
            "DEFAULT; hall sizes and grid dimensions (%s) absent from every CHECK and DEFAULT "
            "on %s"
            % (len(te), len(se.get("invariants", [])), len(se.get("unspecified", [])),
               "/".join(geometry), ", ".join(sorted(GEOMETRY_TABLES))))


GEOMETRY_TABLES = set(["screen", "seat", "showtime", "showtime_seat"])
FR_ADR = re.compile(r"FR-ADR-\d{3}")


def schema_adr_citations(model):
    """{FR-ADR id: sorted [table.object]} over the schema objects in `tables`.

    The same scope the ledger's existing `DataModel:` notes list: tables,
    columns, constraints and indexes.  seed_expectations, meta and roles are
    excluded - they are test-oracle inputs and prose, not schema the decision
    landed in.
    """
    out = {}
    for t in model["tables"]:
        objs = [(t["name"], t)] + [("%s.%s" % (t["name"], c["name"]), c) for c in t["columns"]]
        for kind in ("unique", "checks", "foreign_keys", "indexes"):
            objs += [("%s.%s" % (t["name"], o.get("name", "?")), o) for o in t.get(kind, [])]
        for label, o in objs:
            text = " ".join(str(o.get(k) or "") for k in ("cite", "note", "why", "purpose"))
            for a in FR_ADR.findall(text):
                out.setdefault(a, set()).add(label)
    return dict((k, sorted(v)) for k, v in out.items())


@rule
def r_ledger_datamodel(model):
    """The ADR ledger's included_in_datamodel column is DERIVED, never asserted.

    docs/01 ADR/README.md: "derive the cell from the citations actually present
    in the target document, never by assertion".  A row (keyed on adr_id) reads
    INCLUDED exactly when a schema object in datamodel.json cites that FR-ADR id.
    NOT_APPLICABLE is accepted wherever NOT_INCLUDED would be (README: legal when
    justified in notes).  A cited id with no ledger row is a dangling citation.
    """
    if not os.path.exists(LEDGER):
        return ("ledger-datamodel", False, "ADR ledger not found at " + LEDGER)
    with io.open(LEDGER, encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh, delimiter="\t"))
    cited = schema_adr_citations(model)
    ids = set(r["adr_id"] for r in rows)
    bad = ["%s is cited by %s but has no ledger row" % (a, cited[a][0])
           for a in sorted(set(cited) - ids)]
    for r in rows:
        have = r.get("included_in_datamodel", "")
        want = "INCLUDED" if r["adr_id"] in cited else "NOT_INCLUDED"
        if have == want or (want == "NOT_INCLUDED" and have == "NOT_APPLICABLE"):
            continue
        bad.append("%s reads %s, datamodel.json says %s%s"
                   % (r["adr_id"], have or "(blank)", want,
                      (" (cited by %s)" % ", ".join(cited[r["adr_id"]][:2]))
                      if want == "INCLUDED" else ""))
    return ("ledger-datamodel", not bad,
            ("%d mismatch(es): %s" % (len(bad), "; ".join(bad[:6]))) if bad else
            "%d ledger rows: %d INCLUDED, each cited by a schema object; the rest cited by none"
            % (len(rows), len(cited)))


# ------------------------------------------------------------------ driver

def run(model, quiet=False):
    fails = 0
    for fn in RESULTS:
        name, ok, msg = fn(model)
        if not ok:
            fails += 1
        if not quiet:
            print("%s  %-22s %s" % ("PASS" if ok else "FAIL", name, msg))
    return fails


def selftest():
    """Plant one defect per rule and prove that rule, and only it, goes red."""
    base = load()
    planted = 0
    proved = 0

    def probe(label, mutate, expect):
        nonlocal planted, proved
        m = json.loads(json.dumps(base))
        mutate(m)
        planted += 1
        outcomes = {}
        for fn in RESULTS:
            name, ok, _msg = fn(m)      # each rule runs once; calling twice to
            outcomes[name] = ok          # read name and ok separately is wasteful
        went_red = outcomes.get(expect) is False
        if went_red:
            proved += 1
        print("  %-46s -> %-18s %s"
              % (label, expect, "RED (correct)" if went_red
                 else "STAYED GREEN - RULE IS BROKEN"))

    def first_table(m, name):
        for t in m["tables"]:
            if t["name"] == name:
                return t
        return m["tables"][0]

    probe("rename booking -> bookings",
          lambda m: first_table(m, "booking").__setitem__("name", "bookings"),
          "table-set")
    probe("strip a citation",
          lambda m: first_table(m, "booking")["columns"][0].pop("cite", None),
          "uncited")
    probe("make a price column text",
          lambda m: first_table(m, "booking")["columns"].append(
              {"name": "total_price", "type": "text", "nullable": True, "cite": "x"}),
          "money-integer")
    probe("add a card_number column",
          lambda m: first_table(m, "payment")["columns"].append(
              {"name": "card_number", "type": "text", "nullable": True, "cite": "x"}),
          "no-card-data")
    probe("add a next_run_at column",
          lambda m: first_table(m, "outbox_message")["columns"].append(
              {"name": "next_run_at", "type": "timestamptz", "nullable": True, "cite": "x"}),
          "deleted-scope")
    def cascade_one_fk(m):
        for t in m["tables"]:
            if t.get("foreign_keys"):
                t["foreign_keys"][0]["on_delete"] = "CASCADE"
                return

    probe("turn one foreign key into ON DELETE CASCADE", cascade_one_fk,
          "fk-restrict")
    probe("default a decision-bearing instant to now()",
          lambda m: first_table(m, "showtime")["columns"].append(
              {"name": "opens_at", "type": "timestamptz", "nullable": False,
               "default": "now()", "cite": "x"}),
          "clock-defaults")

    def strip_created_at_default(m):
        for t in m["tables"]:
            for c in t["columns"]:
                if c["name"] == "created_at":
                    c["default"] = None
                    return

    probe("remove created_at's now() default", strip_created_at_default,
          "clock-defaults")
    probe("make an _at column a date",
          lambda m: first_table(m, "booking")["columns"].append(
              {"name": "settled_at", "type": "date", "nullable": True, "cite": "x"}),
          "timestamptz")
    def drop_seat_guarantee(m):
        # Strip it from BOTH unique constraints and indexes.  An earlier form of
        # this probe chained the two with `or`, and a list of Nones is truthy, so
        # the second half never ran: the probe would have passed while leaving an
        # index still carrying the guarantee.
        pair = set(["showtime_id", "seat_id"])
        for t in m["tables"]:
            for kind in ("unique", "indexes"):
                t[kind] = [u for u in t.get(kind, [])
                           if set(c.lower() for c in u.get("columns", [])) != pair]

    probe("drop the (showtime_id, seat_id) unique", drop_seat_guarantee,
          "seat-guarantee")

    def make_guard_partial(m):
        # The insidious one.  A partial guard still shows up in every "does the
        # constraint exist" check, and still frees the pair for every row its
        # predicate excludes.  It is what a reasonable person adds the day
        # cancellation is asked for.
        g = m.get("seat_guarantee") or {}
        for t in m["tables"]:
            if t["name"] != g.get("table"):
                continue
            for u in list(t.get("unique", [])) + list(t.get("indexes", [])):
                if u.get("name") == g.get("constraint"):
                    u["where"] = "cancelled_at IS NULL"

    probe("make the seat guard a PARTIAL index", make_guard_partial,
          "seat-guarantee")
    probe("collapse email_claimed_at into email_sent_at",
          lambda m: first_table(m, "password_reset_token").__setitem__(
              "columns", [c for c in first_table(m, "password_reset_token")["columns"]
                          if c["name"] != "email_claimed_at"]),
          "reset-token-three")
    probe("CHECK the booking-reference alphabet",
          lambda m: first_table(m, "booking").setdefault("checks", []).append(
              {"name": "ck_ref", "expression": "reference ~ '^[A-Z2-9]{8}$'", "cite": "x"}),
          "reserved-not-decided")
    probe("CHECK char_length(reference) on booking",
          lambda m: first_table(m, "booking")["checks"].append(
              {"name": "ck_ref_len", "expression": "char_length(reference) = 9", "cite": "x"}),
          "reserved-not-decided")
    probe("add a seat_hold table (OPEN-HOLDRECOVER-01)",
          lambda m: m["tables"].append(
              {"name": "seat_hold", "columns": [{"name": "id", "type": "bigint",
                                                  "nullable": False, "cite": "x"}]}),
          "reserved-not-decided")
    probe("add booking.admitted_at (OPEN-DUPREF-01)",
          lambda m: first_table(m, "booking")["columns"].append(
              {"name": "admitted_at", "type": "timestamptz", "nullable": True, "cite": "x"}),
          "reserved-not-decided")
    probe("add outbox_message.plaintext_token",
          lambda m: first_table(m, "outbox_message")["columns"].append(
              {"name": "plaintext_token", "type": "text", "nullable": True, "cite": "x"}),
          "reserved-not-decided")
    probe("CHECK banning the letter I in row_label",
          lambda m: first_table(m, "seat")["checks"].append(
              {"name": "ck_seat__no_i", "expression": "row_label !~ 'I'", "cite": "SRC-004 R-4"}),
          "reserved-not-decided")
    probe("drop the ruled row_label CHECK (SRC-004 R-4)",
          lambda m: first_table(m, "seat").__setitem__(
              "checks", [c for c in first_table(m, "seat")["checks"]
                         if c["name"] != "ck_seat__row_label_upper"]),
          "reserved-not-decided")
    probe("harden a hall grid width into a seat CHECK",
          lambda m: first_table(m, "seat")["checks"].append(
              {"name": "ck_seat__grid_col_max", "expression": "grid_col <= 20", "cite": "x"}),
          "seed-expectations")
    probe("cite an ADR the ledger marks NOT_INCLUDED",
          lambda m: first_table(m, "booking")["columns"][0].__setitem__(
              "cite", first_table(m, "booking")["columns"][0]["cite"] + " · FR-ADR-001"),
          "ledger-datamodel")
    probe("cite a column the Bible does not know",
          lambda m: first_table(m, "booking").__setitem__(
              "columns", [c for c in first_table(m, "booking")["columns"]
                          if c["name"] != "id"]),
          "bible-references")
    probe("relabel the ASSUMED hall sizes as RULED",
          lambda m: m["seed_expectations"]["screens"].__setitem__("status", "RULED"),
          "seed-expectations")
    probe("harden the seeded categories into a CHECK",
          lambda m: first_table(m, "seat_category")["checks"].append(
              {"name": "ck_seat_category__names",
               "expression": "name IN ('Standard', 'Premium', 'Recliner')", "cite": "x"}),
          "seed-expectations")
    probe("strip the citation from a seed invariant",
          lambda m: m["seed_expectations"]["invariants"][0].pop("cite"),
          "seed-expectations")
    probe("put a card-shaped number in a seed gap",
          lambda m: m["seed_expectations"]["unspecified"].append(
              {"what": "5" + "5" * 15, "cite": "x", "kind": "x"}),
          "seed-expectations")

    print()
    print("VERDICT: %d of %d rules watched going red." % (proved, planted))
    if proved != planted:
        print("         A rule that stayed green cannot be trusted when it is green.")
    return 0 if proved == planted else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        print("Red-proofing every rule by planting a defect it must catch.")
        print("=" * 78)
        return selftest()
    model = load()
    print("datamodel.json vs the documents it was derived from")
    print("=" * 78)
    fails = run(model)
    print()
    print("rules: %d  -  %d pass  -  %d fail" % (len(RESULTS), len(RESULTS) - fails, fails))
    if fails:
        print("VERDICT: FAIL")
        return 1
    print("VERDICT: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())

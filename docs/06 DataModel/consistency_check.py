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
NL = chr(10)

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

    # OPEN-REFCHAR-01 - the reference alphabet is reserved and irreversible.
    for t in model["tables"]:
        for ck in t.get("checks", []):
            expr = ck["expression"].lower()
            if "reference" in expr and ("~" in expr or "similar to" in expr):
                bad.append("%s: a CHECK constrains the booking-reference alphabet "
                           "(OPEN-REFCHAR-01)" % ck.get("name", t["name"]))

    # OPEN-SEATLABEL-01 / OPEN-SEATALPHA-01 - row_label normalisation and alphabet.
    for t in model["tables"]:
        for ck in t.get("checks", []):
            if "row_label" in ck["expression"].lower():
                bad.append("%s: a CHECK constrains row_label "
                           "(OPEN-SEATLABEL-01 / OPEN-SEATALPHA-01)"
                           % ck.get("name", t["name"]))

    # OPEN-HOLDRECOVER-01 - a live hold is Redis-only and has no row.
    for name in by_name:
        if "hold" in name:
            bad.append("%s: holds have no database row (OPEN-HOLDRECOVER-01), and a "
                       "table would put the seat guarantee in two places" % name)

    # OPEN-RESETTOKEN-01 - the flow is unbuildable as specified; do not make one
    # resolution cheap by providing somewhere for the plaintext to live.
    for c in by_name.get("password_reset_token", {}).get("columns", []):
        n = c["name"].lower()
        if n == "token" or "token_plain" in n or "plaintext" in n:
            bad.append("password_reset_token.%s stores the token itself "
                       "(OPEN-RESETTOKEN-01, reserved: secrets)" % c["name"])

    # OPEN-DUPREF-01 - nothing rules what happens when a reference is presented
    # twice, so a redemption column would answer it.
    for c in by_name.get("booking", {}).get("columns", []):
        n = c["name"].lower()
        if "redeem" in n or "redemption" in n or "admitted" in n or "scanned" in n:
            bad.append("booking.%s answers OPEN-DUPREF-01" % c["name"])

    return ("reserved-not-decided", not bad,
            "; ".join(bad) or "no reserved question answered by a constraint")


DOTTED = re.compile(r"\b(" + "|".join(sorted(INHERITED_TABLES, key=len, reverse=True))
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
    probe("cite a column the Bible does not know",
          lambda m: first_table(m, "booking").__setitem__(
              "columns", [c for c in first_table(m, "booking")["columns"]
                          if c["name"] != "id"]),
          "bible-references")

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

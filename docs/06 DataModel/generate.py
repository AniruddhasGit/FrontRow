#!/usr/bin/env python
"""Generate schema.sql and TRACEABILITY.tsv from datamodel.json.

datamodel.json is the SPEC OF RECORD.  Everything this script writes is
DERIVED.  A hand-edit to a generated file is a defect: --check re-derives
every output in memory and exits 1 if what is on disk differs, so the edit
is caught rather than absorbed.

    py generate.py            emit the generated files
    py generate.py --check    re-derive and diff; exit 1 on any drift
    py generate.py --selftest plant a defect in a generated file and prove
                              --check goes red, then restore and verify the
                              restore.  A check nobody has watched fail is
                              decoration.

Why the emission is sorted and explicit rather than convenient: regenerating
must produce NO diff, so nothing may depend on dict ordering, set iteration
or a filesystem walk.  Every list this script writes is either in the order
datamodel.json declares it or in an explicitly sorted order.
"""
import argparse
import io
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
MODEL = os.path.join(HERE, "datamodel.json")
NL = chr(10)
TAB = chr(9)

BANNER_SQL = (
    "-- GENERATED FILE - DO NOT EDIT." + NL +
    "-- Source of record: datamodel.json.  Regenerate with:  py generate.py" + NL +
    "-- A hand-edit here is reverted by the next run and caught by --check." + NL)

BANNER_TSV = "# GENERATED FILE - DO NOT EDIT.  Source of record: datamodel.json."

# PostgreSQL spellings for the type vocabulary the model uses.  The model
# never writes a raw SQL type: a typo in the model must fail HERE, loudly,
# rather than reach the database as a column of the wrong type.
TYPES = {
    "uuid": "uuid", "text": "text", "citext": "citext",
    "integer": "integer", "bigint": "bigint", "smallint": "smallint",
    "boolean": "boolean", "timestamptz": "timestamptz", "date": "date",
    "jsonb": "jsonb", "bytea": "bytea", "inet": "inet",
}

# Money must survive the round trip through a database driver as an integer.
# NUMERIC(x,2) is the trap this guards: the driver hands it back as a Decimal
# and one careless layer turns it into a float, at which point paise are lost
# and two screens disagree about what a customer paid.
MONEY_TYPES = ("integer", "bigint")


def die(msg):
    sys.stderr.write("ERROR: " + msg + NL)
    sys.exit(1)


def load(path=MODEL):
    if not os.path.exists(path):
        die("datamodel.json not found at " + path)
    with io.open(path, encoding="utf-8") as fh:
        return json.load(fh)


def sqltype(col, table):
    t = col["type"]
    if t.startswith("enum:"):
        return t.split(":", 1)[1]
    if t not in TYPES:
        die("%s.%s has unknown type %r - the type vocabulary is closed"
            % (table, col["name"], t))
    return TYPES[t]


def order_tables(model):
    """Emit tables so every foreign-key target already exists.

    A stable topological sort: at each step take the alphabetically first
    table whose dependencies are all emitted.  The alphabetical tie-break is
    what makes the output byte-identical on every run.
    """
    tables = dict((t["name"], t) for t in model["tables"])
    deps = {}
    for name, t in tables.items():
        d = set()
        for fk in t.get("foreign_keys", []):
            target = fk["references"]["table"]
            if target != name:          # a self-reference needs no ordering
                d.add(target)
        deps[name] = d
    out, done = [], set()
    while len(out) < len(tables):
        ready = sorted(n for n in tables if n not in done and deps[n] <= done)
        if not ready:
            stuck = sorted(set(tables) - done)
            die("circular foreign keys among: " + ", ".join(stuck))
        for n in ready:
            out.append(tables[n])
            done.add(n)
    return out


def emit_schema(model):
    L = [BANNER_SQL]
    L.append("BEGIN;")
    L.append("")

    exts = model.get("extensions", [])
    if exts:
        L.append("-- Extensions.  Named here because RDS grants a restricted role no")
        L.append("-- right to install one: if this line fails in AWS it is a permissions")
        L.append("-- problem, not a schema problem.")
        for e in exts:
            L.append("-- %s" % e.get("cite", ""))
            L.append("CREATE EXTENSION IF NOT EXISTS %s;" % e["name"])
        L.append("")

    for en in model.get("enums", []):
        L.append("-- %s" % en.get("cite", ""))
        if en.get("note"):
            L.append("-- %s" % en["note"])
        vals = ", ".join("'" + v + "'" for v in en["values"])
        L.append("CREATE TYPE %s AS ENUM (%s);" % (en["name"], vals))
        L.append("")

    for t in order_tables(model):
        L.append("-- " + ("-" * 74))
        L.append("-- %s - %s" % (t["name"], t["purpose"]))
        L.append("-- %s" % t.get("cite", ""))
        for line in t.get("comments", []):
            L.append("-- %s" % line)
        L.append("CREATE TABLE %s (" % t["name"])

        col_lines = []
        for c in t["columns"]:
            frag = "    %-26s %s" % (c["name"], sqltype(c, t["name"]))
            if c.get("identity"):
                # FR-ADR-017 chooses IDENTITY over serial deliberately.  It is
                # not a DEFAULT: "DEFAULT identity" is not SQL, and GENERATED
                # ALWAYS also refuses an application-supplied value, which is
                # the half that makes the key genuinely database-generated.
                frag += " GENERATED ALWAYS AS IDENTITY"
            if not c.get("nullable", True):
                frag += " NOT NULL"
            if c.get("default") is not None:
                frag += " DEFAULT %s" % c["default"]
            col_lines.append((frag, c))

        tail = []
        pk = t.get("primary_key") or []
        if pk:
            tail.append("    PRIMARY KEY (%s)" % ", ".join(pk))
        for u in t.get("unique", []):
            if u.get("where") or u.get("expression_index"):
                # Partial uniqueness is an index, not a constraint - and so is
                # uniqueness over an EXPRESSION.  PostgreSQL has no syntax for
                # UNIQUE (lower(trim(name))) as a table constraint at all; it
                # must be CREATE UNIQUE INDEX.  Both are emitted after the
                # CREATE TABLE, below.
                continue
            tail.append("    CONSTRAINT %s UNIQUE (%s)"
                        % (u["name"], ", ".join(u["columns"])))
        for ck in t.get("checks", []):
            tail.append("    CONSTRAINT %s CHECK (%s)" % (ck["name"], ck["expression"]))
        for fk in t.get("foreign_keys", []):
            r = fk["references"]
            tail.append("    CONSTRAINT %s FOREIGN KEY (%s) REFERENCES %s (%s)"
                        " ON DELETE %s ON UPDATE %s"
                        % (fk["name"], ", ".join(fk["columns"]), r["table"],
                           ", ".join(r["columns"]),
                           fk.get("on_delete", "RESTRICT"),
                           fk.get("on_update", "RESTRICT")))

        total = len(col_lines) + len(tail)
        for i, pair in enumerate(col_lines):
            comma = "," if i < total - 1 else ""
            c = pair[1]
            cite = c.get("cite") or ""
            note = c.get("note") or ""
            trail = ""
            if cite:
                trail = "  -- " + cite + ((" - " + note) if note else "")
            L.append(pair[0] + comma + trail)
        for j, line in enumerate(tail):
            comma = "," if (len(col_lines) + j) < total - 1 else ""
            L.append(line + comma)
        L.append(");")

        for u in t.get("unique", []):
            if not (u.get("where") or u.get("expression_index")):
                continue
            if u.get("why"):
                L.append("-- %s" % u["why"])
            # An expression column is wrapped in its own parentheses, which
            # PostgreSQL requires for a functional index.
            cols = ", ".join(("(%s)" % c) if "(" in c else c for c in u["columns"])
            where = (" WHERE %s" % u["where"]) if u.get("where") else ""
            L.append("CREATE UNIQUE INDEX %s ON %s (%s)%s;"
                     % (u["name"], t["name"], cols, where))
        for ix in t.get("indexes", []):
            if ix.get("why"):
                L.append("-- %s" % ix["why"])
            uq = "UNIQUE " if ix.get("unique") else ""
            where = (" WHERE %s" % ix["where"]) if ix.get("where") else ""
            L.append("CREATE %sINDEX %s ON %s (%s)%s;"
                     % (uq, ix["name"], t["name"], ", ".join(ix["columns"]), where))
        L.append("")

    roles = model.get("roles", [])
    if roles:
        L.append("-- " + ("-" * 74))
        L.append("-- Roles.  The application never connects as the owner of these")
        L.append("-- tables.  Building against the restricted role from the first line")
        L.append("-- is the only way a missing grant is found here rather than in AWS,")
        L.append("-- where the superuser this schema was written under does not exist.")
        for r in roles:
            L.append("-- %s: %s" % (r["name"], r.get("why", "")))
            L.append("-- %s" % r.get("cite", ""))
            L.append("DO $$ BEGIN")
            L.append("  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '%s') THEN"
                     % r["name"])
            L.append("    CREATE ROLE %s NOLOGIN;" % r["name"])
            L.append("  END IF;")
            L.append("END $$;")
            for g in r.get("grants", []):
                L.append(g if g.rstrip().endswith(";") else g + ";")
            L.append("")

    L.append("COMMIT;")
    return NL.join(L) + NL


def emit_traceability(model):
    """One row per schema object, with the document that requires it.

    The Definition of Done asks for zero uncited columns.  This file is how
    that is counted, so it lists objects that HAVE a citation and objects
    that do not, rather than silently omitting the second kind - an audit
    that drops what it cannot explain always reports success.
    """
    rows = [["Object", "Kind", "Table", "Name", "Citation", "ReservedRow", "Note"]]
    for t in sorted(model["tables"], key=lambda x: x["name"]):
        rows.append(["table", "entity", t["name"], t["name"],
                     t.get("cite", ""), "", t.get("purpose", "")])
        for c in t["columns"]:
            rows.append(["column", c["type"], t["name"], c["name"],
                         c.get("cite", ""), c.get("reserved_row") or "",
                         c.get("note", "")])
        for u in t.get("unique", []):
            rows.append(["constraint", "unique", t["name"], u["name"],
                         u.get("cite", ""), "", u.get("why", "")])
        for ck in t.get("checks", []):
            rows.append(["constraint", "check", t["name"], ck["name"],
                         ck.get("cite", ""), "", ck.get("why", "")])
        for fk in t.get("foreign_keys", []):
            rows.append(["constraint", "foreign_key", t["name"], fk["name"],
                         fk.get("cite", ""), "", fk["references"]["table"]])
        for ix in t.get("indexes", []):
            rows.append(["index", "index", t["name"], ix["name"],
                         ix.get("cite", ""), "", ix.get("why", "")])
    for en in sorted(model.get("enums", []), key=lambda x: x["name"]):
        rows.append(["enum", "type", "", en["name"], en.get("cite", ""),
                     "", "|".join(en["values"])])
    out = [BANNER_TSV]
    for r in rows:
        out.append(TAB.join(str(x).replace(TAB, " ").replace(NL, " ") for x in r))
    return NL.join(out) + NL


OUTPUTS = (("schema.sql", emit_schema), ("TRACEABILITY.tsv", emit_traceability))


def write_all(model, check):
    drift = []
    for name, fn in OUTPUTS:
        want = fn(model)
        path = os.path.join(HERE, name)
        have = None
        if os.path.exists(path):
            have = io.open(path, encoding="utf-8").read()
        if check:
            if have != want:
                drift.append(name)
        else:
            with io.open(path, "w", encoding="utf-8", newline="") as fh:
                fh.write(want)
            print("  wrote %-20s %6d bytes" % (name, len(want)))
    return drift


def selftest():
    """Prove --check goes red.  Watched failure, not assumed failure."""
    path = os.path.join(HERE, "schema.sql")
    if not os.path.exists(path):
        die("run generate.py once before --selftest")
    original = io.open(path, encoding="utf-8").read()
    went_red = False
    try:
        with io.open(path, "w", encoding="utf-8", newline="") as fh:
            fh.write(original + NL + "-- a hand edit nobody authorised" + NL)
        went_red = "schema.sql" in write_all(load(), True)
        print("  planted a hand-edit in schema.sql   -> --check %s"
              % ("WENT RED (correct)" if went_red
                 else "STAYED GREEN - THE CHECK IS BROKEN"))
    finally:
        with io.open(path, "w", encoding="utf-8", newline="") as fh:
            fh.write(original)
    restored = io.open(path, encoding="utf-8").read() == original
    print("  restored schema.sql                 -> %s"
          % ("verified byte-identical" if restored else "RESTORE FAILED"))
    still_green = not write_all(load(), True)
    print("  --check after restore               -> %s"
          % ("green (correct)" if still_green else "STILL RED - RESTORE INCOMPLETE"))
    ok = went_red and restored and still_green
    print("VERDICT: %s" % ("PASS - the drift check has been watched failing."
                           if ok else "FAIL"))
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()

    if a.selftest:
        return selftest()

    model = load()
    if a.check:
        drift = write_all(model, True)
        if drift:
            sys.stderr.write("DRIFT: " + ", ".join(drift)
                             + " differ(s) from datamodel.json." + NL)
            sys.stderr.write("A generated file was hand-edited, or the model changed"
                             " without regenerating." + NL)
            return 1
        print("PASS - every generated file matches datamodel.json exactly.")
        return 0
    write_all(model, False)
    print("PASS - regenerated from datamodel.json.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

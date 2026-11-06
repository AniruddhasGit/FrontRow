#!/usr/bin/env python
"""Generate every derived file of this package from datamodel.json.

    schema.sql                   the DDL
    TRACEABILITY.tsv             one row per schema object, with its citation
    seed/expected_summary.json   what a correct seed must produce (expectations,
                                 never seed data), re-derived from the seed rules
    fingerprints.json            SHA-256 of datamodel.json and of the three files
                                 above, plus per-table structural fingerprints

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
import hashlib
import io
import json
import os
import re
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
        L.append("-- ORDER: the roles must EXIST before this file runs.  schema.sql creates")
        L.append("-- no role: roles belong to the operator - checks/roles_local.sql locally,")
        L.append("-- the client on RDS.  Run as the owner, a missing role makes the GRANT")
        L.append("-- below fail and the whole file roll back, which is the correct failure.")
        for r in roles:
            L.append("-- %s: %s" % (r["name"], r.get("why", "")))
            L.append("-- %s" % r.get("cite", ""))
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


# ------------------------------------------------------------ seed expectations
#
# seed/expected_summary.json is what a correct scripts/seed.py must produce
# against an EMPTY, migrated database.  It is derived from the rules in
# datamodel.json -> seed_expectations, which transcribe P-XCT-30 / P-XCT-32 /
# S-XCT-44 / S-XCT-45.  This script never writes a row of seed data: it runs the
# seed's ARITHMETIC (which showtime books how many seats, in how many bookings)
# so that every count the PRD publishes is re-derived rather than copied.  A
# published figure the rules do not reproduce stops the run, because S1.5
# transcribes these figures into tests and a wrong figure is a wrong test.

SEED_SUMMARY = os.path.join("seed", "expected_summary.json")
FINGERPRINTS = "fingerprints.json"

BANNER_JSON = ("GENERATED FILE - DO NOT EDIT.  Source of record: datamodel.json.  "
               "Regenerate with:  py generate.py   A hand-edit is reverted by the "
               "next run and caught by  py generate.py --check.")

# Card-shaped digit runs: no card data anywhere, not even in an expectation.
CARD_DIGITS = re.compile(r"\b(4[0-9]{12}([0-9]{3})?|5[1-5][0-9]{14}|3[47][0-9]{13})\b")


def ceil_frac(n, frac):
    num, den = frac
    return -((-n * num) // den)          # integer ceiling, no float anywhere


def price_paise(base, uplift_bp):
    # FR-ADR-038's integer half-up rule, verbatim from S-RPT-04.  Integers only:
    # a float here is how two screens come to disagree about a total.
    return (base * (10000 + uplift_bp) + 5000) // 10000


def derive_seed(model):
    """Run the seed's arithmetic.  Returns every derived figure, by name."""
    se = model.get("seed_expectations")
    if not se:
        die("datamodel.json has no seed_expectations block")
    letters = se["row_letters"]["letters"]
    cats = se["seat_categories"]["rows"]
    if [c["name"] for c in cats] != ["Standard", "Premium", "Recliner"]:
        die("seed_expectations.seat_categories must list the three bands in "
            "screen-to-back order: Standard, Premium, Recliner (P-XCT-30)")
    base = se["base_price_paise"]["value"]
    prices = dict((c["name"], price_paise(base, c["uplift_basis_points"])) for c in cats)

    screens = []
    for lay in se["screens"]["layouts"]:
        # CR-003: rows are typed per hall - (label, category, seats) front to back - not a rows x cols grid.
        rows = lay["rows"]
        if sum(r[2] for r in rows) != lay["seats"]:
            die("Screen %d: its rows hold %d seats, not %d (P-XCT-30 exception 9)"
                % (lay["number"], sum(r[2] for r in rows), lay["seats"]))
        labels = "".join(r[0] for r in rows)
        if len(set(labels)) != len(labels) or not set(labels) <= set(letters):
            die("Screen %d: row labels %s are not unique row letters" % (lay["number"], labels))
        if rows[0][1] != "Standard" or "Recliner" not in [r[1] for r in rows]:
            die("Screen %d: Standard must be nearest the screen and a Recliner row must exist (CR-003)" % lay["number"])
        seat_cat = [r[1] for r in rows for _ in range(r[2])]   # seat order: row A seat 1 onward
        screens.append({
            "number": lay["number"], "seats": lay["seats"], "rows": len(rows), "row_labels": labels,
            "seat_cat": seat_cat,
            "bands": [(c["name"], sum(1 for r in rows if r[1] == c["name"]),
                       "".join(r[0] for r in rows if r[1] == c["name"]),
                       sum(r[2] for r in rows if r[1] == c["name"])) for c in cats],
        })

    sch, occ, bk = se["schedule"], se["occupancy"], se["bookings"]
    days, slots = sch["days"], len(sch["local_starts"])
    nfilms = se["films"]["count"]
    nfmt = len(se["lookup_vocabulary"]["format"])
    ncust = se["accounts"]["customer"]
    nscr = len(screens)

    per_screen = dict((s["number"], {"showtimes": 0, "booked": 0}) for s in screens)
    per_film = [0] * nfilms
    per_format = [0] * nfmt
    past = future = 0
    booked_total = 0
    booked_by_cat = dict((c["name"], 0) for c in cats)
    revenue_by_cat = dict((c["name"], 0) for c in cats)
    owners = [0] * ncust
    size_hist = {}
    bi = 0
    min_booked, full_showtimes = None, 0
    examples = {}

    for d in range(days):
        for s in range(slots):
            for h, scr in enumerate(screens):
                k = d * slots * nscr + s * nscr + h
                n = scr["seats"]
                pct = occ["base_percent"] + (k % occ["cycle"]) * occ["step_percent"]
                booked = (n * pct) // 100
                min_booked = booked if min_booked is None else min(min_booked, booked)
                full_showtimes += 1 if booked >= n else 0
                film = (k + d) % nfilms
                per_film[film] += 1
                per_format[(d * slots + s) % nfmt] += 1
                if d + sch["day_offset"] < 0:
                    past += 1
                else:
                    future += 1
                per_screen[scr["number"]]["showtimes"] += 1
                per_screen[scr["number"]]["booked"] += booked
                booked_total += booked
                for seat_i in range(booked):           # contiguous from row A seat 1
                    cat = scr["seat_cat"][seat_i]
                    booked_by_cat[cat] += 1
                    revenue_by_cat[cat] += prices[cat]
                remaining = booked
                while remaining > 0:
                    size = min(1 + (bi % bk["size_cycle"]), remaining)
                    owners[bi % ncust] += 1
                    size_hist[size] = size_hist.get(size, 0) + 1
                    bi += 1
                    remaining -= size
                if k in (231, 399):
                    examples[k] = {"day": d + 1, "slot": sch["local_starts"][s],
                                   "screen": scr["number"], "occupancy_percent": pct,
                                   "booked_seats": booked, "film_index": film}

    total_seats = sum(s["seats"] for s in screens)
    showtimes = days * slots * nscr
    runtimes = [se["films"]["runtime_base_minutes"] + i * se["films"]["runtime_step_minutes"]
                for i in range(nfilms)]
    spacing = []
    for a, b in zip(sch["local_starts"], sch["local_starts"][1:]):
        ha, ma = map(int, a.split(":"))
        hb, mb = map(int, b.split(":"))
        spacing.append((hb * 60 + mb) - (ha * 60 + ma))
    voc = se["lookup_vocabulary"]
    acc = se["accounts"]
    mean_occ_bp = (booked_total * 1000000) // (showtimes // nscr * total_seats)  # x10^4 %

    films = []
    for i in range(nfilms):
        films.append({
            "title": se["films"]["title_format"] % (i + 1),
            "runtime_minutes": runtimes[i],
            "language": voc["language"][i % len(voc["language"])],
            "certification": voc["certification"][i % len(voc["certification"])],
            "genres": [voc["genre"][i % len(voc["genre"])],
                       voc["genre"][(i + 1) % len(voc["genre"])]],
            "showtimes": per_film[i],
        })
    referenced = set()
    for f in films:
        referenced.update([f["language"], f["certification"]] + f["genres"])
    if any(v > 0 for v in per_format):
        referenced.update(voc["format"][i] for i, v in enumerate(per_format) if v > 0)
    lookup_all = voc["language"] + voc["certification"] + voc["genre"] + voc["format"]

    nman = acc["manager"]
    assignments = [{"manager": "manager-%02d" % m, "screen": (m - 1) // 2 + 1}
                   for m in range(1, nman + 1)]
    bookings = bi
    return {
        "se": se, "screens": screens, "prices": prices, "films": films,
        "assignments": assignments, "examples": examples,
        "counts": {
            "screens": nscr, "seats": total_seats, "categories": len(cats),
            "language": len(voc["language"]), "certification": len(voc["certification"]),
            "genre": len(voc["genre"]), "format": len(voc["format"]),
            "films": nfilms, "movie_genre": sum(len(set(f["genres"])) for f in films),
            "accounts": acc["admin"] + acc["manager"] + acc["customer"],
            "assignments": len(assignments), "showtimes": showtimes,
            "showtime_seat": total_seats * (showtimes // nscr),
            "bookings": bookings, "booked_seats": booked_total,
        },
        "per_screen": per_screen, "per_format": per_format, "past": past,
        "future": future, "owners": owners, "size_hist": size_hist,
        "booked_by_cat": booked_by_cat, "revenue_by_cat": revenue_by_cat,
        "min_booked": min_booked, "full_showtimes": full_showtimes,
        "mean_occ_bp": mean_occ_bp, "lookup_unreferenced": sorted(set(lookup_all) - referenced),
        "lookup_rows": len(lookup_all), "runtimes": runtimes, "spacing": spacing,
        "longest_occupancy": max(runtimes) + sch["changeover_minutes"],
    }


def published_checks(dv):
    """Compare every figure the documents publish with the figure the rules give.

    Returns (rows, failures).  A disagreement fails unless it is recorded in
    known_disagreements; a recorded disagreement that has started agreeing
    fails too, so the record cannot go stale without somebody noticing.
    """
    se = dv["se"]
    pub = se["published_figures"]
    known = dict((k, v) for k, v in se.get("known_disagreements", {}).items()
                 if not k.startswith("$"))
    c = dv["counts"]
    s1 = dv["screens"][0]
    mean_size = "%.3f" % (c["booked_seats"] / float(c["bookings"]))   # display only
    derived = {
        "showtimes": c["showtimes"],
        "showtimes_per_screen": sorted(set(v["showtimes"] for v in dv["per_screen"].values())),
        "showtimes_per_film": sorted(set(f["showtimes"] for f in dv["films"])),
        "past_showtimes": dv["past"], "future_showtimes": dv["future"],
        "total_seats": c["seats"], "showtime_seat_rows": c["showtime_seat"],
        "booked_seats": c["booked_seats"], "bookings": c["bookings"],
        "mean_booking_size_3dp": mean_size,
        "bookings_per_customer_min": min(dv["owners"]),
        "bookings_per_customer_max": max(dv["owners"]),
        "mean_occupancy_percent_2dp": "%d.%02d" % divmod((dv["mean_occ_bp"] + 50) // 100, 100),
        "lookup_rows": dv["lookup_rows"], "accounts": c["accounts"],
        "screen1_bands": [b[1] for b in s1["bands"]],
        "price_paise_by_category": dv["prices"],
        "worked_example_k399_screen": dv["examples"][399]["screen"],
        "worked_example_k399_booked_seats": dv["examples"][399]["booked_seats"],
        "worked_example_k231_booked_seats": dv["examples"][231]["booked_seats"],
        "worked_example_k231_film_index": dv["examples"][231]["film_index"],
        "longest_occupancy_minutes": dv["longest_occupancy"],
        "slot_spacing_minutes": sorted(set(dv["spacing"])),
    }
    rows, failures = [], []
    for key in pub:
        if key.startswith("$") or key == "cite":
            continue
        if key not in derived:
            failures.append("published figure %r has no derivation in generate.py" % key)
            continue
        want, got = pub[key], derived[key]
        if isinstance(got, list) and len(got) == 1 and not isinstance(want, list):
            got = got[0]                 # "every film has 90" -> the set {90}
        agrees = (want == got)
        row = {"figure": key, "published": want, "derived": got, "agrees": agrees}
        if not agrees:
            if key in known:
                row["recorded_disagreement"] = known[key]
            else:
                failures.append("%s: published %r, the rules give %r" % (key, want, got))
        elif key in known:
            failures.append("%s is listed in known_disagreements but now agrees (%r) - "
                            "remove the record" % (key, got))
        rows.append(row)
    for key in known:
        if key not in pub:
            failures.append("known_disagreements names %r, which is not a published figure" % key)
    return rows, failures


def emit_expected_summary(model):
    dv = derive_seed(model)
    se = dv["se"]
    checks, failures = published_checks(dv)
    if failures:
        die("seed expectations disagree with the published figures:" + NL + "  "
            + (NL + "  ").join(failures))
    if dv["lookup_unreferenced"]:
        die("lookup rows no seeded film references: " + ", ".join(dv["lookup_unreferenced"]))
    if dv["min_booked"] < 1 or dv["full_showtimes"]:
        die("a seeded showtime is empty or full - P-XCT-30 forbids both")
    if dv["longest_occupancy"] >= min(dv["spacing"]):
        die("seeded showtimes would overlap: longest occupancy %d >= slot spacing %d"
            % (dv["longest_occupancy"], min(dv["spacing"])))

    model_tables = [t["name"] for t in model["tables"]]
    te = dict((k, v) for k, v in se["table_expectations"].items() if not k.startswith("$"))
    missing = sorted(set(model_tables) - set(te))
    extra = sorted(set(te) - set(model_tables))
    if missing or extra:
        die("seed_expectations.table_expectations must cover exactly the model's tables; "
            "missing %s, unknown %s" % (missing, extra))
    tables = {}
    for name in sorted(model_tables):
        e = te[name]
        r = e["rows"]
        if isinstance(r, str):
            if not r.startswith("derived:") or r[8:] not in dv["counts"]:
                die("table_expectations.%s.rows has unknown derivation %r" % (name, r))
            out = {"rows": dv["counts"][r[8:]], "basis": "derived by generate.py from the rule cited"}
        elif r is None:
            out = {"rows": None, "basis": "UNSPECIFIED - no document states a figure; a gap stays a gap"}
        else:
            out = {"rows": r, "basis": "stated by the document cited"}
        for k in sorted(e):
            if k not in ("rows",):
                out[k] = e[k]
        tables[name] = out

    screens = []
    for s in dv["screens"]:
        ps = dv["per_screen"][s["number"]]
        screens.append({
            "screen": s["number"], "seats": s["seats"], "rows": s["rows"],
            "row_labels": s["row_labels"],
            "bands": [{"category": b[0], "rows": b[1], "row_labels": b[2], "seats": b[3]} for b in s["bands"]],
            "showtimes": ps["showtimes"],
            "showtime_seat_rows": s["seats"] * ps["showtimes"],
            "booked_seats": ps["booked"],
        })
    cats = []
    for c in se["seat_categories"]["rows"]:
        seats = sum(b[3] for s in dv["screens"] for b in s["bands"] if b[0] == c["name"])
        cats.append({"name": c["name"], "uplift_basis_points": c["uplift_basis_points"],
                     "price_paise": dv["prices"][c["name"]], "seats": seats,
                     "booked_seats": dv["booked_by_cat"][c["name"]],
                     "takings_paise": dv["revenue_by_cat"][c["name"]]})
    acc = se["accounts"]
    doc = {
        "_GENERATED": BANNER_JSON,
        "what_this_is": ("What a correct run of scripts/seed.py against an EMPTY, migrated "
                         "database must produce. EXPECTATIONS, not seed data: nothing here "
                         "is a row to insert. Every figure is derived from datamodel.json -> "
                         "seed_expectations and every rule there cites P-XCT-30, P-XCT-32, "
                         "S-XCT-44 or S-XCT-45."),
        "status_law": ("ASSUMED figures (hall sizes OPEN-SCALE-02, category names and uplifts "
                       "OPEN-SEAT-01, the lookup vocabulary, the schedule) are demonstration "
                       "inputs and NEVER harden into a constraint, a default or an application "
                       "limit. PROVISIONAL figures (one cinema SRC-003 C-2, managers SRC-003 C-1) "
                       "reverse with their ruling. null means no document states the figure."),
        "cite": se["cite"],
        "flags": {
            "assumed": [
                "hall sizes and grids - " + se["screens"]["status"],
                "seat categories - " + se["seat_categories"]["status"],
                "base price - " + se["base_price_paise"]["status"],
                "lookup vocabulary - " + se["lookup_vocabulary"]["status"],
                "schedule - " + se["schedule"]["status"],
            ],
            "provisional": [
                "cinema count - " + se["cinema"]["cite"],
                "managers and their mapping - " + se["manager_mapping"]["status"],
            ],
            "one_way_doors_touched": [se["row_letters"]["reserved_rows"]] + [
                u["what"] for u in se["unspecified"] if u["kind"].startswith("ONE-WAY DOOR")],
        },
        "tables": tables,
        "users_by_role": {"admin": acc["admin"], "manager": acc["manager"],
                          "customer": acc["customer"], "guest": "no account (SRC-003 C-1)",
                          "email_domain_default": acc["email_domain_default"],
                          "cite": acc["cite"]},
        "cinema": {"rows": se["cinema"]["count"], "name": se["cinema"]["name"],
                   "timezone": se["cinema"]["timezone"], "cite": se["cinema"]["cite"]},
        "screens": screens,
        "screen_name_pattern": se["screens"]["name_pattern"],
        "seat_categories": cats,
        "price_rule": se["price_rule"]["rule"] + "  (" + se["price_rule"]["cite"] + ")",
        "films": dv["films"],
        "manager_assignments": dv["assignments"],
        "schedule": {
            "showtimes": dv["counts"]["showtimes"],
            "past": dv["past"], "from_today": dv["future"],
            "by_format": dict((se["lookup_vocabulary"]["format"][i], v)
                              for i, v in enumerate(dv["per_format"])),
            "local_starts": se["schedule"]["local_starts"],
            "longest_occupancy_minutes": dv["longest_occupancy"],
            "slot_spacing_minutes": sorted(set(dv["spacing"])),
            "timezone": se["cinema"]["timezone"],
        },
        "bookings": {
            "booked_seats": dv["counts"]["booked_seats"],
            "bookings": dv["counts"]["bookings"],
            "booking_size_histogram": dict((str(k), dv["size_hist"][k])
                                           for k in sorted(dv["size_hist"])),
            "per_customer_min": min(dv["owners"]), "per_customer_max": max(dv["owners"]),
            "payment_state": se["bookings"]["payment_state"],
            "receipt_dispatch_status": se["bookings"]["dispatch_status"],
            "receipt_dispatch_attempts": se["bookings"]["dispatch_attempts"],
            "takings_paise_total": sum(dv["revenue_by_cat"].values()),
            "takings_note": ("DERIVED here and published nowhere: the sum of FR-ADR-038 seat "
                             "prices over the contiguous front-of-house fill. Unverified against "
                             "any implementation - none exists. Integer minor unit."),
        },
        "published_figure_checks": checks,
        "invariants": se["invariants"],
        "unspecified": se["unspecified"],
    }
    text = json.dumps(doc, indent=2, ensure_ascii=False) + NL
    if CARD_DIGITS.search(text):
        die("a card-shaped digit run reached expected_summary.json")
    return text


# ---------------------------------------------------------------- fingerprints
#
# fingerprints.json lets a code session detect drift without re-reading this
# package: SHA-256 of the spec of record and of every generated file, and a
# per-table STRUCTURAL fingerprint an ORM test can recompute.  fingerprints.json
# is excluded from hashing itself - a file cannot contain its own digest.

def sha256_text(text):
    # Line endings are normalised to LF before hashing, so a Windows checkout
    # with autocrlf does not register as drift.  .gitattributes already forces
    # eol=lf; this is the belt to that brace.
    return hashlib.sha256(text.replace("\r\n", "\n").encode("utf-8")).hexdigest()


def table_signature(t):
    """The sorted column/type/constraint list for one table.

    Prose (cite, note, purpose, why, comments) is deliberately excluded: a
    clarified citation is not schema drift and must not fail an ORM test.
    """
    lines = []
    for c in t["columns"]:
        frag = "column %s %s %s" % (c["name"], sqltype(c, t["name"]),
                                    "NULL" if c.get("nullable", True) else "NOT NULL")
        if c.get("identity"):
            frag += " IDENTITY"
        if c.get("default") is not None:
            frag += " DEFAULT %s" % c["default"]
        lines.append(frag)
    pk = t.get("primary_key") or []
    if pk:
        lines.append("primary_key (%s)" % ", ".join(pk))
    for u in t.get("unique", []):
        lines.append("unique %s (%s)%s" % (u["name"], ", ".join(u["columns"]),
                                            (" WHERE %s" % u["where"]) if u.get("where") else ""))
    for ck in t.get("checks", []):
        lines.append("check %s (%s)" % (ck["name"], ck["expression"]))
    for fk in t.get("foreign_keys", []):
        r = fk["references"]
        lines.append("foreign_key %s (%s) -> %s (%s) ON DELETE %s ON UPDATE %s"
                     % (fk["name"], ", ".join(fk["columns"]), r["table"],
                        ", ".join(r["columns"]), fk.get("on_delete", "RESTRICT"),
                        fk.get("on_update", "RESTRICT")))
    for ix in t.get("indexes", []):
        lines.append("index %s%s (%s)%s" % ("UNIQUE " if ix.get("unique") else "", ix["name"],
                                            ", ".join(ix["columns"]),
                                            (" WHERE %s" % ix["where"]) if ix.get("where") else ""))
    return sorted(lines)


def emit_fingerprints(model, model_text, generated):
    tables = {}
    for t in sorted(model["tables"], key=lambda x: x["name"]):
        sig = table_signature(t)
        tables[t["name"]] = {
            "sha256": sha256_text(NL.join(["table " + t["name"]] + sig)),
            "columns": len(t["columns"]),
            "signature": sig,
        }
    roles = []
    for r in model.get("roles", []):
        roles.append("role " + r["name"])
        roles.extend("grant " + g.strip().rstrip(";") for g in r.get("grants", []))
    files = {"datamodel.json": sha256_text(model_text)}
    for name in sorted(generated):
        files[name.replace(os.sep, "/")] = sha256_text(generated[name])
    doc = {
        "_GENERATED": BANNER_JSON,
        "what_this_is": ("Drift detectors for a code session. files: SHA-256 of the spec of "
                         "record and of every generated file. tables: per-table structural "
                         "fingerprints an ORM test can recompute. fingerprints.json is excluded "
                         "from hashing itself."),
        "algorithm": ("sha256 over the UTF-8 bytes with CRLF normalised to LF. A table's sha256 "
                      "is over the line 'table <name>' followed by its signature lines, joined "
                      "by LF, signature lines sorted in byte order. Types are the PostgreSQL "
                      "spellings schema.sql emits. Citations and notes are excluded on purpose: "
                      "prose is not drift."),
        "excluded": ["fingerprints.json - a file cannot carry its own digest",
                     "checks/verify_invariants.sql and every other hand-written file - not generated"],
        "files": files,
        "schema_structure_sha256": sha256_text(NL.join(
            ["%s %s" % (n, tables[n]["sha256"]) for n in sorted(tables)] + roles)),
        "roles_and_grants": roles,
        "tables": tables,
    }
    return json.dumps(doc, indent=2, ensure_ascii=False) + NL


# --------------------------------------------------------------------- driver

PRIMARY = (("schema.sql", emit_schema),
           ("TRACEABILITY.tsv", emit_traceability),
           (SEED_SUMMARY, emit_expected_summary))


def read_model_text(path=MODEL):
    if not os.path.exists(path):
        die("datamodel.json not found at " + path)
    return io.open(path, encoding="utf-8").read()


def derive_all(model, model_text):
    """Every generated file, as {relative path: text}, derived in memory."""
    out = {}
    for name, fn in PRIMARY:
        out[name] = fn(model)
    out[FINGERPRINTS] = emit_fingerprints(model, model_text, out)
    return out


def write_all(model, check, model_text=None):
    if model_text is None:
        model_text = read_model_text()
    drift = []
    for name, want in derive_all(model, model_text).items():
        path = os.path.join(HERE, name)
        have = None
        if os.path.exists(path):
            have = io.open(path, encoding="utf-8", newline="").read()
        if check:
            if have != want:
                drift.append(name.replace(os.sep, "/"))
        else:
            d = os.path.dirname(path)
            if not os.path.isdir(d):
                os.makedirs(d)
            with io.open(path, "w", encoding="utf-8", newline="") as fh:
                fh.write(want)
            print("  wrote %-28s %7d bytes" % (name.replace(os.sep, "/"), len(want.encode("utf-8"))))
    return drift


def _plant_and_check(rel, label):
    """Hand-edit one generated file on disk, prove --check names it, restore."""
    path = os.path.join(HERE, rel)
    original = io.open(path, encoding="utf-8", newline="").read()
    try:
        with io.open(path, "w", encoding="utf-8", newline="") as fh:
            fh.write(original.replace("GENERATED FILE", "GENERATED FIlE", 1)
                     if rel.endswith(".json") else
                     original + NL + "-- a hand edit nobody authorised" + NL)
        went_red = rel.replace(os.sep, "/") in write_all(load(), True)
    finally:
        with io.open(path, "w", encoding="utf-8", newline="") as fh:
            fh.write(original)
    restored = io.open(path, encoding="utf-8", newline="").read() == original
    print("  %-52s -> %s" % (label, "WENT RED (correct)" if went_red
                             else "STAYED GREEN - THE CHECK IS BROKEN"))
    print("  %-52s -> %s" % ("restored " + rel.replace(os.sep, "/"),
                             "verified byte-identical" if restored else "RESTORE FAILED"))
    return went_red and restored


def _expect_die(label, fn):
    """Run fn, which must refuse (die -> SystemExit 1).  Nothing touches disk."""
    err = sys.stderr
    sys.stderr = io.StringIO()
    refused = False
    try:
        fn()
    except SystemExit as e:
        refused = (e.code == 1)
    finally:
        msg = sys.stderr.getvalue().strip().splitlines()
        sys.stderr = err
    print("  %-52s -> %s" % (label, "REFUSED (correct)" if refused
                             else "ACCEPTED - THE CHECK IS BROKEN"))
    if refused and msg:
        print("      %s" % msg[-1].strip()[:110])
    return refused


def selftest():
    """Prove every drift check goes red.  Watched failure, not assumed failure.

    Disk is touched only for GENERATED files, each restored and verified.
    datamodel.json is never written: model defects are planted in memory.
    """
    for name, _fn in PRIMARY + ((FINGERPRINTS, None),):
        if not os.path.exists(os.path.join(HERE, name)):
            die("run generate.py once before --selftest (missing %s)" % name)
    results = []
    results.append(_plant_and_check("schema.sql", "planted a hand-edit in schema.sql"))
    results.append(_plant_and_check(SEED_SUMMARY, "planted a hand-edit in seed/expected_summary.json"))
    results.append(_plant_and_check(FINGERPRINTS, "planted a hand-edit in fingerprints.json"))

    base_text = read_model_text()
    base = json.loads(base_text)

    # A model edit nobody regenerated: the datamodel.json digest must move.
    m = json.loads(base_text)
    drift = write_all(m, True, model_text=base_text + " ")
    ok = drift == [FINGERPRINTS]
    print("  %-52s -> %s" % ("model bytes changed, nothing regenerated",
                             "WENT RED on fingerprints.json only (correct)" if ok
                             else "WRONG RESULT %r" % drift))
    results.append(ok)

    # A structural change must move exactly that table's fingerprint.
    m = json.loads(base_text)
    before = json.loads(emit_fingerprints(base, base_text, {}))["tables"]
    for t in m["tables"]:
        if t["name"] == "booking_seat":
            for c in t["columns"]:
                if c["name"] == "price_paise":
                    c["type"] = "integer"
    after = json.loads(emit_fingerprints(m, base_text, {}))["tables"]
    moved = sorted(n for n in before if before[n]["sha256"] != after[n]["sha256"])
    ok = moved == ["booking_seat"]
    print("  %-52s -> %s" % ("booking_seat.price_paise bigint -> integer",
                             "only booking_seat's fingerprint moved (correct)" if ok
                             else "WRONG TABLES MOVED %r" % moved))
    results.append(ok)

    # Prose is not drift: a changed citation must move no table fingerprint.
    m = json.loads(base_text)
    m["tables"][0]["columns"][0]["cite"] = "a reworded citation"
    after = json.loads(emit_fingerprints(m, base_text, {}))["tables"]
    moved = sorted(n for n in before if before[n]["sha256"] != after[n]["sha256"])
    ok = not moved
    print("  %-52s -> %s" % ("reworded a citation only",
                             "no table fingerprint moved (correct)" if ok
                             else "PROSE REGISTERED AS DRIFT %r" % moved))
    results.append(ok)

    def with_seed(mutate):
        m = json.loads(base_text)
        mutate(m["seed_expectations"])
        return lambda: emit_expected_summary(m)

    results.append(_expect_die("a published figure the rules do not give (11004)",
                               with_seed(lambda se: se["published_figures"].__setitem__("bookings", 11004))))
    results.append(_expect_die("a recorded disagreement that now agrees",
                               with_seed(lambda se: se["published_figures"].__setitem__(
                                   "worked_example_k399_booked_seats", 72))))
    results.append(_expect_die("a hall whose rows do not hold its seats",
                               with_seed(lambda se: se["screens"]["layouts"][0]["rows"][0].__setitem__(2, 99))))
    results.append(_expect_die("a table left out of table_expectations",
                               with_seed(lambda se: se["table_expectations"].pop("booking"))))
    results.append(_expect_die("a card-shaped number in an expectation",
                               with_seed(lambda se: se["unspecified"].append(
                                   {"what": "4" + "1" * 15, "cite": "x", "kind": "x"}))))

    still_green = not write_all(load(), True)
    print("  %-52s -> %s" % ("--check after every restore",
                             "green (correct)" if still_green else "STILL RED - RESTORE INCOMPLETE"))
    results.append(still_green)
    ok = all(results)
    print("VERDICT: %s" % (("PASS - %d of %d checks: every planted defect went red, "
                            "every restore verified." % (sum(results), len(results)))
                           if ok else "FAIL - %d of %d checks passed"
                           % (sum(results), len(results))))
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
        print("PASS - every generated file matches datamodel.json exactly"
              " (%d files)." % (len(PRIMARY) + 1))
        return 0
    write_all(model, False)
    print("PASS - regenerated from datamodel.json.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

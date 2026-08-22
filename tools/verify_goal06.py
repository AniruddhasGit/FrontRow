#!/usr/bin/env python
"""GOAL_06 verification - re-derives every figure in docs/11 Journeys/JOURNEY_INDEX.md.

Run from the repo root:

    py tools/verify_goal06.py              print the report; exit 0 only if every check passes
    py tools/verify_goal06.py --selftest   red-proof each check by planting a known failure

WHY THIS EXISTS. `JOURNEY_INDEX.md` publishes counts - 140 of 163 P-rows touched, 242 steps,
64 defects. A count in prose that nothing recomputes decays; this repository has caught that
failure five times (`GOTCHAS.md`, "Checks that measure less than they appear to"). Every figure
this prints is derived from a committed file. Nothing is typed and nothing is passed in.

WHAT IT READS - committed artefacts only, never a scratch directory:
  docs/03 PRD/sections/*.md        the universe of P-rows
  docs/11 Journeys/*_JOURNEY.md    the step tables: seams, and the P-rows each step cites
  docs/11 Journeys/DEFECTS_FOUND.tsv   the merged defect register
  CONSTITUTION.md, docs/00 SourceOfTruth/   to resolve every OPEN- id a defect cites

The lane-scoped TSVs the five journey agents wrote are deliberately NOT inputs. They were
scratch; the documents in the tree are the record.
"""
import io
import os
import re
import sys
import glob

JOURNEYS = os.path.join("docs", "11 Journeys")
SECTIONS = os.path.join("docs", "03 PRD", "sections")
DEFECTS = os.path.join(JOURNEYS, "DEFECTS_FOUND.tsv")

P_ROW = re.compile(r"\bP-[A-Z]+-[0-9]+\b")
OPEN_ID = re.compile(r"\bOPEN-[A-Z0-9]+-[0-9]+\b")
# Step rows are numbered "1", "1.1", "2.3a" - NOT a bare integer. Requiring ^[0-9]+$ here
# matched nothing at all and the seam check passed by measuring an empty set, which is why
# the zero-step guard in check_seams() exists.
STEP_NO = re.compile(r"^[0-9]+(\.[0-9]+)*[a-z]?$")

HEADER = ["DefectID", "Lane", "PRDSection", "Anchor", "Kind", "Severity",
          "Seam", "Statement", "WhyItMatters", "Disposition"]
KINDS = {"gap", "contradiction", "unhandled-edge"}
SEVERITIES = ["blocks-code", "ambiguous", "cosmetic"]        # worst first; order is load-bearing
DEFECT_ID = re.compile(r"^J-(CUS|GST|ENT|MGR|ADM)-[0-9]{2}$")
DISPOSITION = re.compile(r"^(PRD-fix|new-Art-X-row|already-open:OPEN-[A-Z0-9]+-[0-9]+)$")

# The lane is keyed off the VALIDATED DefectID prefix, never off the free-text Lane cell.
# The five lanes wrote five different conventions in that cell (ADM, CUSTOMER, ENT, GUEST,
# MANAGER), so grouping on it reported zero for every lane while the total said 64 - a
# zero-detector that reports zero for everything cannot detect a real zero.
PREFIX_LANE = {"CUS": "customer", "GST": "guest", "ENT": "entry",
               "MGR": "manager", "ADM": "admin"}
LANES = ["customer", "guest", "entry", "manager", "admin"]

# Column positions in a step table. Anchored by the header row, checked, never assumed.
STEP_COLUMNS = ["#", "Surface", "State entering", "Action", "Seam crossed", "Seam type",
                "What they leave with", "P-rows", "Defects"]
COL_SEAM, COL_SEAMTYPE, COL_PROWS = 4, 5, 7

failures = []


def fail(rule, msg):
    failures.append((rule, msg))


def read(path):
    with io.open(path, encoding="utf-8") as fh:
        return fh.read().replace(chr(13) + chr(10), chr(10))


def journey_files():
    return sorted(glob.glob(os.path.join(JOURNEYS, "*_JOURNEY.md")))


def universe():
    """Every P-row that exists, harvested from the PRD section files."""
    ids = set()
    for f in sorted(glob.glob(os.path.join(SECTIONS, "*.md"))):
        ids |= set(P_ROW.findall(read(f)))
    if not ids:
        fail("universe", "no P-rows found in %s - the harvest is blind" % SECTIONS)
    return ids


def check_headers():
    """The column order this script indexes must be the column order the documents use.
    A silently reordered table would make every seam and coverage figure below wrong."""
    for f in journey_files():
        for line in read(f).split(chr(10)):
            t = line.strip()
            if not t.startswith("|") or "Seam type" not in t:
                continue
            cells = [c.strip() for c in t.strip("|").split("|")]
            if cells != STEP_COLUMNS:
                fail("headers", "%s has a step table whose columns are %r, not %r"
                     % (os.path.basename(f), cells, STEP_COLUMNS))
            break


def walk_steps():
    """Yield (file, step_no, cells) for every step row in every journey."""
    for f in journey_files():
        for line in read(f).split(chr(10)):
            t = line.strip()
            if not t.startswith("|"):
                continue
            cells = [c.strip() for c in t.strip("|").split("|")]
            if len(cells) < len(STEP_COLUMNS) or not STEP_NO.match(cells[0]):
                continue
            yield f, cells[0], cells


def check_seams():
    """Every step names the seam it crosses. A blank seam, or one reading 'none', is a step
    that measures nothing - a walk padded with seamless steps claims coverage it never had."""
    total = 0
    by_type = {}
    for f, no, cells in walk_steps():
        total += 1
        seam = cells[COL_SEAM]
        seamtype = cells[COL_SEAMTYPE].strip("`* ").lower()
        by_type[seamtype] = by_type.get(seamtype, 0) + 1
        if not seam or seam in ("-", "n/a") or seam.lower().startswith("none"):
            fail("seams", "%s step %s has no seam" % (os.path.basename(f), no))
        if seamtype.startswith("none") or not seamtype:
            fail("seams", "%s step %s has no seam type" % (os.path.basename(f), no))
    for f in journey_files():
        if not re.search(r"^\|\s*[0-9]+(\.[0-9]+)*[a-z]?\s*\|", read(f), re.M):
            fail("seams", "%s has no parseable step rows - the checker is blind to it"
                 % os.path.basename(f))
    if journey_files() and total == 0:
        fail("seams", "journey files exist but zero step rows parsed - a vacuous pass")
    return total, by_type


def coverage(uni):
    """Coverage is read from the P-rows column of the step tables themselves, so the figure
    measures the documents rather than a companion file that could drift from them."""
    cited = set()
    per_file = {}
    for f, _no, cells in walk_steps():
        ids = set(P_ROW.findall(cells[COL_PROWS]))
        bogus = ids - uni
        if bogus:
            fail("coverage", "%s cites %d P-row(s) that do not exist: %s"
                 % (os.path.basename(f), len(bogus), " ".join(sorted(bogus)[:5])))
        per_file[f] = per_file.get(f, set()) | (ids & uni)
        cited |= ids & uni
    return cited, per_file


def known_open_ids():
    ids = set()
    for p in ["CONSTITUTION.md"] + glob.glob(os.path.join("docs", "00 SourceOfTruth", "*.md")):
        if os.path.exists(p):
            ids |= set(OPEN_ID.findall(read(p)))
    return ids


def load_defects():
    if not os.path.exists(DEFECTS):
        fail("defects", "%s does not exist" % DEFECTS)
        return []
    lines = [l for l in read(DEFECTS).split(chr(10)) if l.strip()]
    if not lines:
        fail("defects", "%s is empty" % DEFECTS)
        return []
    head = lines[0].split(chr(9))
    if head != HEADER:
        fail("defects", "header is %r, expected %r" % (head, HEADER))
        return []
    rows, seen, known = [], set(), known_open_ids()
    for n, line in enumerate(lines[1:], start=2):
        cells = line.split(chr(9))
        if len(cells) != len(HEADER):
            fail("defects", "line %d has %d cells, expected %d"
                 % (n, len(cells), len(HEADER)))
            continue
        rec = dict(zip(HEADER, cells))
        did = rec["DefectID"]
        if not DEFECT_ID.match(did):
            fail("defects", "line %d: bad DefectID %r" % (n, did))
        if did in seen:
            fail("defects", "duplicate DefectID %r" % did)
        seen.add(did)
        if rec["Kind"] not in KINDS:
            fail("defects", "%s: Kind %r not in %s" % (did, rec["Kind"], sorted(KINDS)))
        if rec["Severity"] not in SEVERITIES:
            fail("defects", "%s: Severity %r not in %s" % (did, rec["Severity"], SEVERITIES))
        if not DISPOSITION.match(rec["Disposition"]):
            fail("defects", "%s: Disposition %r malformed" % (did, rec["Disposition"]))
        for col in ("Statement", "WhyItMatters"):
            if not rec[col].strip():
                fail("defects", "%s: %s is empty" % (did, col))
        # An OPEN- token is a CLAIM that the row exists. Spelling one that does not is a
        # defect this repository has already committed once, in S8.7.
        if rec["Disposition"].startswith("already-open:"):
            oid = rec["Disposition"].split(":", 1)[1]
            if oid not in known:
                fail("open-ids", "%s cites %s, which is not a filed Article X row" % (did, oid))
        rows.append(rec)
    return rows


def lane_of(rec):
    return PREFIX_LANE.get(rec["DefectID"].split("-")[1], "?")


def report():
    del failures[:]
    check_headers()
    uni = universe()
    steps, by_type = check_seams()
    cited, per_file = coverage(uni)
    rows = load_defects()

    print("GOAL_06 verification - every figure below is derived, none is typed")
    print("=" * 74)
    print()
    print("P-row coverage")
    print("  universe (P-rows in %s) : %d" % (SECTIONS, len(uni)))
    print("  touched by at least one journey step        : %d" % len(cited))
    print("  UNTOUCHED                                   : %d" % (len(uni) - len(cited)))
    for f in sorted(per_file):
        print("    %-26s %3d" % (os.path.basename(f), len(per_file[f])))
    missing = sorted(uni - cited)
    if missing:
        print("  untouched rows (JOURNEY_INDEX.md must give a reason for each):")
        for i in range(0, len(missing), 8):
            print("    " + " ".join(missing[i:i + 8]))
    print()
    print("Journey steps")
    print("  step rows            : %d" % steps)
    for k in sorted(by_type, key=lambda x: -by_type[x]):
        print("    %-10s %3d" % (k, by_type[k]))
    print()
    print("Defects (worst severity first)")
    print("  total : %d" % len(rows))
    for sev in SEVERITIES:
        print("    %-14s %3d" % (sev, len([r for r in rows if r["Severity"] == sev])))
    for kind in sorted(KINDS):
        print("    %-16s %3d" % (kind, len([r for r in rows if r["Kind"] == kind])))
    print()
    by_lane = {}
    for r in rows:
        by_lane.setdefault(lane_of(r), []).append(r)
    print("  per lane:")
    for lane in LANES:
        n = len(by_lane.get(lane, []))
        flag = ""
        if n == 0:
            flag = "   <-- ZERO"
            fail("zero-lane", "lane %s filed no defects; GOAL_06 requires a written "
                              "explanation of why zero is believable" % lane)
        print("    %-9s %3d%s" % (lane, n, flag))
    print()
    if failures:
        print("FAIL - %d problem(s):" % len(failures))
        for rule, msg in failures:
            print("  [%s] %s" % (rule, msg))
        return 1
    print("PASS - the journeys, the defect register and the PRD agree.")
    print("       This is the cheap layer only. It cannot tell whether a walk is TRUE,")
    print("       only whether it is internally consistent and completely accounted for.")
    return 0


def selftest():
    """Red-proof each check by planting a known failure. A check nobody has watched fail
    is decoration - GOTCHAS.md records five occasions this repository proved that."""
    plants = [
        ("coverage", JOURNEYS + "/GUEST_JOURNEY.md",
         lambda s: s.replace("| `P-BRW-01`", "| `P-NOPE-99`", 1),
         "a step citing a P-row that does not exist"),
        ("headers", JOURNEYS + "/GUEST_JOURNEY.md",
         lambda s: s.replace("| Seam crossed | Seam type |", "| Seam type | Seam crossed |", 1),
         "a step table with two columns swapped"),
        ("defects", DEFECTS,
         lambda s: s.replace(chr(9), "|", 1),
         "a defect header with a broken column separator"),
        ("open-ids", DEFECTS,
         lambda s: s.replace("already-open:OPEN-", "already-open:OPEN-NOTAROW", 1),
         "a defect citing an Article X row that is not filed"),
    ]
    ok = 0
    for rule, path, mutate, why in plants:
        if not os.path.exists(path):
            print("  SKIP  %-10s %s (%s missing)" % (rule, why, path))
            continue
        backup = read(path)
        try:
            with io.open(path, "w", encoding="utf-8", newline="") as fh:
                fh.write(mutate(backup))
            del failures[:]
            check_headers()
            u = universe()
            check_seams()
            coverage(u)
            load_defects()
            hit = any(r == rule for r, _ in failures)
            print("  %-5s %-10s planted: %s" % ("ok" if hit else "MISS", rule, why))
            ok += 1 if hit else 0
        finally:
            with io.open(path, "w", encoding="utf-8", newline="") as fh:
                fh.write(backup)
    print()
    print("%d of %d checks red-proofed" % (ok, len(plants)))
    return 0 if ok == len(plants) else 1


if __name__ == "__main__":
    if not os.path.isdir(JOURNEYS):
        sys.stderr.write("run this from the repository root\n")
        sys.exit(2)
    sys.exit(selftest() if "--selftest" in sys.argv else report())

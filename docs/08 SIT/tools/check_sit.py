"""check_sit.py - the GOAL_10 consistency check for docs/08 SIT/ (compressed per SRC-004 R-1).

    py "docs/08 SIT/tools/check_sit.py"             run every check, regenerate COVERAGE.tsv
    py "docs/08 SIT/tools/check_sit.py" --selftest  plant one violation per check, prove each fires

Exit 0 = every check passed. Exit 1 = at least one failed. Exit 2 = the tool itself errored.
Standard library only. Reads the Bible, never writes it.
"""
import copy
import csv
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_sit as B  # noqa: E402

WALL = re.compile(r"(?i)\bnow\b|now\(|\btoday\b|current_date|current_timestamp|localtimestamp|"
                  r"datetime\.now|utcnow|time\.time|date\.today|Date\.now|wall[- ]clock|\bsleep|"
                  r"\b2026-10-18\b")
AUTHORED = ["Precondition", "Steps", "DataFixture", "ClockInstant"]
# For the verbatim Bible/journey text a bare English 'now' ("stored ids now sold") is not a clock
# read, so the verbatim check drops it; a hit is also accepted when the clause negates it.
WALL_VERBATIM = re.compile(WALL.pattern.replace(r"\bnow\b|", ""), re.I)
NEGATED = re.compile(r"(?i)\b(no|not|never|without|zero)\b[^.;]{0,40}$")


def load():
    unit = B.read_tsv(os.path.join(B.SIT, "SIT_TestCases.tsv"))
    jour = B.read_tsv(os.path.join(B.SIT, "SIT_JourneyCases.tsv"))
    defs = B.read_tsv(os.path.join(B.SIT, "BIBLE_DEFECTS_SIT.tsv"))
    fx = B.read_tsv(os.path.join(B.SIT, "FIXTURES.tsv"))
    with open(B.BIBLE, encoding="utf-8", newline="") as f:
        bible = [r for r in csv.DictReader(f) if r["Type"] == "Story"]
    walks = 0
    for fn in os.listdir(B.JOURNEYS):
        if fn.endswith("_JOURNEY.md"):
            with open(os.path.join(B.JOURNEYS, fn), encoding="utf-8") as f:
                walks += sum(1 for ln in f if ln.startswith("| # |"))
    return dict(unit=unit, jour=jour, defs=defs, fx=fx, bible=bible, walks=walks, pidx=B.prd_index())


def checks(d, out):
    res = []

    def rule(key, ok, msg, detail=()):
        res.append((key, ok, msg, list(detail)))

    crit = [r for r in d["bible"] if r["AcceptanceCriteria"].strip()]
    rule("count-equal", len(crit) == len(d["unit"]),
         "acceptance criteria in the Bible = %d · unit cases = %d" % (len(crit), len(d["unit"])))

    by = {}
    for c in d["unit"]:
        by.setdefault(c["CriterionRef"], []).append(c["CaseID"])
    refs = {r["ID"] + "/AC" for r in crit}
    nocase = sorted(refs - set(by))
    multi = sorted(k for k, v in by.items() if len(v) > 1)
    orphan = sorted(k for k in by if k not in refs)
    rule("coverage-1to1", not (nocase or multi or orphan),
         "criteria with no case = %d · criteria with >1 case = %d · cases with no criterion = %d"
         % (len(nocase), len(multi), len(orphan)), nocase + multi + orphan)
    if out:
        cov = []
        cases = {c["CriterionRef"]: c for c in d["unit"]}
        for r in crit:
            k = r["ID"] + "/AC"
            c = cases.get(k, {})
            cov.append(dict(BibleStoryID=r["ID"], CriterionRef=k, Phase=r["Milestone"],
                            CaseIDs=" ".join(by.get(k, [])) or "NONE", CaseCount=len(by.get(k, [])),
                            Runnable=c.get("Runnable", "-"), DefectRef=c.get("DefectRef", "-")))
        for k in orphan:
            cov.append(dict(BibleStoryID="NONE", CriterionRef=k, Phase="-", CaseIDs=" ".join(by[k]),
                            CaseCount=len(by[k]), Runnable="-", DefectRef="-"))
        B.write_tsv(os.path.join(B.SIT, "COVERAGE.tsv"),
                    ["BibleStoryID", "CriterionRef", "Phase", "CaseIDs", "CaseCount", "Runnable", "DefectRef"], cov)

    empty = [c["CaseID"] + ":" + k for c in d["unit"] + d["jour"]
             for k in ("Precondition", "DataFixture", "ExpectedResult") if not c.get(k, "").strip()]
    rule("no-empty-fields", not empty, "cases with an empty Precondition, DataFixture or ExpectedResult = %d"
         % len(empty), empty)

    hits = [c["CaseID"] + ":" + k + ":" + m.group(0) for c in d["unit"] + d["jour"] for k in AUTHORED
            for m in WALL.finditer(c.get(k, ""))]
    rule("no-wall-clock-authored", not hits,
         "wall-clock / current-date references in the case-authored columns (%s) = %d"
         % (", ".join(AUTHORED), len(hits)), hits)
    # The Bible text copied verbatim into ExpectedResult: quoted search patterns are bans, not
    # reads. What remains after stripping them must be relative to the injected clock.
    resid = []
    for c in d["unit"] + d["jour"]:
        for cl in re.split(r" (?=C\d+: )| (?=J\d+(?:\.\d+)?: )", c["ExpectedResult"]):
            sq = B.strip_quoted(cl)
            for m in WALL_VERBATIM.finditer(sq):
                if NEGATED.search(sq[:m.start()]):
                    continue
                if not re.search(r"(?i)injected|clock|ClockInstant|T0|\bT\b|date=|2026-08-", cl):
                    resid.append(c["CaseID"] + ":" + m.group(0) + ": " + cl[:120])
    rule("no-wall-clock-verbatim", not resid,
         "wall-clock references in ExpectedResult not anchored to the injected clock = %d" % len(resid), resid)

    dang = []
    for c in d["unit"] + d["jour"]:
        for p, loc in re.findall(r"(P-[A-Z]{3}-\d{2})\(([^)]*)\)", c["PRDRef"]):
            if p not in d["pidx"] or loc == "UNRESOLVED":
                dang.append(c["CaseID"] + ":" + p)
        if c in d["unit"] and not re.search(r"P-[A-Z]{3}-\d{2}\(", c["PRDRef"]):
            dang.append(c["CaseID"] + ": no PRDRef")
    rule("prdref-resolves", not dang, "dangling PRDRef = %d (P-row headings indexed: %d)"
         % (len(dang), len(d["pidx"])), dang)

    st = [c for c in d["unit"] if c["BibleStoryID"] == "S-XCT-01"]
    need = ["scripts/stress_seats.py", "--seat 312", "--n 50", "exactly 1 HTTP 201", "exactly 49 HTTP 409"]
    miss = [n for n in need if not st or n not in st[0]["ExpectedResult"]]
    rule("stress-case", bool(st) and not miss,
         "zero-double-booking case %s names script, seat, concurrency and split; missing = %s"
         % (st[0]["CaseID"] if st else "ABSENT", miss or "none"), miss)

    ids = {x["DefectID"] for x in d["defs"]}
    bad = [c["CaseID"] for c in d["unit"] if c["Runnable"] == "no" and
           (c["DefectRef"] in ("", "-") or any(t not in ids for t in c["DefectRef"].split()))]
    bad += [x["DefectID"] for x in d["defs"] if x["CriterionRef"] not in by]
    rule("unrunnable-filed", not bad,
         "unrunnable cases without a resolving defect, or defects naming no case = %d" % len(bad), bad)

    fxid = {f["FixtureID"] for f in d["fx"]}
    badfx = [c["CaseID"] + ":" + t for c in d["unit"] + d["jour"]
             for t in re.findall(r"\bFX-[A-Z0-9-]+\b", c["DataFixture"]) if t not in fxid]
    rule("fixture-resolves", not badfx, "DataFixture ids not in FIXTURES.tsv = %d" % len(badfx), badfx)

    noseam = [j["CaseID"] for j in d["jour"] if not j["SeamTypes"].strip()]
    rule("journey-1to1", len(d["jour"]) == d["walks"] and not noseam,
         "journey step tables = %d · journey cases = %d · cases with no seam = %d"
         % (d["walks"], len(d["jour"]), len(noseam)), noseam)

    lab = [c["CaseID"] for c in d["unit"] + d["jour"] if c.get("Label") != B.LABEL]
    rule("labelled", not lab, "cases missing the label '%s' = %d" % (B.LABEL, len(lab)), lab)
    return res


def fresh(d):
    """Generated files must equal a fresh generation - nobody hand-edits them."""
    defs = []
    cases, _ = B.unit_cases(defs)
    j = B.journey_cases()
    norm = lambda rows, cols: [[B.clean(str(r.get(c, ""))) for c in cols] for r in rows]  # noqa: E731
    return (norm(cases, B.UNIT_COLS) == norm(d["unit"], B.UNIT_COLS) and
            norm(j, B.JOURNEY_COLS) == norm(d["jour"], B.JOURNEY_COLS) and
            norm(defs, B.DEFECT_COLS) == norm(d["defs"], B.DEFECT_COLS))


def report(res):
    for k, ok, msg, det in res:
        print("%s  %-24s %s" % ("PASS" if ok else "FAIL", k, msg))
        for x in det[:15]:
            print("        - " + x)
    nf = sum(not ok for _, ok, _, _ in res)
    print("\nchecks: %d · %d pass · %d fail" % (len(res), len(res) - nf, nf))
    return nf


def selftest(d):
    plants = {
        "count-equal": lambda x: x["unit"].pop(),
        "coverage-1to1": lambda x: x["unit"].append(dict(x["unit"][0], CaseID="SIT-DUP")),
        "no-empty-fields": lambda x: x["unit"][3].__setitem__("Precondition", ""),
        "no-wall-clock-authored": lambda x: x["unit"][5].__setitem__("Steps", x["unit"][5]["Steps"] + " datetime.now()"),
        "no-wall-clock-verbatim": lambda x: x["unit"][6].__setitem__("ExpectedResult", "C1: wait until today ends"),
        "prdref-resolves": lambda x: x["unit"][7].__setitem__("PRDRef", "P-ZZZ-99(E9.md:1)"),
        "stress-case": lambda x: [c.__setitem__("ExpectedResult", c["ExpectedResult"].replace("--n 50", "--n 5"))
                                  for c in x["unit"] if c["BibleStoryID"] == "S-XCT-01"],
        "unrunnable-filed": lambda x: x["unit"][9].update(Runnable="no", DefectRef="-"),
        "fixture-resolves": lambda x: x["unit"][10].__setitem__("DataFixture", "FX-NOPE"),
        "journey-1to1": lambda x: x["jour"].pop(),
        "labelled": lambda x: x["jour"][0].__setitem__("Label", "full depth"),
    }
    fired = 0
    for key, plant in plants.items():
        x = copy.deepcopy(d)
        plant(x)
        res = {k: ok for k, ok, _, _ in checks(x, out=False)}
        red = res.get(key) is False
        fired += red
        print("%s  %-24s planted violation %s" % ("RED " if red else "MISS", key, "fired" if red else "DID NOT FIRE"))
    print("\nselftest: %d of %d planted violations went red" % (fired, len(plants)))
    return 0 if fired == len(plants) else 1


def main():
    try:
        d = load()
    except Exception as e:  # pragma: no cover
        print("ERROR", e)
        return 2
    if "--selftest" in sys.argv:
        return selftest(d)
    res = checks(d, out=True)
    res.append(("generated-fresh", fresh(d), "SIT_TestCases / SIT_JourneyCases / BIBLE_DEFECTS_SIT equal a "
                "fresh run of build_sit.py", []))
    nf = report(res)
    print("\nBIBLE DEFECTS FILED (criteria that cannot be, or cannot fully be, run as written):")
    for x in d["defs"]:
        print("  %s %s %-34s blocks=%s" % (x["DefectID"], x["BibleStoryID"], x["Class"], x["Blocks"]))
    print("  total %d · blocking %d" % (len(d["defs"]), sum(x["Blocks"] == "yes" for x in d["defs"])))
    return 1 if nf else 0


if __name__ == "__main__":
    sys.exit(main())

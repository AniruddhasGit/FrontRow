"""Consistency check for docs/09 NegativeTesting (GOAL_11, compressed per SRC-004 R-1).

Run:  py "docs/09 NegativeTesting/check_negative.py"
Exits 0 only when every check passes. Prints the counts the GOAL_11 Definition of Done asks for.
It checks the documents against each other; it does not and cannot check that a case is a GOOD
case. That is a reviewer's job, and no independent reviewer has read these files yet.
"""
import csv
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CASES = os.path.join(HERE, "SIT_NegativeCases.tsv")
COVER = os.path.join(HERE, "OVERSELL_COVERAGE.tsv")
PLAN = os.path.join(HERE, "CONCURRENCY_ATTACK_PLAN.md")

CASE_COLS = ["CaseID", "Family", "Severity", "Title", "Attack", "DefectItWouldCatch",
             "ExpectedResult", "CrossRole", "PositiveHalf", "Invariant", "SourceRef",
             "BibleRef", "OversellPaths", "Status"]
COVER_COLS = ["PathID", "Path", "Entry", "HowItMarksSold", "Guard", "Sev1Cases", "AllCases", "Status"]
FAMILIES = {"CONCURRENCY": "CON", "MONEY": "MON", "AUTHZ": "AUZ", "DATA": "DAT",
            "DEPENDENCY": "DEP", "ABUSE": "ABU", "LEAK": "LEK", "TEST-HYGIENE": "TST"}
NA = "n/a - not a cross-role case"
POSITIVE = re.compile(r"greater than 0|non-empty|non-zero|at least 1|count greater", re.I)
# A positive half must also say the permitted actor SUCCEEDED, not only name a figure.
POS_STATUS = re.compile(r"\b(20[0-9]|2xx)\b")
# A 13-19 digit run is card-shaped, written solid or with a single space or dash between digits
# (cards are printed in groups: 4-4-4-4, 4-6-5). No file in this folder may carry one (CLAUDE.md).
CARD_RUN = re.compile(r"(?<!\d)\d(?:[ -]?\d){12,18}(?!\d)")

# GOAL_11: severity one is reserved for these five harms. Every S1 case names one in Invariant.
S1_HARMS = {
    "seat-never-sold-twice": "a seat sold twice",
    "never-charged-twice": "a customer charged twice",
    "never-charged-without-seat": "a customer charged and not given a seat",
    "own-data-only": "one customer seeing another's booking or payment data",
    "revenue-manager-only": "a non-manager reading a cinema's revenue",
}

# The topics the task brief named, each mapped to the cases that answer it and a pattern that the
# case's Attack and ExpectedResult (not its Title) must still match.
# A deleted case fails; so does a case rewritten off its topic.
REQUIRED_TOPICS = {
    "double sale": (["NC-CON-01", "NC-CON-02", "NC-CON-03"], r"booking_seat"),
    # The non-owner presents tA, is refused, nothing it touched changed, and the owner still books.
    "lock token theft": (["NC-CON-09", "NC-CON-08"],
                         r"(?=.*\{tA\})(?=.*(HOLD_NOT_OWNED|no-ops))(?=.*(no key is touched|returns tB))(?=.*\b201\b)"),
    "Redis down returns error, not DB fallback": (["NC-DEP-01", "NC-DEP-02"], r"Redis.*503 DEPENDENCY_UNAVAILABLE"),
    "idempotency replay": (["NC-CON-05", "NC-MON-01", "NC-MON-12", "NC-MON-13"], r"Idempotency[-_]Key|key K"),
    "more than 10 seats": (["NC-MON-07"], r"\b11\b.*exceeds 10"),
    # A denial (or an empty scope) for the other screen AND the figures that prove it is not empty for all.
    "manager cross-scope, both halves": (["NC-AUZ-03", "NC-AUZ-05"],
                                         r"(?=.*manager)(?=.*(403 FORBIDDEN|scope_empty true))(?=.*\b350000\b)(?=.*(\b250000\b|takings_paise 0\b))"),
    "float money": (["NC-MON-09"], r"float"),
    "card data": (["NC-MON-11"], r"card.*cvv.*Luhn"),
    "wall clock in tests": (["NC-TST-01"], r"datetime\.now|faketime"),
    "SIGTERM mid-request": (["NC-DEP-10"], r"SIGTERM"),
    "reset token leakage into logs or DB (SRC-004 R-3)": (["NC-LEK-01", "NC-LEK-02"], r"(?=.*token)(?=.*(column|stdout))"),
    "lower-case row label rejected (SRC-004 R-4)": (["NC-DAT-06"], r"'c'"),
    "reference check-character rejection (SRC-004 R-5)": (["NC-DAT-09", "NC-DAT-10"], r"check character"),
    "hold TTL never extended (FR-ADR-027)": (["NC-CON-20"], r"never extended"),
    "failed reset send not retried (SRC-004 JC-R6-01)": (["NC-LEK-08"], r"not retried.*0 database columns.*0 captured log lines"),
    "non-ASCII row label rejected (SRC-004 JC-R6-03)": (["NC-DAT-12"], r"422.*non-ASCII"),
    "reset ?token= not in nginx or ALB access logs": (["NC-LEK-09"], r"nginx.*ALB.*access log"),
    "partial win releases only what this request won": (["NC-CON-22"], r"already mine.*GET lock:seat:41:312 still returns tA"),
}


def read(path, cols):
    with open(path, encoding="utf-8", newline="") as f:
        r = csv.reader(f, delimiter="\t")
        header = next(r)
        rows = [dict(zip(header, line)) for line in r]
        widths = {len(line) for line in csv.reader(open(path, encoding="utf-8", newline=""), delimiter="\t")}
    return header, rows, widths


def main():
    fails = []
    for p in (CASES, COVER, PLAN):
        if not os.path.exists(p):
            print(f"FAIL  missing file {os.path.basename(p)}")
            return 1

    h, cases, w = read(CASES, CASE_COLS)
    if h != CASE_COLS:
        fails.append(f"case header differs: {h}")
    if w != {len(CASE_COLS)}:
        fails.append(f"case rows have widths {sorted(w)}, expected {len(CASE_COLS)}")
    hc, cover, wc = read(COVER, COVER_COLS)
    if hc != COVER_COLS:
        fails.append(f"coverage header differs: {hc}")
    if wc != {len(COVER_COLS)}:
        fails.append(f"coverage rows have widths {sorted(wc)}, expected {len(COVER_COLS)}")

    empty = [(r.get("CaseID", "?"), c) for r in cases for c in CASE_COLS if not (r.get(c) or "").strip()]
    empty += [(r.get("PathID", "?"), c) for r in cover for c in COVER_COLS if not (r.get(c) or "").strip()]

    ids = [r["CaseID"] for r in cases]
    dup = sorted({i for i in ids if ids.count(i) > 1})
    badfam = [r["CaseID"] for r in cases
              if r["Family"] not in FAMILIES or not r["CaseID"].startswith(f"NC-{FAMILIES.get(r['Family'], '?')}-")]
    badsev = [r["CaseID"] for r in cases if r["Severity"] not in ("S1", "S2", "S3")]

    cross = [r for r in cases if r["CrossRole"] == "Y"]
    badcross = [r["CaseID"] for r in cases if r["CrossRole"] not in ("Y", "N")]
    missing_pos = [r["CaseID"] for r in cross if r["PositiveHalf"] == NA or not POSITIVE.search(r["PositiveHalf"])
                   or not POS_STATUS.search(r["PositiveHalf"]) or r["PositiveHalf"] == r["ExpectedResult"]]
    stray_pos = [r["CaseID"] for r in cases if r["CrossRole"] == "N" and r["PositiveHalf"] != NA]

    path_ids = [r["PathID"] for r in cover]
    by_path = {p: [] for p in path_ids}
    unknown_paths = []
    for r in cases:
        if r["OversellPaths"] == "none":
            continue
        for p in [x.strip() for x in r["OversellPaths"].split(";")]:
            if p in by_path:
                by_path[p].append(r)
            else:
                unknown_paths.append((r["CaseID"], p))
    uncovered = [p for p in path_ids if not any(c["Severity"] == "S1" for c in by_path[p])]
    stale = []
    for r in cover:
        want = "; ".join(c["CaseID"] for c in by_path[r["PathID"]] if c["Severity"] == "S1") or "NONE"
        if r["Sev1Cases"] != want:
            stale.append(r["PathID"])

    text = {r["CaseID"]: " ".join(r[c] for c in ("Attack", "ExpectedResult"))
            for r in cases}
    missing_topics = {t: [i for i in v if i not in text or not re.search(pat, text[i], re.I | re.S)]
                      for t, (v, pat) in REQUIRED_TOPICS.items()}
    missing_topics = {t: v for t, v in missing_topics.items() if v}
    no_harm = [r["CaseID"] for r in cases if r["Severity"] == "S1"
               and not set(x.strip() for x in r["Invariant"].split(";")) & set(S1_HARMS)]
    # The harm tags mean severity one. An S2 or S3 case carrying one is mis-graded or mis-tagged.
    harm_low = [r["CaseID"] for r in cases if r["Severity"] != "S1"
                and set(x.strip() for x in r["Invariant"].split(";")) & set(S1_HARMS)]
    harm_n = {h: sum(1 for r in cases if r["Severity"] == "S1" and h in r["Invariant"]) for h in S1_HARMS}
    card_runs = []
    for fn in sorted(os.listdir(HERE)):
        fp = os.path.join(HERE, fn)
        if os.path.isfile(fp):
            for n, ln in enumerate(open(fp, encoding="utf-8", errors="replace"), 1):
                card_runs += [f"{fn}:{n}" for _ in CARD_RUN.findall(ln)]
    nofam = [f for f in FAMILIES if not any(r["Family"] == f for r in cases)]

    plan = open(PLAN, encoding="utf-8").read()
    noplan = [f for f in FAMILIES if not re.search(rf"^### {re.escape(f)}\b", plan, re.M)]
    nonot = []
    for f in FAMILIES:
        m = re.search(rf"^### {re.escape(f)}\b(.*?)(?=^### |\Z)", plan, re.M | re.S)
        if m and "**Not tested" not in m.group(1):
            nonot.append(f)

    sev = {s: sum(1 for r in cases if r["Severity"] == s) for s in ("S1", "S2", "S3")}
    total = len(cases)

    def line(ok, name, detail):
        print(f"{'PASS' if ok else 'FAIL'}  {name:<16} {detail}")
        if not ok:
            fails.append(name)

    print("compressed per SRC-004 R-1 - consistency check, not a quality review")
    print(f"INFO  severity       S1 {sev['S1']} of {total} - S2 {sev['S2']} of {total} - S3 {sev['S3']} of {total}")
    stated = re.search(r"worst number first: (\d+) of (\d+) cases are severity one\.\*\* (\d+) are S2 and (\d+) are S3", plan)
    got = (sev["S1"], total, sev["S2"], sev["S3"])
    line(bool(stated) and tuple(int(x) for x in stated.groups()) == got, "plan-sev-count",
         f"plan states {stated.groups() if stated else 'nothing'}, case file gives {got}")
    line(not empty, "empty-cells", f"{len(empty)} empty cell(s) {empty[:5]}")
    line(not dup, "unique-ids", f"{len(dup)} duplicate id(s) {dup}")
    line(not badfam, "family-prefix", f"{len(badfam)} case(s) with a family/prefix mismatch {badfam}")
    line(not badsev, "severity-vocab", f"{len(badsev)} case(s) outside S1/S2/S3 {badsev}")
    line(not badcross, "crossrole-vocab", f"{len(badcross)} case(s) with CrossRole not Y/N {badcross}")
    line(not no_harm, "s1-harm", f"{len(no_harm)} S1 case(s) naming none of the five GOAL_11 harms {no_harm}")
    line(not harm_low, "harm-grade", f"{len(harm_low)} non-S1 case(s) carrying an S1 harm tag {harm_low}")
    print("INFO  s1-by-harm     " + " - ".join(f"{h} {n}" for h, n in harm_n.items()))
    line(not card_runs, "no-card-digits", f"{len(card_runs)} 13-19 digit run(s), solid or space/dash separated, in this folder {card_runs[:5]}")
    line(not missing_pos, "positive-half", f"{len(missing_pos)} of {len(cross)} cross-role case(s) missing a 2xx non-empty half {missing_pos}")
    line(not stray_pos, "positive-stray", f"{len(stray_pos)} non-cross-role case(s) carrying a positive half {stray_pos}")
    line(not uncovered, "oversell-cover", f"{len(path_ids)} path(s), {len(uncovered)} uncovered by a severity-one case {uncovered}")
    line(not unknown_paths, "oversell-refs", f"{len(unknown_paths)} case reference(s) to an undeclared path {unknown_paths[:5]}")
    line(not stale, "oversell-sync", f"{len(stale)} coverage row(s) whose Sev1Cases disagree with the case file {stale}")
    line(not nofam, "families", f"{len(FAMILIES) - len(nofam)} of {len(FAMILIES)} families have cases; missing {nofam}")
    line(not missing_topics, "named-topics", f"{len(REQUIRED_TOPICS) - len(missing_topics)} of {len(REQUIRED_TOPICS)} named topics answered by a case still on topic; failing {missing_topics}")
    line(not noplan, "plan-families", f"{len(noplan)} famil(ies) with no section in the attack plan {noplan}")
    line(not nonot, "plan-not-tested", f"{len(nonot)} famil(ies) whose plan section has no 'Not tested' statement {nonot}")
    print(f"RESULT {'exit 0' if not fails else 'exit 1'} ({len(fails)} failing check(s))")
    return 0 if not fails else 1


if __name__ == "__main__":
    sys.exit(main())

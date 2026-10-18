"""build_sit.py - generate docs/08 SIT/ case files from the Bible and the journeys.

Compressed per SRC-004 R-1. Standard library only. Run from anywhere:

    py "docs/08 SIT/tools/build_sit.py"

Writes (all GENERATED - never hand-edit; change this script or its inputs):
    docs/08 SIT/SIT_TestCases.tsv      one row per Bible AcceptanceCriteria cell (1:1)
    docs/08 SIT/SIT_JourneyCases.tsv   one row per journey walk in docs/11 Journeys/
    docs/08 SIT/BIBLE_DEFECTS_SIT.tsv  criteria that cannot be turned into a runnable case

Hand-maintained inputs it reads:
    docs/05 Bible/FrontRow_Bible.csv          (read only - another lane owns it)
    docs/11 Journeys/*_JOURNEY.md             (read only)
    docs/06 DataModel/schema.sql              (read only - table names of record)
    docs/08 SIT/FIXTURES.tsv                  (fixture catalogue, this lane)
    docs/08 SIT/tools/filed_defects.tsv       (defects filed by reading, this lane)

Method, stated so nobody mistakes it for more than it is: the ExpectedResult of every
unit case is the Bible cell itself, split into its '; '-separated clauses and numbered.
The case adds what the cell does not carry in a runnable form: the fixture, the clock
pin, the identities to open, the rows the cell names, and an ordered procedure. A case
generated this way can be no more binary than the cell it came from - which is the point
of the goal: where the cell cannot be run, the defect file says so.
"""
import csv
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SIT = os.path.dirname(HERE)
ROOT = os.path.dirname(os.path.dirname(SIT))
BIBLE = os.path.join(ROOT, "docs", "05 Bible", "FrontRow_Bible.csv")
SCHEMA = os.path.join(ROOT, "docs", "06 DataModel", "schema.sql")
JOURNEYS = os.path.join(ROOT, "docs", "11 Journeys")
PRD_SECTIONS = os.path.join(ROOT, "docs", "03 PRD", "sections")

LABEL = "compressed per SRC-004 R-1"
# The fixed injected instant every case starts from unless its cell pins another.
# 2026-08-14 is a FRIDAY; 12:50:00Z is 18:20:00 Asia/Kolkata. Chosen because S-RPT-11
# pins exactly this instant and the reporting cells use 2026-08-14 as 'today'.
T0 = "2026-08-14T12:50:00Z"

UNIT_COLS = ["CaseID", "BibleStoryID", "CriterionRef", "Title", "Precondition", "Steps",
             "ExpectedResult", "DataFixture", "ClockInstant", "Surface", "PRDRef",
             "Roles", "Phase", "Runnable", "DefectRef", "Label"]
JOURNEY_COLS = ["CaseID", "JourneyRef", "Persona", "Title", "Precondition", "Steps",
                "ExpectedResult", "DataFixture", "ClockInstant", "Surface", "PRDRef",
                "SeamsCrossed", "SeamTypes", "KnownDefects", "Runnable", "Label"]
DEFECT_COLS = ["DefectID", "BibleStoryID", "CriterionRef", "Class", "Blocks", "Reason",
               "Evidence", "FiledBy"]

# SRC-004 R-5's reference alphabet; the replaced one is it plus Z S B G, built rather than spelled so
# the old class appears nowhere in docs/08 SIT as text.
REF_ALPHABET = "23456789ACDEFHJKMNPQRTVWXY"
OLD_REF_ALPHABET = "".join(sorted(REF_ALPHABET + "BGSZ"))
# A cell that acts on an EXISTING booking/outbox/receipt_dispatch/hold row cannot run on FX-20-SEED
# alone (the seed holds none of them): a bind parameter or path placeholder naming one, or prose that
# presupposes one. Merely counting such rows ("count is unchanged") needs none and does not match.
NEEDS_ROWS = re.compile(
    r"\b(?:booking_id|reference|hold_token|hold_id|reset_token_id)\s*=\s*:[a-z_]+|"
    r"\{(?:booking_id|reference|hold_id|hold_token)\}|"
    r"(?i:\b(?:after|for|with|on|given|against|of|from) (?:a|an|one|the|each|two|three|its|that) "
    r"(?:(?:successful|confirmed|pending|live|active|existing|paid|held|second|first|new|seat) )*"
    r"(?:bookings?|holds?|receipt_dispatch rows?|outbox(?:_message)? rows?|reset requests?)\b)")
# A precondition borrowed from another story: "S-RPT-06's seed", "the five-seat fixture of S-PAY-02".
XREF = re.compile(r"\b(S-[A-Z]{3}-\d\d)'s (?:[\w-]+ ){0,2}(?:seed|fixture|capacities|selection|rows)\b|"
                  r"\b(?:seed|fixture|rows) of (S-[A-Z]{3}-\d\d)\b")

ISO = r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2})?(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})"


def clean(s):
    return re.sub(r"[\t\r\n]+", " ", s).strip()


def read_tsv(path):
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f, delimiter="\t", quoting=csv.QUOTE_NONE))


def write_tsv(path, cols, rows):
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write("\t".join(cols) + "\n")
        for r in rows:
            f.write("\t".join(clean(str(r.get(c, ""))) for c in cols) + "\n")


def split_clauses(cell):
    """Split on the Bible's '; ' clause separator, never inside quotes/backticks/brackets."""
    out, buf, depth, q = [], [], 0, None
    i = 0
    while i < len(cell):
        ch = cell[i]
        if q:
            if ch == q:
                q = None
        elif ch in "`\"":
            q = ch
        elif ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth = max(0, depth - 1)
        elif ch == ";" and depth == 0 and cell[i + 1:i + 2] == " ":
            out.append("".join(buf).strip())
            buf = []
            i += 2
            continue
        buf.append(ch)
        i += 1
    if "".join(buf).strip():
        out.append("".join(buf).strip())
    return [c for c in out if c]


def strip_quoted(s):
    """Remove quoted/backticked spans - search patterns and literal strings."""
    s = re.sub(r"`[^`]*`", " ", s)
    s = re.sub(r"'[^']*'", " ", s)
    s = re.sub(r"\"[^\"]*\"", " ", s)
    return s


def surfaces(a):
    s = []
    if re.search(r"\b(GET|POST|PATCH|PUT|DELETE|HEAD|OPTIONS) /", a):
        s.append("api")
    if re.search(r"\bSELECT\b|information_schema|pg_[a-z_]+|\bINSERT\b|\bUPDATE\b", a):
        s.append("db")
    if re.search(r"\bRedis\b|\bSET\b .*NX|\bPTTL\b|\bTTL\b|lock:seat|\bDEL\b", a):
        s.append("redis")
    if re.search(r"(?i)\bworker\b|\bqueue\b|ElasticMQ|\bSQS\b|\bSES\b|outbox", a):
        s.append("worker-queue")
    if re.search(r"(?i)render|aria-|\bbutton\b|screen reader|keyboard|frontend/src|\bpx\b|focus|landing page", a):
        s.append("ui")
    if re.search(r"scripts/", a):
        s.append("script")
    if re.search(r"\brg\b|ripgrep|inspect\.signature|app\.routes|OpenAPI|route table|\.github/", a):
        s.append("static")
    if re.search(r"docs/", a):
        s.append("docs")
    if re.search(r"(?i)deployed environment|against the deployed|AWS", a):
        s.append("deployed")
    if re.search(r"(?i)container|SIGTERM|/health/|Dockerfile|docker", a):
        s.append("runtime")
    return s or ["static"]


def roles(a):
    r = []
    if re.search(r"(?i)\bguest\b|no session|unauthenticated|no JWT|without (a|the) cookie|anonymous", a):
        r.append("guest")
    if re.search(r"(?i)\bcustomers?\b|signed in as [A-Z]\b|/api/me/|/holds|/api/bookings|\bregist|stress_seats", a):
        r.append("customer")
    if re.search(r"(?i)\bmanager\b|/api/reports", a):
        r.append("manager")
    if re.search(r"(?i)\badmin\b|/api/admin", a):
        r.append("admin")
    return r


def literals(a):
    """Rows, identities and configuration the cell names literally - the precondition as data."""
    found = []

    def add(kind, vals):
        vals = sorted(set(vals), key=lambda v: (len(v), v))
        if vals:
            found.append(kind + "=" + ",".join(vals[:12]))
    add("showtime_id", re.findall(r"showtimes?/(\d+)", a) + re.findall(r"showtime_id\s*=\s*(\d+)", a)
        + re.findall(r"--showtime (\d+)", a) + re.findall(r"showtime (\d+)", a))
    add("showtime_key", re.findall(r"\bST-\d+\b", a))
    add("seat_id", re.findall(r"seat_id\s*=\s*(\d+)", a) + re.findall(r"--seat (\d+)", a)
        + re.findall(r"lock:seat:\d+:(\d+)", a))
    add("seat_label", re.findall(r"\b(?:seat|seats) ([A-Z]{1,2}\d{1,3})\b", a)
        + re.findall(r"\[\"([A-Z]{1,2}\d{1,3})\"\]", a))
    add("screen", re.findall(r"(?i)screen[_ ](?:id\s*=\s*)?(\d+)", a))
    add("booking_id", re.findall(r"booking_id\s*=\s*(\d+)", a))
    add("user_id", re.findall(r"user_id\s*=\s*(\d+)", a) + re.findall(r"actor_user_id (\d+)", a))
    add("reference", re.findall(r"reference (?:is )?[`']?([A-Z0-9]{8})\b", a)
        + re.findall(r"\bFR-[A-Z0-9]{4}-[A-Z0-9]{3,5}\b", a))
    add("email", re.findall(r"[A-Za-z0-9._+-]+@[A-Za-z0-9-]+\.[A-Za-z.]+", a))
    add("actor", re.findall(r"\b(?:customer|manager|admin) ([A-Z]\d?)\b", a))
    add("movie", re.findall(r"DEMO MOVIE \d\d", a))
    add("price_paise", re.findall(r"base(?: price)? (?:of )?(\d{3,7})(?: paise)?", a)
        + re.findall(r"base_price_paise\s*=\s*(\d+)", a))
    add("uplift_bp", re.findall(r"(\d{1,5}) basis points", a))
    add("seat_count", re.findall(r"(\d{2,3})[- ]seat\b", a))
    add("instant", re.findall(ISO, a))
    add("state", [m.group(0) for m in re.finditer(
        r"(?i)against an empty database|after alembic upgrade head|on a hall where [^,;]{0,60}|"
        r"customer [A-Z] owns [^,;]{0,40}|for two bookings [^,;]{0,60}|seed(?:ed)? a [^,;]{0,80}|"
        # the bare "for a confirmed booking" is the precondition itself, not data: require more after the noun
        r"for a (?:seeded|confirmed) \w+ [^,;:]{1,80}", a)])
    if "stress_seats" in a:
        found.append("users=stress01..stress50@frontrow.test (FX-10-ACCOUNTS), signed in by the script's own warm-up")
    add("named_constants", [t for t in re.findall(r"\b((?:[A-Z][A-Z0-9]+_){1,}[A-Z0-9]+)\b", strip_quoted(a))
                   if not re.match(r"CURRENT_|LOCALTIME|STATEMENT_", t)])
    ph = sorted(set(re.findall(r"[/:]\{([a-z_]+)\}", a)))
    if ph:
        found.append("path placeholders " + ",".join(ph) + " bound to the lowest-id matching row of FX-20-SEED "
                     "(the cell asserts a property of any such row)")
    return found


def clock(a, static_only):
    if static_only:
        return "not applicable - static inspection of the repository; no clock is read or set"
    pin = re.search(r"injected clock (?:at|to|set to|pinned to|of) (" + ISO + ")", a)
    t0 = pin.group(1) if pin else T0
    inst = sorted(set(re.findall(ISO, a)) - {t0})[:10]
    offs = sorted(set(re.findall(r"\bT0?\s*[+-]\s*\d+(?:\.\d+)?\s*(?:ms|s|min|m|h)\b", a)))[:10]
    s = "injected clock pinned to " + t0 + (" (pinned by the cell)" if pin else " (SIT default T0)")
    if inst:
        s += "; instants the cell names: " + ", ".join(inst)
    if offs:
        s += "; advanced by the injected clock to: " + ", ".join(offs)
    return s


def fixture(a, title, surf):
    runtime = [s for s in surf if s not in ("static", "docs")]
    if not runtime:
        return "FX-STATIC"
    base = "FX-30-CELL"
    if re.search(r"(?i)\bseed\b", title) or re.search(r"scripts/seed\.py (creates|is run|run)|fresh seed", a):
        base = "FX-00-SCHEMA (the seed is the subject under test)"
    if "deployed" in surf:
        base += "; FX-DEPLOYED for the clauses that name the deployed environment"
    return base


def prd_index():
    idx = {}
    for fn in sorted(os.listdir(PRD_SECTIONS)):
        if not fn.endswith(".md"):
            continue
        with open(os.path.join(PRD_SECTIONS, fn), encoding="utf-8") as f:
            for n, line in enumerate(f, 1):
                m = re.match(r"^#+\s*`?(P-[A-Z]{3}-\d{2})`?", line)
                if m and m.group(1) not in idx:
                    idx[m.group(1)] = "%s:%d" % (fn, n)
    return idx


def schema_tables():
    with open(SCHEMA, encoding="utf-8") as f:
        return set(re.findall(r"CREATE TABLE ([a-z_]+)", f.read()))


def mech_defects(sid, a, tables, lits, surf):
    """Mechanical detectors. Each returns (class, blocks, reason, evidence)."""
    out = []
    s = strip_quoted(a)
    for m in re.finditer(r"\bSELECT\b[^;]{0,240}?\bFROM\s+([a-z_][a-z0-9_.]*)", s):
        t = m.group(1)
        if t in tables or t.startswith(("pg_", "information_schema", "jsonb_", "generate_series")):
            continue
        if len(t) <= 2 or t in ("that", "the", "this", "it", "which", "a", "its"):   # alias or prose
            continue
        out.append(("table-not-in-schema", "yes",
                    "queries table '%s', which docs/06 DataModel/schema.sql does not create; as written the "
                    "SELECT errors against a correct schema" % t, s[m.start():m.end() + 40]))
    # SRC-004 R-5: reference alphabet loses Z S B G and gains a trailing check character.
    refs = re.findall(r"\bFR-([A-Z0-9]{4})-([A-Z0-9]{3,5})\b", a) + \
        [(x[:4], x[4:]) for x in re.findall(r"(?:reference (?:is )?|`|')([A-Z0-9]{8})(?:`|'|\b)", a)]
    # only literals that are well-formed under the OLD alphabet count; a deliberately malformed
    # input such as FR-0BCD-EFGH (a zero typed for O) is a negative probe, not a stale reference
    bad = sorted({p + q for p, q in refs
                  if re.fullmatch("[%s]{8}" % OLD_REF_ALPHABET, p + q) and re.search(r"[ZSBG]", p + q)})
    if bad or "30-character alphabet" in a or OLD_REF_ALPHABET in a:
        out.append(("stale-vs-SRC-004-R-5", "yes",
                    "asserts a booking reference shape SRC-004 R-5 replaced: the alphabet now excludes Z S B G "
                    "and every reference carries one trailing check character; literals or alphabet cited: %s"
                    % (", ".join(bad) or "the 30-character alphabet"), ", ".join(bad)))
    return out


def unit_cases(defect_rows):
    with open(BIBLE, encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    stories = [r for r in rows if r["Type"] == "Story"]
    pidx = prd_index()
    tables = schema_tables()
    filed = read_tsv(os.path.join(HERE, "filed_defects.tsv"))
    cases = []
    n = 0
    for r in stories:
        sid, a = r["ID"], r["AcceptanceCriteria"].strip()
        n += 1
        cref = sid + "/AC"
        clauses = split_clauses(a)
        surf = surfaces(a)
        static_only = not [x for x in surf if x not in ("static", "docs")]
        lits = literals(a)
        rl = roles(a)
        fx = fixture(a, r["Title"], surf)
        pids = re.findall(r"P-[A-Z]{3}-\d{2}", r["SourceRef"])
        prd = " ".join("%s(%s)" % (p, pidx.get(p, "UNRESOLVED")) for p in dict.fromkeys(pids))
        my = []
        for cls, blocks, reason, ev in mech_defects(sid, a, tables, lits, surf):
            my.append(dict(BibleStoryID=sid, CriterionRef=cref, Class=cls, Blocks=blocks,
                           Reason=reason, Evidence=ev, FiledBy="mechanical: build_sit.py"))
        xrefs = sorted({x for m in XREF.finditer(a) for x in m.groups() if x and x != sid})
        if xrefs:
            my.append(dict(BibleStoryID=sid, CriterionRef=cref, Class="precondition-by-cross-reference",
                           Blocks="no",
                           Reason="the precondition is another story's setup (%s), named but not stated; the "
                                  "case runs only with that story's rows loaded first. Runnable; not "
                                  "self-contained" % ", ".join(xrefs),
                           Evidence=XREF.search(a).group(0), FiledBy="mechanical: build_sit.py"))
        # Data literals only. UPPER_SNAKE constants (error codes, config names) and path placeholders
        # bound to FX-20-SEED never say which booking/outbox/receipt_dispatch/hold row exists, and
        # counting them is why this detector could never fire.
        data = [x for x in lits if not x.startswith(("named_constants=", "path placeholders "))]
        xfiled = any(fr["BibleStoryID"] == sid and fr["Class"] == "precondition-by-cross-reference"
                     for fr in filed)
        need = NEEDS_ROWS.search(a)
        if not static_only and not data and not xrefs and not xfiled and need:
            my.append(dict(BibleStoryID=sid, CriterionRef=cref, Class="precondition-not-in-cell",
                           Blocks="yes",
                           Reason="the cell needs a booking/outbox/receipt_dispatch/hold row (it names '%s') "
                                  "but no identifier, instant, state or row the precondition can be stated "
                                  "as data from, and FX-20-SEED holds none; the case cannot pin it without "
                                  "inventing rows" % need.group(0), Evidence="no data literal extracted",
                           FiledBy="mechanical: build_sit.py"))
        for fr in filed:
            if fr["BibleStoryID"] == sid:
                my.append(dict(fr, CriterionRef=cref, FiledBy="by reading: " + fr.get("FiledBy", "")))
        for d in my:
            d["DefectID"] = "SITD-%03d" % (len(defect_rows) + 1)
            defect_rows.append(d)
        blocking = [d for d in my if d["Blocks"] == "yes"]
        pre = ["load DataFixture " + fx.split(" ")[0]]
        pre += ["rows/identities named by the cell: " + "; ".join(lits)] if lits else \
            ["no additional rows: the cell names none" + (" and needs none (static)" if static_only else "")]
        if rl:
            pre.append("authenticated clients opened for: " + ", ".join(rl))
        steps = ["1 reset to DataFixture via the harness (harness/README.md section Fixtures)",
                 "2 " + ("no clock is involved" if static_only else "pin the injected clock to ClockInstant; "
                         "advance it only as a clause states"),
                 "3 " + ("open one harness client per role: " + ", ".join(rl) if rl else "no client session needed"),
                 "4 perform clauses C1..C%d of ExpectedResult in order, each being the action it names and "
                 "the observation it asserts" % len(clauses),
                 "5 record every observation; PASS iff every clause holds, FAIL on the first that does not"]
        cases.append(dict(
            CaseID="SIT-%s" % sid[2:], BibleStoryID=sid, CriterionRef=cref, Title=r["Title"],
            Precondition=" | ".join(pre), Steps=" | ".join(steps),
            ExpectedResult=" ".join("C%d: %s" % (i + 1, c) for i, c in enumerate(clauses)),
            DataFixture=fx, ClockInstant=clock(a, static_only), Surface="+".join(surf), PRDRef=prd,
            Roles=",".join(rl) or "none", Phase=r["Milestone"],
            Runnable="no" if blocking else "yes",
            DefectRef=" ".join(d["DefectID"] for d in my) or "-", Label=LABEL))
    return cases, len(stories)


def journey_cases():
    files = [("GUEST_JOURNEY.md", "guest"), ("CUSTOMER_JOURNEY.md", "customer"),
             ("ADMIN_JOURNEY.md", "admin"), ("MANAGER_JOURNEY.md", "manager"),
             ("CROSSCUTTING_JOURNEY.md", "cross-cutting")]
    out = []
    for fn, persona in files:
        with open(os.path.join(JOURNEYS, fn), encoding="utf-8") as f:
            lines = f.read().splitlines()
        walk, rows, hdr, sub = None, [], None, ""

        def flush():
            if walk and rows:
                out.append(make_journey(fn, persona, walk, rows))
        for ln in lines:
            m = re.match(r"^#{1,3}\s+(Walk \d+\b.*|RE-\d+\b.*)$", ln)
            if m:
                flush()
                walk, rows, hdr = m.group(1).strip(), [], None
                continue
            sm = re.match(r"^###\s+(.*)$", ln)
            if sm:
                sub = sm.group(1).strip()
            if walk and ln.startswith("| # |"):
                hdr = [c.strip() for c in ln.strip("|").split("|")]
                if rows:   # a second step table under one walk is its own walk
                    flush()
                    walk, rows = walk.split(" (sub-walk")[0] + " (sub-walk: " + sub + ")", []
                continue
            if walk and hdr and re.match(r"^\|\s*\d+(\.\d+)?\s*\|", ln):
                cells = [c.strip() for c in ln.strip().strip("|").split(" | ")]
                if len(cells) >= len(hdr):
                    rows.append(dict(zip(hdr, cells)))
        flush()
    return out


def dewall(s):
    """Journey prose says 'today' meaning the local date of the injected clock; say so."""
    return re.sub(r"(?i)\btoday\b", "T0's local date", s)


def make_journey(fn, persona, walk, rows):
    code = {"GUEST": "GST", "CUSTOMER": "CUS", "ADMIN": "ADM", "MANAGER": "MGR", "CROSSCUTTING": "XCT"}[fn.split("_")[0]]
    wid = re.match(r"(Walk \d+|RE-\d+)", walk).group(1).replace("Walk ", "W").replace(" ", "")
    if "(sub-walk" in walk:
        wid += "b"
    if wid.startswith("RE-"):
        code = "ENT"
    pids, seams, types, defs = [], [], [], []
    for r in rows:
        pids += re.findall(r"P-[A-Z]{3}-\d{2}", r.get("P-rows", ""))
        seams.append(r.get("Seam crossed", ""))
        types.append(r.get("Seam type", "").strip("`"))
        defs += re.findall(r"J-[A-Z]{3}-\d{2}", r.get("Defects", ""))
    pidx = prd_index()
    allt = " ".join(r.get("Action", "") + " " + r.get("Seam crossed", "") for r in rows)
    first = rows[0]
    return dict(
        CaseID="SITJ-%s-%s" % (code, wid), JourneyRef="docs/11 Journeys/%s#%s" % (fn, walk.split(" — ")[0]),
        Persona=persona, Title=walk,
        Precondition=dewall("load DataFixture FX-30-CELL; walk entry state (step 1): " + first.get("State entering", "")),
        Steps=dewall(" ".join("J%s: [%s] %s" % (r.get("#"), r.get("Surface", ""), r.get("Action", "")) for r in rows)),
        ExpectedResult=dewall(" ".join("J%s: %s" % (r.get("#"), r.get("What they leave with", "")) for r in rows)),
        DataFixture="FX-30-CELL" + ("; FX-DEPLOYED where a step names the deployed environment"
                                    if re.search(r"(?i)deployed|AWS", allt) else ""),
        ClockInstant="injected clock pinned to %s (SIT default T0); every TTL, cut-off or expiry a step "
                     "crosses is reached by advancing the injected clock, never by waiting" % T0,
        Surface="+".join(surfaces(allt)),
        PRDRef=" ".join("%s(%s)" % (p, pidx.get(p, "UNRESOLVED")) for p in dict.fromkeys(pids)) or "-",
        SeamsCrossed=" || ".join("J%s %s" % (r.get("#"), s) for r, s in zip(rows, seams)),
        SeamTypes=",".join(dict.fromkeys(t for t in types if t)),
        KnownDefects=" ".join(dict.fromkeys(defs)) or "-",
        Runnable="yes" if not defs else "yes-with-known-defects (the expected value at a step carrying a "
                                        "J- defect is the documents' reading and may itself be wrong)",
        Label=LABEL)


def main():
    defects = []
    cases, nstories = unit_cases(defects)
    write_tsv(os.path.join(SIT, "SIT_TestCases.tsv"), UNIT_COLS, cases)
    write_tsv(os.path.join(SIT, "BIBLE_DEFECTS_SIT.tsv"), DEFECT_COLS, defects)
    jc = journey_cases()
    write_tsv(os.path.join(SIT, "SIT_JourneyCases.tsv"), JOURNEY_COLS, jc)
    print("stories=%d unit_cases=%d journey_cases=%d defects=%d runnable_no=%d"
          % (nstories, len(cases), len(jc), len(defects), sum(c["Runnable"] == "no" for c in cases)))
    return 0


if __name__ == "__main__":
    sys.exit(main())

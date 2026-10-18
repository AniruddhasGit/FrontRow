#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""generate_ledger.py - derive docs/10 EngineeringLedger/engineering_ledger.tsv from the Bible.

Produced by GOAL_12, compressed per SRC-004 R-1 (one lighter pass over GOAL_09-13; never a
faked green, never an invented answer to an OPEN row).

    py "docs/10 EngineeringLedger/generate_ledger.py"           regenerate the ledger
    py "docs/10 EngineeringLedger/generate_ledger.py" --check   regenerate in memory, diff it
                                                                 against the file, run every check

The ledger is GENERATED. Only two columns survive regeneration, keyed by ID: `Status` and
`StatusNote` (the reason a row is Blocked lives IN the row). Every other cell is recomputed
from its inputs, so hand-editing one is pointless - the next run puts it back, and --check
fails until it does.

Inputs (read only - this script writes exactly one file):
    docs/05 Bible/FrontRow_Bible.csv                    the stories, their criteria, milestones
    CONSTITUTION.md Article X (X.0 .. X.0g)             which OPEN-* rows are still open
    docs/00 SourceOfTruth/SRC-004_*.md                  rows SRC-004 ruled after Article X was written
    docs/05 Bible/CENSUS_*.md                           stories the census named as defective
    docs/08 SIT/SIT_TestCases.tsv, SIT_JourneyCases.tsv cases, when GOAL_10 has written them
    docs/09 NegativeTesting/SIT_NegativeCases.tsv       cases, when GOAL_11 has written them

Standard library only. Deterministic: same inputs, same bytes.
"""
from __future__ import annotations

import argparse
import csv
import difflib
import glob
import io
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
BIBLE = os.path.join(ROOT, "docs", "05 Bible", "FrontRow_Bible.csv")
LEDGER = os.path.join(HERE, "engineering_ledger.tsv")
CONSTITUTION = os.path.join(ROOT, "CONSTITUTION.md")
SRC_DIR = os.path.join(ROOT, "docs", "00 SourceOfTruth")
CENSUS_GLOB = os.path.join(ROOT, "docs", "05 Bible", "CENSUS_*.md")
SIT_FILES = [os.path.join(ROOT, "docs", "08 SIT", "SIT_TestCases.tsv"),
             os.path.join(ROOT, "docs", "08 SIT", "SIT_JourneyCases.tsv")]
NEG_FILES = [os.path.join(ROOT, "docs", "09 NegativeTesting", "SIT_NegativeCases.tsv")]

COLUMNS = ["Type", "ID", "ParentID", "Epic", "Lane", "Title", "AcceptanceCriteria", "Priority",
           "Estimate", "Milestone", "Status", "StatusNote", "DependsOn", "Labels", "Persona",
           "Classification", "Risk", "OwnedPaths", "Wave", "TestTrustLevel", "SITCaseIDs",
           "NegativeCaseIDs", "OpenRefs", "RuledRefs", "EvidencePath", "SourceRef", "GoalRef"]
PRESERVED = ("Status", "StatusNote")
STATUSES = ("Backlog", "InProgress", "Done", "Blocked")

STORY_ID = re.compile(r"\b(?:S-[A-Z]{3}-\d{2}|E-[A-Z]{3}(?:-[AB])?|T-P\d-\d{2})\b")
OPEN_ID = re.compile(r"\bOPEN-[A-Z0-9]+-\d{2}\b")

# --------------------------------------------------------------------------------------------
# Phase 1 skeleton tasks. SRC-002 §12.2 names Phase 1 as "Repo skeleton, config loading, health
# endpoints, structured logging, local docker-compose with Postgres and Redis. Nothing else."
# The Bible's milestone-1 stories cover most of it, but no Bible story has the repo skeleton
# itself as its subject, and the Phase 1 goal (GOAL_14) works by unit, not by story. These are
# Type=Task rows: each one DECOMPOSES a Bible story (its ParentID) or, for the skeleton, cites
# the frozen source directly. They add no scope - every criterion below is a GOAL_14 DoD line
# or a clause of the parent story. Estimates are left empty: nobody has estimated them.
# --------------------------------------------------------------------------------------------
P1_TASKS = [
    ("T-P1-01", "E-XCT", "Lay down the repo skeleton in the SRC-002 §11 shape",
     "backend/app/{api,core,domain,models,workers,jobs}/, backend/migrations/, backend/tests/, "
     "frontend/src/, scripts/ exist, each with the file that makes it importable or buildable; "
     "the backend imports with py -c 'import app.main' from backend/ and exits 0; "
     "the frontend builds with npm run build and exits 0; no movie, showtime, seat or booking "
     "model exists anywhere in the tree (GOAL_14: a Phase 1 that also contains a movie model "
     "has failed)",
     "", "backend", "backend/app/main.py;backend/app/__init__.py;backend/pyproject.toml;"
     "backend/requirements.txt;frontend/package.json;frontend/index.html;frontend/src/main.tsx;"
     "README.md;.env.example",
     "SRC-002 §11 SRC-002 §12.2"),
    ("T-P1-02", "S-XCT-29", "Load and validate configuration from the environment",
     "removing one required environment variable makes the container exit non-zero with a "
     "message naming that variable, pasted (GOAL_14 DoD); no default silently papers over a "
     "missing required value (SRC-002 §7.1); see the parent story for the full criterion",
     "T-P1-01", "backend infra", "backend/app/core/config.py",
     "SRC-002 §7.1 SRC-002 §12.2"),
    ("T-P1-03", "S-XCT-21", "Serve /health/live touching no dependency",
     "GET /health/live returns 200 with the API container up, and still returns 200 while both "
     "Postgres and Redis are stopped (GOAL_14 DoD); see the parent story",
     "T-P1-01", "backend infra", "backend/app/api/health.py",
     "SRC-002 §7.4 SRC-002 §12.2"),
    ("T-P1-04", "S-XCT-21", "Serve /health/ready returning 503 when Postgres or Redis is down",
     "GET /health/ready returns 200 with both dependencies up, 503 with the Redis container "
     "stopped and 503 with the Postgres container stopped, all three outputs pasted - stopping a "
     "container is the proof (GOAL_14 DoD); see the parent story",
     "T-P1-02 T-P1-03", "backend infra", "backend/app/api/health.py",
     "SRC-002 §7.4 SRC-002 §12.2"),
    ("T-P1-05", "S-XCT-24", "Emit JSON logs to stdout with a request id on every line",
     "every log line of a docker compose logs api capture parses as JSON and carries a request "
     "id; the parse-failure count is pasted and is 0; zero log files exist on disk inside the "
     "container (GOAL_14 DoD); see the parent story",
     "T-P1-01", "backend infra", "backend/app/core/logging.py;backend/app/core/request_id.py",
     "SRC-002 §7.6 SRC-002 §12.2"),
    ("T-P1-06", "S-XCT-31", "Drain in-flight requests on SIGTERM and exit 0",
     "SIGTERM to the API container drains in-flight requests and exits 0 inside the grace "
     "period, with the timing pasted (GOAL_14 DoD); the shutdown hook exists for Phase 4 to hang "
     "the lock release on, and releases nothing in Phase 1 because no lock exists yet",
     "T-P1-02", "backend infra", "backend/app/core/shutdown.py;backend/entrypoint.sh",
     "SRC-002 §7.5 SRC-002 §12.2"),
    ("T-P1-07", "S-XCT-35", "Write docker-compose.yml for local development only",
     "docker compose up brings up the API, Postgres and Redis and the API answers "
     "GET /health/live with 200, output pasted (GOAL_14 DoD); the file says in a comment at its "
     "top that it is local development only (SRC-002 §6.1.7); no migration runs on boot "
     "(SRC-002 §7.8)",
     "T-P1-08", "infra", "docker-compose.yml",
     "SRC-002 §6.1 SRC-002 §7.8 SRC-002 §12.2"),
    ("T-P1-08", "S-XCT-35", "Build the API image multi-stage and under 250 MB",
     "docker images reports the built API image under 250 MB, the real number pasted - measured, "
     "not estimated (GOAL_14 DoD, SRC-002 §5.4.2); every production line of the Dockerfile and "
     "entrypoint carries a what-breaks-without-it comment, confirmed by a reviewer who is not the "
     "author (SRC-002 §6.2)",
     "T-P1-01", "infra", "backend/Dockerfile;frontend/Dockerfile;backend/.dockerignore",
     "SRC-002 §5.4 SRC-002 §6.2 SRC-002 §12.2"),
    ("T-P1-09", "S-XCT-40", "Specify every Zone C item Phase 1 needs",
     "every Zone C item the Phase 1 deploy needs has a specification in docs/30 Deployment/ "
     "carrying What to build, What the application expects, Acceptance criteria and Common "
     "mistakes, and a prep-queue row with a needed-by stage, and was said in chat (GOAL_14 DoD); "
     "no Zone C artefact is written and nothing is created in AWS (SRC-002 §6.5)",
     "T-P1-01", "infra", "docs/30 Deployment/",
     "SRC-002 §6.5 SRC-002 §12.2"),
]

# --------------------------------------------------------------------------------------------
# OwnedPaths - ASSUMED. docs/07 Architecture/ had no module map when this was written, so the
# paths are the SRC-002 §11 shape split by lane. Every row also owns its own test file, which
# never collides. When GOAL_09 publishes a module map, replace LANE_PATHS and XCT_RULES with it.
# --------------------------------------------------------------------------------------------
LANE_PATHS = {
    "ACC": ["backend/app/api/auth.py", "backend/app/domain/accounts/", "frontend/src/features/account/"],
    "ADM": ["backend/app/api/admin/", "backend/app/domain/admin/", "frontend/src/features/admin/"],
    "BRW": ["backend/app/api/browse.py", "backend/app/domain/catalogue/", "frontend/src/features/browse/"],
    "SEA": ["backend/app/api/holds.py", "backend/app/domain/holds/", "frontend/src/features/seatmap/"],
    "PAY": ["backend/app/api/bookings.py", "backend/app/domain/booking/", "frontend/src/features/checkout/"],
    "TKT": ["backend/app/workers/", "backend/app/domain/receipt/"],
    "RPT": ["backend/app/api/reports.py", "backend/app/domain/reports/", "frontend/src/features/dashboard/"],
    "SCP": [],   # a scope guard writes only its test
}
XCT_RULES = [   # (regex over the title, paths) - every match is unioned
    (r"health", ["backend/app/api/health.py"]),
    (r"setting|configuration", ["backend/app/core/config.py"]),
    (r"\blogs?\b|[Rr]edact|request id", ["backend/app/core/logging.py"]),
    (r"SIGTERM|[Dd]rain", ["backend/app/core/shutdown.py"]),
    (r"[Rr]ate-limit|Retry-After|X-Forwarded-For|warm-up", ["backend/app/core/ratelimit.py"]),
    (r"/metrics", ["backend/app/api/metrics.py"]),
    (r"[Mm]igration|unique constraint|seat-occupancy", ["backend/migrations/"]),
    (r"paise|money", ["backend/app/domain/money.py"]),
    (r"audit", ["backend/app/core/audit.py", "backend/migrations/"]),
    (r"deletable", ["backend/migrations/"]),
    (r"authorisation|screen scope", ["backend/app/api/deps.py"]),
    (r"credential|cookie", ["backend/app/core/security.py"]),
    (r"[Cc]ache|Redis's", ["backend/app/core/cache.py"]),
    (r"[Ss]eed", ["scripts/seed.py"]),
    (r"fifty|concurrency proof|unique constraint fail|seat guarantee", ["scripts/stress_seats.py"]),
    (r"error envelope|405", ["backend/app/api/errors.py"]),
    (r"[Ss]pecify|Zone C|SSM|alarm|production|task definition|backup", ["docs/30 Deployment/"]),
    (r"stateless|1 GB|scheduled job|service or dependency", ["docker-compose.yml", "backend/Dockerfile"]),
    (r"WCAG|375-pixel", ["frontend/src/styles/"]),
    (r"booked any seat", ["backend/app/domain/booking/"]),
    # process and absence stories: they own only their test file
    (r"eight phases|reserved question|artificial-intelligence", []),
]

# Classification - which SRC-002 §6 zone the row's code falls in. Title keywords, first match.
ZONE_C_SPEC = re.compile(r"Specify|Zone C|SSM|task definition|alarm|backup")
ZONE_B = re.compile(r"health|SIGTERM|[Dd]rain|setting from the environment|stateless|1 GB|"
                    r"[Mm]igrations as a separate|Dockerfile|container|refuse to boot|Refuse to boot")

MILESTONE_GOAL = {"1": "GOAL_14"}   # later phase goals are not written yet: GoalRef says so


def die(msg: str) -> None:
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(2)


def read_text(p: str) -> str:
    with open(p, encoding="utf-8") as f:
        return f.read()


def lane_of(row_id: str) -> str:
    m = re.match(r"[EST]-([A-Z]{3}|P\d)", row_id)
    return m.group(1) if m else ""


def owned_paths(row: dict) -> list[str]:
    lane = row["Lane"]
    title = row["Title"]
    labels = row["Labels"].split()
    paths: list[str] = []
    if lane == "XCT":
        matched = False
        for rx, ps in XCT_RULES:
            if re.search(rx, title):
                paths += ps
                matched = True
        if not matched:
            paths = ["backend/app/core/"]
    else:
        paths += LANE_PATHS.get(lane, [])
    if "data" in labels and row["Milestone"] == "2" and lane not in ("SCP",):
        paths.append("backend/migrations/")
    lane_dir = lane.lower()
    paths.append(f"backend/tests/{lane_dir}/test_{row['ID'].lower().replace('-', '_')}.py")
    out: list[str] = []
    for p in paths:
        if p not in out:
            out.append(p)
    return out


def overlaps(a: str, b: str) -> bool:
    """Equal, or one is a directory (trailing /) containing the other."""
    if a == b:
        return True
    if a.endswith("/") and b.startswith(a):
        return True
    if b.endswith("/") and a.startswith(b):
        return True
    return False


def persona_of(row: dict) -> str:
    text = " ".join((row["Title"], row.get("Description", ""), row["AcceptanceCriteria"])).lower()
    found = [p for p in ("guest", "customer", "manager", "admin") if re.search(rf"\b{p}s?\b", text)]
    if row["Lane"] == "ADM" and "admin" not in found:
        found.append("admin")
    if row["Lane"] == "RPT" and "manager" not in found:
        found.append("manager")
    if not found:
        found = ["operator"]
    order = ["guest", "customer", "manager", "admin", "operator"]
    return " ".join(sorted(set(found), key=order.index))


def classification_of(row: dict) -> str:
    t = row["Title"]
    if ZONE_C_SPEC.search(t):
        return "ZoneC-spec"
    if ZONE_B.search(t):
        return "ZoneB"
    return "ZoneA"


def risk_of(row: dict, open_refs: list[str]) -> str:
    labels = set(row["Labels"].split())
    if labels & {"concurrency", "money", "security"} or open_refs:
        return "High"
    if labels & {"data", "email", "infra"}:
        return "Medium"
    return "Low"


SEAM = {"S-SEA-20", "S-ACC-13", "S-ACC-08"}   # BIBLE_COLUMN_DICTIONARY: need an unspecified seam
WALL = {"S-SEA-15"}                           # BIBLE_COLUMN_DICTIONARY: wall-clock measurement


def trust_of(row: dict, census_named: set[str]) -> str:
    rid = row["ID"]
    if rid in SEAM:
        return "needs-seam"
    if rid in WALL:
        return "wall-clock"
    if rid in census_named:
        return "census-named"
    if re.search(r"\b(ECS|ALB|RDS|ElastiCache|deployed environment|CloudWatch|task definition)\b",
                 row["AcceptanceCriteria"]):
        return "aws-reasoned"
    return "spec"


def open_rows() -> tuple[set[str], set[str]]:
    """(still-open ids per CONSTITUTION Art X X.0..X.0g, ids SRC-004 has since ruled)."""
    text = read_text(CONSTITUTION)
    start = text.find("### X.0 ")
    end = text.find("### X.1 ")
    if start < 0 or end < 0:
        die("CONSTITUTION.md Article X sections X.0 / X.1 not found")
    opened: set[str] = set()
    for line in text[start:end].splitlines():
        m = re.match(r"\|\s*`(OPEN-[A-Z0-9]+-\d{2})`", line)
        if m:
            opened.add(m.group(1))
    ruled: set[str] = set()
    for p in sorted(glob.glob(os.path.join(SRC_DIR, "SRC-004_*.md"))):
        for line in read_text(p).splitlines():
            if line.startswith("## R-"):
                ruled |= set(OPEN_ID.findall(line))
    return opened - ruled, ruled & opened


def census_named() -> set[str]:
    out: set[str] = set()
    for p in sorted(glob.glob(CENSUS_GLOB)):
        out |= {x for x in STORY_ID.findall(read_text(p)) if x.startswith("S-")}
    return out


def read_cases(paths: list[str]) -> tuple[dict[str, list[str]], set[str], list[str]]:
    """Map story id -> case ids, the set of all case ids, and the files actually found."""
    by_story: dict[str, list[str]] = {}
    all_ids: set[str] = set()
    found: list[str] = []
    for p in paths:
        if not os.path.isfile(p):
            continue
        found.append(os.path.relpath(p, ROOT).replace("\\", "/"))
        rows = list(csv.DictReader(io.StringIO(read_text(p)), delimiter="\t"))
        for r in rows:
            cid = (r.get("CaseID") or "").strip()
            if not cid:
                continue
            all_ids.add(cid)
            ref = " ".join(v for k, v in r.items()
                           if k and re.search(r"story|bible", k, re.I) and v)
            if not ref:
                ref = " ".join(v for v in r.values() if isinstance(v, str))
            for sid in set(STORY_ID.findall(ref)):
                by_story.setdefault(sid, []).append(cid)
    for k in by_story:
        by_story[k] = sorted(set(by_story[k]))
    return by_story, all_ids, found


def existing_status() -> dict[str, tuple[str, str]]:
    if not os.path.isfile(LEDGER):
        return {}
    rows = csv.DictReader(io.StringIO(read_text(LEDGER)), delimiter="\t")
    return {r["ID"]: (r.get("Status", ""), r.get("StatusNote", "")) for r in rows if r.get("ID")}


def build() -> tuple[list[dict], dict]:
    bible = list(csv.DictReader(io.StringIO(read_text(BIBLE))))
    if not bible:
        die("the Bible is empty")
    by_id = {r["ID"]: r for r in bible}
    still_open, ruled = open_rows()
    named = census_named()
    sit, sit_ids, sit_found = read_cases(SIT_FILES)
    neg, neg_ids, neg_found = read_cases(NEG_FILES)
    prior = existing_status()

    rows: list[dict] = []
    for b in bible:
        rows.append({
            "Type": b["Type"], "ID": b["ID"], "ParentID": b["ParentID"],
            "Epic": b["ParentID"] if b["Type"] == "Story" else b["ID"],
            "Lane": lane_of(b["ID"]), "Title": b["Title"],
            "AcceptanceCriteria": b["AcceptanceCriteria"], "Priority": b["Priority"],
            "Estimate": b["Estimate"], "Milestone": b["Milestone"], "Labels": b["Labels"],
            "DependsOn": b["DependsOn"], "SourceRef": b["SourceRef"],
            "_text": " ".join((b["Description"], b["AcceptanceCriteria"], b["SourceRef"])),
            "Description": b["Description"],
        })
    for tid, parent, title, ac, deps, labels, paths, src in P1_TASKS:
        p = by_id[parent]
        rows.append({
            "Type": "Task", "ID": tid, "ParentID": parent,
            "Epic": parent if p["Type"] == "Epic" else p["ParentID"],
            "Lane": lane_of(parent), "Title": title, "AcceptanceCriteria": ac,
            "Priority": "MustHave", "Estimate": "", "Milestone": "1", "Labels": labels,
            "DependsOn": deps, "SourceRef": src + " GOAL_14", "_text": ac + " " + src,
            "Description": "", "_paths": paths.split(";"),
        })

    for r in rows:
        opens = sorted(set(OPEN_ID.findall(r["_text"])) & still_open)
        rul = sorted(set(OPEN_ID.findall(r["_text"])) & ruled)
        r["OpenRefs"] = " ".join(opens)
        r["RuledRefs"] = " ".join(f"{x}=SRC-004" for x in rul)
        st, note = prior.get(r["ID"], ("Backlog", ""))
        r["Status"], r["StatusNote"] = (st or "Backlog"), note
        if r["Type"] == "Epic":
            for k in ("Persona", "Classification", "Risk", "OwnedPaths", "Wave", "TestTrustLevel",
                      "SITCaseIDs", "NegativeCaseIDs", "EvidencePath"):
                r[k] = ""
        else:
            r["Persona"] = persona_of(r) if r["Type"] == "Story" else "operator"
            r["Classification"] = classification_of(r)
            if r["Type"] == "Task":
                r["Classification"] = "ZoneC-spec" if r["ID"] == "T-P1-09" else (
                    "ZoneA" if r["ID"] in ("T-P1-01", "T-P1-05") else "ZoneB")
            r["Risk"] = risk_of(r, opens)
            r["_owned"] = r.get("_paths") or owned_paths(r)
            r["OwnedPaths"] = ";".join(r["_owned"])
            r["TestTrustLevel"] = trust_of(r, named) if r["Type"] == "Story" else "spec"
            r["SITCaseIDs"] = " ".join(sit.get(r["ID"], []))
            r["NegativeCaseIDs"] = " ".join(neg.get(r["ID"], []))
            r["EvidencePath"] = f"docs/10 EngineeringLedger/evidence/{r['ID']}/"
        r["GoalRef"] = MILESTONE_GOAL.get(r["Milestone"], f"unwritten (phase {r['Milestone']} goal)")
        if r["Type"] == "Task":
            r["GoalRef"] = "GOAL_14"

    assign_waves(rows, by_id)
    meta = {"bible": bible, "sit_ids": sit_ids, "neg_ids": neg_ids, "sit_found": sit_found,
            "neg_found": neg_found, "still_open": still_open, "ruled": ruled}
    return rows, meta


def expand_deps(row: dict, rows_by_id: dict) -> list[str]:
    """A dependency on an epic means its work rows in milestones at or before this row's."""
    out: list[str] = []
    for d in row["DependsOn"].split():
        dr = rows_by_id.get(d)
        if dr is None:
            continue
        if dr["Type"] == "Epic":
            out += [x["ID"] for x in rows_by_id.values()
                    if x["Type"] != "Epic" and x["Epic"] == d
                    and int(x["Milestone"]) <= int(row["Milestone"]) and x["ID"] != row["ID"]
                    and x["ParentID"] != row["ID"]]
        else:
            out.append(d)
    return out


def assign_waves(rows: list[dict], _by_id: dict) -> None:
    """Greedy layering. Waves never span milestones; a row sits after every dependency it has
    (epic dependencies expanded, cycles broken by processing order); a row never shares a
    wave with a row whose OwnedPaths overlap its own. Wave numbers are global and ascending."""
    by_id = {r["ID"]: r for r in rows}
    work = [r for r in rows if r["Type"] != "Epic"]
    order = {r["ID"]: i for i, r in enumerate(rows)}
    wave_of: dict[str, int] = {}
    members: dict[int, list[dict]] = {}
    base = 0
    for m in sorted({int(r["Milestone"]) for r in work}):
        pending = [r for r in work if int(r["Milestone"]) == m]
        pending.sort(key=lambda r: order[r["ID"]])
        deps = {r["ID"]: [d for d in expand_deps(r, by_id)
                          if int(by_id[d]["Milestone"]) == m] for r in pending}
        placed: set[str] = set()
        top = base
        while pending:
            progress = False
            for r in list(pending):
                ds = [d for d in deps[r["ID"]] if d not in placed and d in deps]
                if ds and any(d in [p["ID"] for p in pending] for d in ds):
                    continue
                w = max([wave_of[d] for d in deps[r["ID"]] if d in wave_of] + [base]) + 1
                while any(overlaps(a, b) for o in members.get(w, [])
                          for a in o["_owned"] for b in r["_owned"]):
                    w += 1
                wave_of[r["ID"]] = w
                members.setdefault(w, []).append(r)
                placed.add(r["ID"])
                pending.remove(r)
                top = max(top, w)
                progress = True
            if not progress:   # a dependency cycle inside the milestone: break it in file order
                r = pending[0]
                deps[r["ID"]] = [d for d in deps[r["ID"]] if d in placed]
        base = top
    for r in work:
        r["Wave"] = str(wave_of[r["ID"]])


def render(rows: list[dict]) -> str:
    buf = io.StringIO()
    buf.write("\t".join(COLUMNS) + "\n")
    for r in rows:
        cells = []
        for c in COLUMNS:
            v = str(r.get(c, ""))
            if "\t" in v or "\n" in v or "\r" in v:
                die(f"{r['ID']}.{c} carries a tab or newline; the TSV would break")
            cells.append(v)
        buf.write("\t".join(cells) + "\n")
    return buf.getvalue()


def check(rows: list[dict], meta: dict, text: str) -> int:
    fails = 0

    def result(ok: bool, name: str, detail: str) -> None:
        nonlocal fails
        print(f"{'PASS' if ok else 'FAIL'}  {name:<26} {detail}")
        if not ok:
            fails += 1

    # 1 - regeneration is byte-identical to the file on disk (Status/StatusNote preserved)
    on_disk = read_text(LEDGER) if os.path.isfile(LEDGER) else ""
    diff = list(difflib.unified_diff(on_disk.splitlines(), text.splitlines(),
                                     "on-disk", "regenerated", lineterm="", n=0))
    result(not diff, "regenerate-no-diff", f"{len(diff)} diff lines")
    for line in diff[:40]:
        print("      " + line[:200])

    # 2 - counts
    bible = meta["bible"]
    bs = sum(1 for b in bible if b["Type"] == "Story")
    be = sum(1 for b in bible if b["Type"] == "Epic")
    ls_ = sum(1 for r in rows if r["Type"] == "Story")
    le = sum(1 for r in rows if r["Type"] == "Epic")
    lt = sum(1 for r in rows if r["Type"] == "Task")
    result(bs == ls_ and be == le, "count-equals-bible",
           f"Bible stories {bs} = ledger stories {ls_} · Bible epics {be} = ledger epics {le} "
           f"· plus {lt} Phase 1 Task rows (SRC-002 §12.2) · total rows {len(rows)}")

    # 3 - status law
    bad = [r["ID"] for r in rows if r["Status"] not in STATUSES]
    blocked_no_note = [r["ID"] for r in rows if r["Status"] == "Blocked" and not r["StatusNote"].strip()]
    done_no_evidence = [r["ID"] for r in rows if r["Status"] == "Done" and r["Type"] != "Epic"
                        and not os.path.isdir(os.path.join(ROOT, r["EvidencePath"]))]
    dist: dict[str, int] = {}
    for r in rows:
        dist[r["Status"]] = dist.get(r["Status"], 0) + 1
    result(not bad and not blocked_no_note and not done_no_evidence, "status-law",
           f"distribution {dict(sorted(dist.items()))} · illegal {len(bad)} · Blocked without "
           f"a note {len(blocked_no_note)} · Done without evidence {len(done_no_evidence)}")

    # 4 - SIT / negative case ids resolve
    dangling_sit = [(r["ID"], c) for r in rows for c in r.get("SITCaseIDs", "").split()
                    if c not in meta["sit_ids"]]
    dangling_neg = [(r["ID"], c) for r in rows for c in r.get("NegativeCaseIDs", "").split()
                    if c not in meta["neg_ids"]]
    filled = sum(1 for r in rows if r.get("SITCaseIDs"))
    result(not dangling_sit and not dangling_neg, "case-ids-resolve",
           f"SIT files found {meta['sit_found'] or 'NONE'} · negative files found "
           f"{meta['neg_found'] or 'NONE'} · rows with SIT cases {filled} · dangling SIT "
           f"{len(dangling_sit)} · dangling negative {len(dangling_neg)}")

    # 5 - DependsOn resolves and never points at a later milestone
    ids = {r["ID"]: r for r in rows}
    dangling = [(r["ID"], d) for r in rows for d in r["DependsOn"].split() if d not in ids]
    later = [(r["ID"], d) for r in rows for d in r["DependsOn"].split()
             if d in ids and int(ids[d]["Milestone"]) > int(r["Milestone"])]
    result(not dangling and not later, "depends-no-later-phase",
           f"dangling {len(dangling)} · pointing at a later milestone {len(later)}"
           + (f" {later[:5]}" if later else ""))

    # 6 - no two rows in one wave with overlapping OwnedPaths
    waves: dict[str, list[dict]] = {}
    for r in rows:
        if r["Type"] != "Epic":
            waves.setdefault(r["Wave"], []).append(r)
    pairs = 0
    clashes = []
    for w, rs in waves.items():
        for i in range(len(rs)):
            for j in range(i + 1, len(rs)):
                pairs += 1
                a, b = rs[i]["OwnedPaths"].split(";"), rs[j]["OwnedPaths"].split(";")
                if any(overlaps(x, y) for x in a for y in b):
                    clashes.append((w, rs[i]["ID"], rs[j]["ID"]))
    sizes = sorted(len(v) for v in waves.values())
    result(not clashes, "wave-owned-paths-disjoint",
           f"{len(waves)} waves · {pairs} same-wave pairs compared · overlapping {len(clashes)} "
           f"· wave size min {sizes[0]} max {sizes[-1]}")

    # 7 - waves never span milestones, and wave order follows milestone order
    span = {}
    for r in rows:
        if r["Type"] != "Epic":
            span.setdefault(r["Wave"], set()).add(r["Milestone"])
    multi = [w for w, ms in span.items() if len(ms) > 1]
    result(not multi, "wave-within-milestone", f"waves spanning >1 milestone {len(multi)}")

    # 8 - the header carries the names /ss anchors on, and a header lookup reads them
    head = text.split("\n", 1)[0].split("\t")
    need = ("ID", "Title", "Milestone", "Status", "DependsOn", "OwnedPaths", "SourceRef", "GoalRef")
    missing = [n for n in need if n not in head]
    result(not missing and len(head) == len(set(head)), "header-names",
           f"{len(head)} columns, unique; missing of {list(need)}: {missing}")

    # 9 - legal enum values in generated columns
    legal = {
        "Type": {"Epic", "Story", "Task"}, "Priority": {"MustHave", "ShouldHave", "CouldHave"},
        "Milestone": {str(i) for i in range(1, 9)},
        "Classification": {"", "ZoneA", "ZoneB", "ZoneC-spec"},
        "Risk": {"", "High", "Medium", "Low"},
        "TestTrustLevel": {"", "spec", "census-named", "needs-seam", "wall-clock", "aws-reasoned"},
    }
    illegal = [(r["ID"], c, r[c]) for r in rows for c, ok in legal.items() if r[c] not in ok]
    result(not illegal, "enum-legality", f"illegal cells {len(illegal)} {illegal[:5]}")
    return fails


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--check", action="store_true",
                    help="do not write; diff against the file and run every check")
    args = ap.parse_args()
    rows, meta = build()
    text = render(rows)
    if args.check:
        fails = check(rows, meta, text)
        print(f"\nchecks failed: {fails}")
        print("VERDICT:", "PASS" if fails == 0 else "FAIL")
        return 0 if fails == 0 else 1
    with open(LEDGER, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    print(f"wrote {os.path.relpath(LEDGER, ROOT)}: {len(rows)} rows, {len(COLUMNS)} columns")
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_architecture.py - the mechanical gate for docs/07 Architecture (GOAL_09, compressed per SRC-004 R-1).

    py "docs/07 Architecture/check_architecture.py"

Each check maps to one Definition-of-Done line in goals/GOAL_09_architecture.txt:

  C1 label      every document carries "compressed per SRC-004 R-1"
  C2 aws-label  every [AWS-..] tagged line carries the reasoned-not-observed label, every label sits
                on a tagged line, ids are unique; prints the two counts, which must match. Also flags
                an UNTAGGED line (outside code fences) where an AWS service is the subject of a
                behaviour verb ("SQS deletes", "the load balancer stops"). No exemption: a line that
                only points at a claim tagged elsewhere is reworded so it states no behaviour itself.
                Scans README.md too.
  C3 failures   every row of 08's failure table has a non-empty customer / operator / data-at-risk cell
  C4 decisions  02's "Still open" table == Article X (X.0-X.0g) minus SRC-004's ruled ids, and its
                "Closed by" table == Article X intersect SRC-004; both difference counts zero
  C5 memory     the ```memory block in 04 re-adds: host, limits, committed, headroom, one-off headroom
  C6 zone-c     no Zone C artefact in this folder (Terraform, CloudFormation, task definitions, YAML);
                content is scanned in every file whatever its extension, e.g. an ECS task-definition
                JSON body ("containerDefinitions") saved as .txt or with no extension
  C7 naming     the deployed environment is never called "production" (Art VIII.14)

Standard library only. Reads files; writes nothing. Exit 0 = every check passed, 1 = a check failed.
"""
from __future__ import annotations

import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
DOCS = [
    "for_llm/01_system_context.md", "for_llm/02_container.md", "for_llm/03_concurrency_model.md",
    "for_llm/04_deployment.md", "for_llm/05_surface_route_map.md", "for_llm/06_booking_sequence.md",
    "for_llm/07_state_machines.md", "for_llm/08_failure_modes.md",
    "for_humans/01_executive_overview.md", "for_humans/02_decisions_owed.md",
    "for_humans/03_the_deliberate_gaps.md", "README.md",
]
LABEL = "(reasoned, not observed)"
TAG = re.compile(r"\[AWS-[0-9A-Z]+-\d\d\]")
# An AWS service as the subject of a behaviour verb, at most three words apart. Deliberately narrow:
# a requirement ("the ECS stop timeout must exceed") or a noun phrase ("ECS services") does not match.
AWS_CLAIM = re.compile(
    r"\b(?:ALB|ECS|RDS|ElastiCache|SQS|SES|ECR|SSM|CloudWatch|load balancer)\b"
    r"(?:[\s`'*,]+[\w'()-]+){0,3}?[\s`*]+"
    r"(?:redelivers|throttles|rejects|evicts|drops|deletes|expires|stops|kills|restarts|bills|charges"
    r"|deregisters|marks|loses|comes back|retains|routes|retries|sends|starts|pulls|places|replaces"
    r"|caps|is billed|is charged|will)\b")
OPEN_ID = re.compile(r"OPEN-[A-Z0-9]+(?:-[A-Z0-9]+)*-\d+")

failures: list[str] = []


def read(rel_from_here: str) -> str:
    with open(os.path.join(HERE, rel_from_here), encoding="utf-8") as f:
        return f.read()


def read_root(*parts: str) -> str:
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return f.read()


def fail(check: str, msg: str) -> None:
    failures.append(f"{check}: {msg}")


def table_rows(text: str, after_heading: str) -> list[list[str]]:
    """Rows of the first markdown table after a heading line starting with after_heading."""
    lines = text.splitlines()
    try:
        start = next(i for i, l in enumerate(lines) if l.startswith(after_heading))
    except StopIteration:
        return []
    rows, in_table = [], False
    for l in lines[start + 1:]:
        if l.startswith("|"):
            in_table = True
            cells = [c.strip() for c in l.strip().strip("|").split("|")]
            rows.append(cells)
        elif in_table:
            break
        elif l.startswith("## "):
            break
    return rows


# ---- C1 ---------------------------------------------------------------------------------------
missing = [d for d in DOCS if not os.path.isfile(os.path.join(HERE, d))]
for d in missing:
    fail("C1", f"{d} does not exist")
texts = {d: read(d) for d in DOCS if d not in missing}
for d, t in texts.items():
    if "compressed per SRC-004 R-1" not in t:
        fail("C1", f"{d} lacks the 'compressed per SRC-004 R-1' label")
print(f"C1 label      {len(texts) - sum(1 for f in failures if f.startswith('C1'))} of {len(DOCS)} documents labelled")

# ---- C2 ---------------------------------------------------------------------------------------
tags_total = labels_total = 0
seen: dict[str, str] = {}
for d, t in texts.items():
    for n, line in enumerate(t.splitlines(), 1):
        tags = TAG.findall(line)
        nlab = line.count(LABEL)
        tags_total += len(tags)
        labels_total += nlab
        if tags and nlab != len(tags):
            fail("C2", f"{d}:{n} carries {len(tags)} AWS tag(s) and {nlab} label(s)")
        if nlab and not tags:
            fail("C2", f"{d}:{n} carries the label with no AWS tag")
        for tg in tags:
            if tg in seen:
                fail("C2", f"{tg} used twice ({seen[tg]} and {d}:{n})")
            seen[tg] = f"{d}:{n}"
untagged = 0
for d, t in texts.items():
    fence = False
    for n, line in enumerate(t.splitlines(), 1):
        if line.startswith("```"):
            fence = not fence
            continue
        if fence or TAG.search(line) or not AWS_CLAIM.search(line):
            continue
        untagged += 1
        fail("C2", f"{d}:{n} states AWS behaviour with no [AWS-..] tag: {AWS_CLAIM.search(line).group(0)!r}")
print(f"C2 aws-label  {tags_total} tagged AWS-behaviour statements | {labels_total} labels | "
      f"{'MATCH' if tags_total == labels_total else 'MISMATCH'} | {untagged} untagged AWS-behaviour lines")
if tags_total != labels_total:
    fail("C2", f"counts differ: {tags_total} tags vs {labels_total} labels")

# ---- C3 ---------------------------------------------------------------------------------------
fm = texts.get("for_llm/08_failure_modes.md", "")
rows = table_rows(fm, "## Failure table")
if not rows:
    fail("C3", "no table under '## Failure table'")
else:
    header = [h.lower() for h in rows[0]]
    want = ["customer sees", "operator sees", "data at risk"]
    idx = [header.index(w) if w in header else -1 for w in want]
    if -1 in idx:
        fail("C3", f"failure table header lacks one of {want}: {rows[0]}")
    body = [r for r in rows[2:]]
    empty = 0
    for r in body:
        for w, i in zip(want, idx):
            cell = r[i] if i < len(r) else ""
            if cell.strip("*_ ") in ("", "-", "—", "–", "n/a", "N/A"):
                empty += 1
                fail("C3", f"row {r[0]} has an empty '{w}' cell")
    print(f"C3 failures   {len(body)} failure rows | {empty} empty cells")
    if not any("SES" in r[1] for r in body[:1]):
        fail("C3", "the first failure row is not SES (the goal file requires SES first)")

# ---- C4 ---------------------------------------------------------------------------------------
const = read_root("CONSTITUTION.md")
a = const.index("### X.0 ")
b = const.index("**Historical record")
art_x = set()
for line in const[a:b].splitlines():
    m = re.match(r"^\|\s*`(" + OPEN_ID.pattern + r")`", line)
    if m:
        art_x.add(m.group(1))
src4 = read_root("docs", "00 SourceOfTruth", "SRC-004_client_rulings_2026-10-18.md")
ruled = set()
for line in src4.splitlines():
    if line.startswith("## R-"):
        ruled.update(OPEN_ID.findall(line))
dec = texts.get("for_humans/02_decisions_owed.md", "")
still = {OPEN_ID.search(r[0]).group(0) for r in table_rows(dec, "## Still open")[2:] if OPEN_ID.search(r[0])}
closed = {OPEN_ID.search(r[0]).group(0) for r in table_rows(dec, "## Closed by")[2:] if OPEN_ID.search(r[0])}
exp_open = art_x - ruled
exp_closed = art_x & ruled
miss_open, extra_open = exp_open - still, still - exp_open
miss_closed, extra_closed = exp_closed - closed, closed - exp_closed
for x in sorted(miss_open):
    fail("C4", f"{x} is open in Article X and absent from 'Still open'")
for x in sorted(extra_open):
    fail("C4", f"{x} is in 'Still open' but is not an open Article X row (or SRC-004 ruled it)")
for x in sorted(miss_closed | extra_closed):
    fail("C4", f"{x} disagrees between 'Closed by' and Article X ∩ SRC-004")
print(f"C4 decisions  Article X rows {len(art_x)} | SRC-004 ruled {len(ruled)} | expected open {len(exp_open)} | "
      f"listed open {len(still)} | missing {len(miss_open)} | extra {len(extra_open)} | "
      f"closed listed {len(closed)} (expected {len(exp_closed)})")

# ---- C5 ---------------------------------------------------------------------------------------
dep = texts.get("for_llm/04_deployment.md", "")
m = re.search(r"```memory\n(.*?)```", dep, re.S)
if not m:
    fail("C5", "no ```memory block in 04_deployment.md")
else:
    rowsm = {}
    groups: dict[str, list[tuple[int, int]]] = {}
    for line in m.group(1).splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        kind, item, best, worst = [c.strip() for c in line.split("|")]
        groups.setdefault(kind, []).append((int(best), int(worst)))
        if kind == "stated":
            rowsm[item] = (int(best), int(worst))
    s = lambda k: tuple(sum(v[i] for v in groups.get(k, [])) for i in (0, 1))
    host, limits, phys, oneoff = s("host"), s("limit"), s("physical"), s("oneoff")
    committed = (host[0] + limits[0], host[1] + limits[1])
    headroom = (phys[0] - committed[0], phys[1] - committed[1])
    oneoff_h = (headroom[0] - oneoff[0], headroom[1] - oneoff[1])
    computed = {"host_total": host, "limits_total": limits, "steady_committed": committed,
                "steady_headroom": headroom, "oneoff_headroom": oneoff_h}
    for k, v in computed.items():
        if rowsm.get(k) != v:
            fail("C5", f"stated {k} = {rowsm.get(k)} but the rows sum to {v}")
    fits = oneoff_h[1] >= 0 and headroom[1] >= 0
    print(f"C5 memory     host {host[0]}-{host[1]} + limits {limits[0]} = committed {committed[0]}-{committed[1]} MiB "
          f"of {phys[0]} | headroom {headroom[1]}-{headroom[0]} | during one-off {oneoff_h[1]}-{oneoff_h[0]} | "
          f"{'FITS (on estimates)' if fits else 'DOES NOT FIT'}")
    # Not fitting is reported as the result (DoD line 1), not as a gate failure.

# ---- C6 ---------------------------------------------------------------------------------------
bad_ext = (".tf", ".tfvars", ".yml", ".yaml", ".template")
bad_txt = ("AWSTemplateFormatVersion", 'resource "aws_', '"containerDefinitions"', "aws ecs create",
           "aws sqs create", "aws elbv2 create")
created = []
for base, dirs, files in os.walk(HERE):
    dirs[:] = [x for x in dirs if x != "__pycache__"]
    for f in files:
        rel = os.path.relpath(os.path.join(base, f), HERE).replace("\\", "/")
        created.append(rel)
        if f.lower().endswith(bad_ext) or "task-definition" in f.lower() or "taskdef" in f.lower():
            fail("C6", f"{rel} looks like a Zone C artefact")
        if os.path.join(base, f) == os.path.abspath(__file__):
            continue  # this script names the patterns it looks for
        with open(os.path.join(base, f), "rb") as fh:
            t = fh.read().decode("utf-8", errors="ignore")
        for bt in bad_txt:
            if bt in t:
                fail("C6", f"{rel} contains Zone C content '{bt}'")
print(f"C6 zone-c     {len(created)} files in docs/07 Architecture: {', '.join(sorted(created))}")

# ---- C7 ---------------------------------------------------------------------------------------
hits = [(d, n) for d, t in texts.items() for n, l in enumerate(t.splitlines(), 1)
        if re.search(r"\bproduction\b", l, re.I)]
for d, n in hits:
    fail("C7", f"{d}:{n} uses the word 'production'")
print(f"C7 naming     {len(hits)} uses of 'production'")

print()
if failures:
    for f in failures:
        print("FAIL  " + f)
    print(f"VERDICT: FAIL - {len(failures)} finding(s)")
    sys.exit(1)
print("VERDICT: PASS - every check above passed")
sys.exit(0)

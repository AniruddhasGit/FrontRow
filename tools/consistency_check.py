#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""consistency_check.py — the cheap mechanical layer of FrontRow's two-layer check.

`CONSTITUTION.md` Art IX.6 defines what this is for. It answers exactly ONE question:

    does every cross-reference actually resolve?

Dangling `FR-ADR-nnn` ids. Dangling `OPEN-` ids. A `SRC-001 §n` citation pointing at a
clause that was never written. An erratum claimed in `SRC-003` and never filed against the
source it corrects. A frozen source whose bytes moved under its own fingerprint. A prep-queue
row with no Status — the "I reported an action I did not perform" breach, which on the prior
project a small script caught four times after an expensive adversarial agent had spent real
effort finding them.

It CANNOT see a semantic contradiction between two documents that each resolve perfectly well
on their own. That is the expensive layer: `docs/12 DesignReview/`, GOAL_13.

    py tools/consistency_check.py             run every rule against the repo
    py tools/consistency_check.py --selftest  plant a real violation of each rule, prove it fires

Exit codes
    0   every rule passed (or skipped cleanly)
    1   at least one rule failed
    2   the tool itself errored

Most of `docs/` is still empty. A rule whose subject does not exist yet prints SKIP with the
reason and does not gate — the tool has to be useful today, not only at the end.

`--selftest` is the point of the file. For every rule it copies the repo to a scratch
directory, plants a REAL violation of that rule, re-runs, and requires that rule's failure
count to RISE. It measures by DELTA, so it still red-proofs correctly on a repository that is
already red — which is precisely the day you need it. A check nobody has watched fail is
decoration.

Standard library only. No credentials, no network, no shelling out: sha256 is computed here.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import os
import re
import shutil
import sys
import tempfile
import traceback

TEXT_EXT = {".md", ".txt", ".tsv", ".csv", ".json", ".sql", ".yaml", ".yml"}
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build"}

# What this governs is the DOCUMENT SET — artifacts that make claims about each other.
# Deliberately out of scope:
#   tools/       is code, and THIS FILE carries planted violations as string literals;
#                scanning it would make the checker fail on its own selftest fixtures.
#   handoffs/    and PROGRESS.md are narrative. Their job is to record what happened,
#                INCLUDING defects. A handoff that writes "claims FR-ADR-994 is filed" is
#                reporting a defect, not committing one, and flagging it would punish exactly
#                the honesty Art VII requires.
SKIP_PREFIXES = ("tools/", "handoffs/")
SKIP_PATHS = {"PROGRESS.md"}

SRC_DIR = ("docs", "00 SourceOfTruth")
ADR_DIR = ("docs", "01 ADR", "all-ADRs")
LEDGER = ("docs", "01 ADR", "ADR_DECISION_RELEASE_LEDGER.tsv")
ADR_README = ("docs", "01 ADR", "README.md")
DOCS_README = ("docs", "README.md")
PREP_QUEUE = ("docs", "30 Deployment", "AWS_PREP_QUEUE.md")
CONSTITUTION = ("CONSTITUTION.md",)

SRC_FILES = {
    "SRC-001": "SRC-001_requirements_2026-08-14.md",
    "SRC-002": "SRC-002_build_mandate_2026-08-14.md",
    "SRC-003": "SRC-003_client_rulings_2026-08-14.md",
}


# ── plumbing ────────────────────────────────────────────────────────────────────
class Rule:
    """One rule. Independently reportable: its own status, its own count, its own detail."""

    def __init__(self, num: int, key: str, what: str) -> None:
        self.num = num
        self.key = key
        self.what = what
        self.failures: list[str] = []
        self.skip_reason: str | None = None
        self.checked = 0          # how many things this rule looked at
        self.unit = "reference"   # what it looked at, for the rate line
        self.extra = ""           # optional trailing note on the summary line

    def fail(self, detail: str) -> None:
        self.failures.append(detail)

    def skip(self, reason: str) -> None:
        self.skip_reason = reason

    @property
    def status(self) -> str:
        if self.failures:
            return "FAIL"
        if self.skip_reason is not None:
            return "SKIP"
        return "PASS"

    @property
    def rate(self) -> str:
        if self.skip_reason is not None:
            return self.skip_reason
        n, t = len(self.failures), self.checked
        unit = self.unit + ("" if t == 1 else "s")
        if n:
            return f"{n} of {t} {unit} unresolved{self.extra}"
        return f"{t} of {t} {unit} resolve{self.extra}"


def read(path: str) -> str:
    with open(path, encoding="utf-8", errors="replace") as fh:
        return fh.read()


def j(root: str, *parts: str) -> str:
    return os.path.join(root, *parts)


def rel(root: str, p: str) -> str:
    return os.path.relpath(p, root).replace("\\", "/")


def corpus_of(root: str) -> dict[str, str]:
    """Every governed text file, keyed by forward-slash relative path."""
    out: dict[str, str] = {}
    for base, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for f in files:
            if os.path.splitext(f)[1].lower() not in TEXT_EXT:
                continue
            p = rel(root, os.path.join(base, f))
            if p in SKIP_PATHS or p.startswith(SKIP_PREFIXES):
                continue
            out[p] = read(os.path.join(base, f))
    return out


def md_tables(text: str) -> list[tuple[list[str], list[list[str]], list[int]]]:
    """Every GitHub-flavoured markdown table: (header cells, data rows, source line numbers)."""
    lines = text.split("\n")
    tables = []
    i = 0
    while i < len(lines) - 1:
        if lines[i].lstrip().startswith("|") and re.match(
                r"^\s*\|[\s:|-]*\|\s*$", lines[i + 1]) and "-" in lines[i + 1]:
            header = [c.strip() for c in lines[i].strip().strip("|").split("|")]
            rows, nums = [], []
            k = i + 2
            while k < len(lines) and lines[k].lstrip().startswith("|"):
                rows.append([c.strip() for c in lines[k].strip().strip("|").split("|")])
                nums.append(k + 1)
                k += 1
            tables.append((header, rows, nums))
            i = k
        else:
            i += 1
    return tables


def clause_anchors(text: str) -> set[str]:
    """Every `§n` a source actually DEFINES.

    Three shapes are used across SRC-001 and SRC-002 and all three are anchors:
        ## §5 — What we want the system to do        heading
        **§5.2.1** Show a visual seat map…           bold clause at line start
        | **§4.1** Frontend | React + Vite …         bold clause in a table cell
    A `§n` appearing mid-sentence is a CITATION, never a definition, and is deliberately
    not collected — otherwise every dangling citation would define its own target.
    """
    a = set(re.findall(r"^#{1,6}\s*§([0-9][0-9.]*)", text, re.M))
    a |= set(re.findall(r"^\*\*§([0-9][0-9.]*)", text, re.M))
    a |= set(re.findall(r"^\|\s*\*\*§([0-9][0-9.]*)\*\*", text, re.M))
    return {x.rstrip(".") for x in a}


# ── the rules ───────────────────────────────────────────────────────────────────
def rule_1_adr(root: str, corpus: dict[str, str]) -> Rule:
    """Every FR-ADR-### resolves to a file AND a ledger row."""
    r = Rule(1, "adr-reference",
             "every `FR-ADR-###` resolves to a file in all-ADRs/ and a row in the ledger")
    r.unit = "FR-ADR reference"

    adr_dir = j(root, *ADR_DIR)
    ledger_p = j(root, *LEDGER)
    adr_files = ({f[:-3] for f in os.listdir(adr_dir) if f.endswith(".md")}
                 if os.path.isdir(adr_dir) else set())
    ledger_ids: set[str] = set()
    if os.path.isfile(ledger_p):
        rows = list(csv.DictReader(io.StringIO(read(ledger_p)), delimiter="\t"))
        key = "adr_id" if rows and "adr_id" in rows[0] else (
            list(rows[0])[0] if rows else "adr_id")
        ledger_ids = {(row.get(key) or "").strip() for row in rows} - {""}

    # Scope is exactly as specified: docs/, CLAUDE.md, CONSTITUTION.md.
    scoped = {f: t for f, t in corpus.items()
              if f.startswith("docs/") or f in ("CLAUDE.md", "CONSTITUTION.md")}
    seen: dict[str, list[str]] = {}
    for f, t in scoped.items():
        for n in sorted(set(re.findall(r"\bFR-ADR-(\d{3})\b", t))):
            seen.setdefault("FR-ADR-" + n, []).append(f)

    if not seen:
        r.skip("no `FR-ADR-###` is referenced anywhere in docs/, CLAUDE.md or CONSTITUTION.md yet")
        return r

    r.checked = sum(len(v) for v in seen.values())
    for aid in sorted(seen):
        for f in seen[aid]:
            miss = []
            if aid not in adr_files:
                miss.append("no file `docs/01 ADR/all-ADRs/%s.md`" % aid)
            if aid not in ledger_ids:
                miss.append("no row in ADR_DECISION_RELEASE_LEDGER.tsv")
            if miss:
                r.fail(f"{f}: references {aid} — " + " and ".join(miss))
    r.extra = f" (ledger rows: {len(ledger_ids)} · ADR files: {len(adr_files)})"
    return r


# An Article X / SRC-003 open-decision id.
#
# Widened 2026-08-15. The original `OPEN-[A-Z]+-\d+` could not match a subject containing a
# SECOND HYPHEN (SEATMAP-DEGRADED) or a DIGIT (CACHE503), so ids of those two shapes were
# invisible to this rule in BOTH directions at once: invisible as filed rows when harvested from
# CONSTITUTION.md, and invisible as references when scanned in the corpus. The two blindnesses
# cancelled into a green line. `OPEN-CACHE503-01` was a genuinely filed row in Art X.0b whose
# every reference went unchecked. Raised by the PRD in its S8.7 and closed here.
#
# The lesson is the shape, not the characters: a rule that derives BOTH its known set and its
# referenced set through ONE narrow pattern cannot report the ids that pattern cannot see -- it
# has no vocabulary for them, so widening is not a tightening of an existing check but the only
# way it can speak about them at all. Red-proofed by the `open-reference` plants in SELFTESTS,
# two of which use exactly the shapes the old pattern missed.
OPEN_ID = r"OPEN-[A-Z0-9]+(?:-[A-Z0-9]+)*-\d+"


def rule_2_open(root: str, corpus: dict[str, str]) -> Rule:
    """Every OPEN-XXX-nn resolves to an Article X row or an SRC-003 section."""
    r = Rule(2, "open-reference",
             "every `OPEN-XXX-nn` resolves to a CONSTITUTION Article X row or an SRC-003 section")
    r.unit = "OPEN reference"

    const_p = j(root, *CONSTITUTION)
    src3_p = j(root, *SRC_DIR, SRC_FILES["SRC-003"])
    if not os.path.isfile(const_p) and not os.path.isfile(src3_p):
        r.skip("neither CONSTITUTION.md nor SRC-003 exists — nothing defines an OPEN id")
        return r

    art_x: set[str] = set()
    if os.path.isfile(const_p):
        # An Article X row is a table row whose first cell is the backticked id.
        art_x = set(re.findall(r"^\|\s*`(" + OPEN_ID + r")`", read(const_p), re.M))
    src3: set[str] = set()
    if os.path.isfile(src3_p):
        src3 = set(re.findall(r"^#{1,6}\s*`(" + OPEN_ID + r")`", read(src3_p), re.M))
    known = art_x | src3

    seen: dict[str, list[str]] = {}
    for f, t in corpus.items():
        for oid in sorted(set(re.findall(r"\b(" + OPEN_ID + r")\b", t))):
            seen.setdefault(oid, []).append(f)
    if not seen:
        r.skip("no `OPEN-XXX-nn` id is referenced anywhere")
        return r

    r.checked = sum(len(v) for v in seen.values())
    for oid in sorted(seen):
        if oid in known:
            continue
        for f in seen[oid]:
            r.fail(f"{f}: references {oid}, which is neither a row in CONSTITUTION.md "
                   f"Article X nor a section in SRC-003")
    r.extra = f" ({len(art_x)} Article X rows · {len(src3)} SRC-003 sections)"
    return r


def rule_3_clauses(root: str, corpus: dict[str, str]) -> Rule:
    """Every `SRC-001 §n` / `SRC-002 §n` citation resolves to a real clause anchor."""
    r = Rule(3, "source-citation",
             "every `SRC-001 §n` / `SRC-002 §n` citation resolves to a clause that exists")
    r.unit = "clause citation"

    anchors: dict[str, set[str]] = {}
    for sid in ("SRC-001", "SRC-002"):
        p = j(root, *SRC_DIR, SRC_FILES[sid])
        if os.path.isfile(p):
            anchors[sid] = clause_anchors(read(p))
    if not anchors:
        r.skip("neither SRC-001 nor SRC-002 exists in docs/00 SourceOfTruth/")
        return r

    cite = re.compile(r"\b(SRC-00[12])\s*§\s*([0-9][0-9.]*)")
    for f in sorted(corpus):
        for m in cite.finditer(corpus[f]):
            sid, cl = m.group(1), m.group(2).rstrip(".")
            if sid not in anchors:
                continue  # that source is not on disk; rule 5/other rules own that
            r.checked += 1
            if cl not in anchors[sid]:
                line = corpus[f].count("\n", 0, m.start()) + 1
                r.fail(f"{f}:{line}: cites `{sid} §{cl}` — no such clause anchor in "
                       f"{SRC_FILES[sid]}")
    if not r.checked:
        r.skip("no `SRC-001 §n` / `SRC-002 §n` citation appears anywhere yet")
        return r
    r.extra = " (" + " · ".join(f"{s}: {len(a)} anchors" for s, a in sorted(anchors.items())) + ")"
    return r


def _errata_in_source(text: str) -> dict[str, str]:
    """`E-n` -> the `§clause` it corrects, as filed in a source's own §E section."""
    if not re.search(r"^#{1,6}\s*§E\b", text, re.M):
        return {}
    body = text[re.search(r"^#{1,6}\s*§E\b", text, re.M).start():]
    return {m.group(1): m.group(2)
            for m in re.finditer(r"^\*\*`(E-\d+)`\s*[—–-]\s*`§([0-9][0-9.]*)`", body, re.M)}


def _errata_in_src003(text: str) -> dict[str, dict[str, str]]:
    """`SRC-00n` -> {`E-n`: `§clause`}, as tabled in SRC-003."""
    out: dict[str, dict[str, str]] = {}
    for m in re.finditer(r"^#{1,6}\s*Errata filed against\s*`(SRC-\d{3})`", text, re.M):
        target = m.group(1)
        nxt = re.search(r"^#{1,6}\s", text[m.end():], re.M)
        block = text[m.end(): m.end() + (nxt.start() if nxt else len(text))]
        out[target] = {r1: r2 for r1, r2 in re.findall(
            r"^\|\s*`(E-\d+)`\s*\|\s*`§([0-9][0-9.]*)`", block, re.M)}
    return out


def rule_4_errata(root: str, corpus: dict[str, str]) -> Rule:
    """SRC-003's errata tables and the sources' §E sections agree, both directions."""
    r = Rule(4, "erratum-crossref",
             "every erratum tabled in SRC-003 is filed in the target's §E section, and vice versa")
    r.unit = "erratum claim"

    src3_p = j(root, *SRC_DIR, SRC_FILES["SRC-003"])
    if not os.path.isfile(src3_p):
        r.skip("SRC-003 does not exist — nothing tables an erratum")
        return r
    claimed = _errata_in_src003(read(src3_p))
    if not claimed:
        r.skip("SRC-003 has no `Errata filed against \\`SRC-00n\\`` table")
        return r

    filed: dict[str, dict[str, str]] = {}
    for sid in sorted(set(claimed) | {"SRC-001", "SRC-002"}):
        p = j(root, *SRC_DIR, SRC_FILES.get(sid, ""))
        if SRC_FILES.get(sid) and os.path.isfile(p):
            filed[sid] = _errata_in_source(read(p))

    for sid in sorted(claimed):
        if sid not in filed:
            r.checked += len(claimed[sid])
            for eid in sorted(claimed[sid]):
                r.fail(f"SRC-003 tables {eid} against {sid}, which is not on disk")
            continue
        want, have = claimed[sid], filed[sid]
        # direction A — SRC-003 claims it, the source must carry it
        for eid in sorted(want):
            r.checked += 1
            if eid not in have:
                r.fail(f"SRC-003 tables {eid} against {sid} `§{want[eid]}` — "
                       f"{SRC_FILES[sid]} §E does not carry it")
            elif have[eid] != want[eid]:
                r.fail(f"{eid}: SRC-003 says it corrects {sid} `§{want[eid]}`, "
                       f"{SRC_FILES[sid]} §E says `§{have[eid]}`")
        # direction B — the source carries it, SRC-003 must table it
        for eid in sorted(have):
            if eid in want:
                continue
            r.checked += 1
            r.fail(f"{SRC_FILES[sid]} §E files {eid} against `§{have[eid]}` — "
                   f"SRC-003's errata table for {sid} does not")

    # The fingerprint record states an errata count per source. A count is a claim too.
    fp_p = j(root, *SRC_DIR, "fingerprints.json")
    if os.path.isfile(fp_p):
        try:
            import json
            fp = json.loads(read(fp_p))
        except Exception as exc:                                  # noqa: BLE001
            r.fail(f"fingerprints.json is not readable JSON ({exc})")
            fp = {}
        for fn, rec in sorted(fp.get("sources", {}).items()):
            sid = fn.split("_")[0]
            if "errata" not in rec or sid not in filed:
                continue
            r.checked += 1
            if int(rec["errata"]) != len(filed[sid]):
                r.fail(f"fingerprints.json records {rec['errata']} errata for {sid}; "
                       f"its §E section carries {len(filed[sid])}")
    if not r.checked:
        r.skip("SRC-003 tables no errata")
    return r


def rule_5_fingerprints(root: str, corpus: dict[str, str]) -> Rule:
    """fingerprints.json matches the bytes on disk. sha256 computed in-process."""
    r = Rule(5, "fingerprint", "every frozen source hashes to the sha256 recorded for it")
    r.unit = "fingerprint assertion"

    fp_p = j(root, *SRC_DIR, "fingerprints.json")
    if not os.path.isfile(fp_p):
        r.skip("docs/00 SourceOfTruth/fingerprints.json does not exist")
        return r
    import json
    try:
        fp = json.loads(read(fp_p))
    except Exception as exc:                                      # noqa: BLE001
        r.checked = 1
        r.fail(f"fingerprints.json is not readable JSON: {exc}")
        return r

    sources = fp.get("sources", {})
    if not sources:
        r.skip("fingerprints.json declares no sources")
        return r

    for fn, rec in sorted(sources.items()):
        r.checked += 1
        path = j(root, *SRC_DIR, fn)
        if not os.path.isfile(path):
            r.fail(f"{fn} is fingerprinted but is not on disk")
            continue
        with open(path, "rb") as fh:
            raw = fh.read()
        live = hashlib.sha256(raw).hexdigest()
        if live != rec.get("sha256"):
            r.fail(f"{fn} changed — recorded {str(rec.get('sha256'))[:16]}…, "
                   f"live {live[:16]}…. Every artifact derived from it is INVALID and must "
                   f"be re-derived, never silently reused")
            continue
        if "bytes" in rec and int(rec["bytes"]) != len(raw):
            r.fail(f"{fn}: hash matches but fingerprints.json records {rec['bytes']} bytes "
                   f"and the file is {len(raw)}")

    # fingerprints.sha256 is the sha256sum -c companion; it must agree with the JSON.
    side_p = j(root, *SRC_DIR, "fingerprints.sha256")
    if os.path.isfile(side_p):
        side = {m.group(2): m.group(1) for m in
                re.finditer(r"^([0-9a-f]{64})\s+\*?(.+?)\s*$", read(side_p), re.M)}
        for fn, rec in sorted(sources.items()):
            r.checked += 1
            if fn not in side:
                r.fail(f"{fn} is in fingerprints.json but not in fingerprints.sha256")
            elif side[fn] != rec.get("sha256"):
                r.fail(f"{fn}: fingerprints.sha256 and fingerprints.json disagree on the hash")
        for fn in sorted(set(side) - set(sources)):
            r.checked += 1
            r.fail(f"{fn} is in fingerprints.sha256 but not in fingerprints.json")
    return r


def rule_6_readme_paths(root: str, corpus: dict[str, str]) -> Rule:
    """Every path the docs/README.md folder table quotes exists in the repo tree."""
    r = Rule(6, "readme-paths", "every path quoted in the docs/README.md folder table exists")
    r.unit = "path claim"

    p = j(root, *DOCS_README)
    if not os.path.isfile(p):
        r.skip("docs/README.md does not exist")
        return r
    text = read(p)
    table = None
    for header, rows, nums in md_tables(text):
        low = [h.lower().strip("* ") for h in header]
        if "folder" in low and "state" in low:
            table = (header, rows, nums)
            break
    if table is None:
        r.skip("docs/README.md has no folder table (a header row of `# | Folder | … | State`)")
        return r
    header, rows, nums = table

    # every relative path in the tree, for suffix resolution
    tree: set[str] = set()
    for base, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for name in list(dirs) + files:
            tree.add(rel(root, os.path.join(base, name)))

    def exists(tok: str) -> bool:
        tok = tok.strip().rstrip("/")
        if not tok:
            return False
        if os.path.exists(j(root, *tok.split("/"))):
            return True
        if os.path.exists(j(root, "docs", *tok.split("/"))):
            return True
        return any(x == tok or x.endswith("/" + tok) for x in tree)

    # a token is a PATH CLAIM if it carries a separator or a file extension, or names a
    # frozen source by id. `/ss` is a slash command and `FR-ADR-nnn` is an id pattern.
    EXT = re.compile(r"^[\w .+-]+\.(md|tsv|csv|json|sql|py|css|ya?ml|txt|html|sh|toml|ini)$", re.I)
    SLASH_CMD = re.compile(r"^/[a-z]{1,12}$")
    deferred = 0

    for cells, lineno in zip(rows, nums):
        if not cells or all(not c for c in cells):
            continue
        state = cells[-1].strip().strip("*` ").lower()
        live = state == "written"
        # the row's own folder(s): "05 B" + "**DesignSystem**" -> docs/05 B DesignSystem
        combined = " | ".join(cells[:2])
        pairs = re.findall(r"(\d{2}(?:\s+B)?)\s*\|?\s*\*\*([^*|]+?)\s*\*\*", combined)
        for num, name in pairs:
            want = f"docs/{num} {name}"
            r.checked += 1
            if not os.path.isdir(j(root, "docs", f"{num} {name}")):
                r.fail(f"docs/README.md:{lineno}: the table names folder `{want}`, "
                       f"which is not a directory in the repo tree")
        for tok in re.findall(r"`([^`]+)`", " | ".join(cells)):
            t = tok.strip()
            if SLASH_CMD.match(t):
                continue
            is_src = re.match(r"^SRC-\d{3}$", t)
            if not (is_src or "/" in t or EXT.match(t)):
                continue
            if not live:
                # The State cell says the folder is not written yet, so the path is a plan,
                # not a claim about what exists. Counted, reported, never gated — the rule
                # starts biting the moment the row flips to `written`.
                deferred += 1
                continue
            r.checked += 1
            ok = (any(x.startswith("docs/00 SourceOfTruth/" + t) for x in tree)
                  if is_src else exists(t))
            if not ok:
                r.fail(f"docs/README.md:{lineno}: the table quotes `{t}`, "
                       f"which does not exist in the repo tree")
    if not r.checked:
        r.skip("the folder table quotes no resolvable path yet")
        return r
    if deferred:
        r.extra = (f" · {deferred} path claim(s) in rows the table itself marks not-yet-written, "
                   f"deferred")
    return r


def rule_7_prep_queue(root: str, corpus: dict[str, str]) -> Rule:
    """Every AWS prep-queue row carries a non-empty Status."""
    r = Rule(7, "prep-queue-status", "every row of AWS_PREP_QUEUE.md carries a non-empty Status")
    r.unit = "queue row"

    p = j(root, *PREP_QUEUE)
    if not os.path.isfile(p):
        r.skip("docs/30 Deployment/AWS_PREP_QUEUE.md does not exist")
        return r
    text = read(p)
    target = None
    for header, rows, nums in md_tables(text):
        low = [h.lower().strip("* `") for h in header]
        if "status" in low:
            target = (low.index("status"), header, rows, nums)
            break
    if target is None:
        r.skip("AWS_PREP_QUEUE.md has no table with a `Status` column")
        return r
    idx, header, rows, nums = target

    for cells, lineno in zip(rows, nums):
        if len(cells) <= idx:
            r.checked += 1
            r.fail(f"AWS_PREP_QUEUE.md:{lineno}: row has {len(cells)} cells, "
                   f"so it has no Status column at all")
            continue
        r.checked += 1
        value = cells[idx].strip().strip("*`_ ").strip()
        if value in ("", "-", "—", "–", "?", "TBD", "n/a", "N/A"):
            item = re.sub(r"[*`]", "", cells[1] if len(cells) > 1 else "")[:60]
            r.fail(f"AWS_PREP_QUEUE.md:{lineno}: row {cells[0] or '?'} "
                   f"({item.strip() or 'unnamed'}…) has an empty Status. A row with no Status "
                   f"is a request nobody has answered — the class the check exists for")
    if not r.checked:
        r.skip("the prep queue table has no rows yet")
    return r


def _documented_columns(text: str) -> list[str]:
    """The ledger column order as documented in docs/01 ADR/README.md.

    Three shapes are accepted, first that yields three or more names wins:
      1. a fenced block whose lines are the tab- or newline-separated column names;
      2. a markdown table with a `Column` header — the cells of that column, in row order;
      3. a numbered or bulleted list of backticked names.
    """
    for m in re.finditer(r"```[a-zA-Z]*\n(.*?)```", text, re.S):
        body = m.group(1).strip()
        if "\t" in body:
            names = [c.strip() for c in body.split("\n")[0].split("\t") if c.strip()]
        else:
            names = [ln.strip().strip("`,") for ln in body.split("\n") if ln.strip()]
        names = [n for n in names if re.fullmatch(r"[a-z0-9_]+", n or "")]
        if len(names) >= 3:
            return names
    for header, rows, _ in md_tables(text):
        low = [h.lower().strip("* `") for h in header]
        for want in ("column", "column name", "field"):
            if want in low:
                i = low.index(want)
                names = [re.sub(r"[`*]", "", rrow[i]).strip()
                         for rrow in rows if len(rrow) > i]
                names = [n for n in names if re.fullmatch(r"[a-z0-9_]+", n or "")]
                if len(names) >= 3:
                    return names
    names = [m.group(1) for m in
             re.finditer(r"^\s*(?:[-*+]|\d+[.)])\s+`([a-z0-9_]+)`", text, re.M)]
    return names if len(names) >= 3 else []


def rule_8_ledger_header(root: str, corpus: dict[str, str]) -> Rule:
    """The ledger's header row matches the order documented in docs/01 ADR/README.md."""
    r = Rule(8, "ledger-header",
             "the ledger's column header row matches the order docs/01 ADR/README.md documents")
    r.unit = "column"

    ledger_p = j(root, *LEDGER)
    readme_p = j(root, *ADR_README)
    missing = [name for name, path in
               (("docs/01 ADR/ADR_DECISION_RELEASE_LEDGER.tsv", ledger_p),
                ("docs/01 ADR/README.md", readme_p)) if not os.path.isfile(path)]
    if missing:
        r.skip(" and ".join(missing) + (" do not exist" if len(missing) > 1 else " does not exist"))
        return r

    documented = _documented_columns(read(readme_p))
    if not documented:
        r.checked = 1
        r.fail("docs/01 ADR/README.md documents no column order the tool can read. Use a "
               "fenced block of names, a table with a `Column` header, or a list of "
               "backticked names — the ledger's order must be documented somewhere checkable")
        return r

    first = read(ledger_p).split("\n")[0].rstrip("\r")
    actual = [c.strip() for c in first.split("\t")]
    r.checked = max(len(documented), len(actual))

    # Anchored on NAMES, never on positions: report the missing / extra / mis-ordered NAME,
    # so one inserted column does not report every column after it as wrong.
    for name in documented:
        if name not in actual:
            r.fail(f"ledger header: docs/01 ADR/README.md documents column `{name}`, "
                   f"which the header row does not carry")
    for name in actual:
        if name not in documented:
            r.fail(f"ledger header: the header row carries column `{name}`, "
                   f"which docs/01 ADR/README.md does not document")
    shared_doc = [n for n in documented if n in actual]
    shared_act = [n for n in actual if n in documented]
    if shared_doc != shared_act:
        for i, (a, b) in enumerate(zip(shared_act, shared_doc)):
            if a != b:
                r.fail(f"ledger header: column {i + 1} of the shared columns is `{a}`; "
                       f"docs/01 ADR/README.md documents `{b}` there. Order differs")
                break
    r.extra = f" ({len(actual)} in the ledger · {len(documented)} documented)"
    return r


def rule_9_readme_state(root: str, corpus: dict[str, str]) -> Rule:
    """Every `State` cell in the docs/README.md folder table agrees with the repo tree.

    This rule exists because of rule 6, not beside it. Rule 6 DEFERS the path claims in any
    row whose State cell says the folder is not written yet -- correct in intent, since a
    folder nobody has written should not fail on a path that does not exist yet. But that
    makes the document's own staleness set the check's coverage: on 2026-08-15 five written
    folders were still marked `empty`, one of them a 25,000-line document, and rule 6 passed
    green while quietly deferring six claims it should have been gating.

    The failure shape is worth naming because it is not "the check measured the wrong thing".
    It is that THE THING BEING MEASURED DECIDED HOW MUCH WOULD BE MEASURED, and it decided
    downward. A data-driven exemption is only ever as honest as the data driving it, and that
    data is usually the exact thing the check was bought to police.

    So the exemption stays -- removing it would make an honest table fail on folders genuinely
    not yet written -- and this rule guards the cell the exemption keys on. Neither rule is
    sufficient alone: rule 6 without this one can be switched off by a stale cell, and this one
    without rule 6 checks bookkeeping nobody reads.
    """
    r = Rule(9, "readme-state", "every `State` cell in the docs/README.md folder table "
                                "matches whether that folder has content")
    r.unit = "state claim"

    p = j(root, *DOCS_README)
    if not os.path.isfile(p):
        r.skip("docs/README.md does not exist")
        return r
    table = None
    for header, rows, nums in md_tables(read(p)):
        low = [h.lower().strip("* ") for h in header]
        if "folder" in low and "state" in low:
            table = (rows, nums)
            break
    if table is None:
        r.skip("docs/README.md has no folder table (a header row of `# | Folder | ... | State`)")
        return r
    rows, nums = table

    def has_content(folder: str) -> bool:
        """Content means a real file. `.gitkeep` is how an empty folder survives git."""
        d = j(root, "docs", folder)
        if not os.path.isdir(d):
            return False
        for base, dirs, files in os.walk(d):
            dirs[:] = [x for x in dirs if x not in SKIP_DIRS]
            if any(f != ".gitkeep" for f in files):
                return True
        return False

    for cells, lineno in zip(rows, nums):
        if not cells or all(not c for c in cells):
            continue
        state = cells[-1].strip().strip("*` ").lower()
        combined = " | ".join(cells[:2])
        pairs = re.findall(r"(\d{2}(?:\s+B)?)\s*\|?\s*\*\*([^*|]+?)\s*\*\*", combined)
        if not pairs:
            continue
        if "written" in state:
            expect, word = True, "written"
        elif state == "empty":
            expect, word = False, "empty"
        else:
            r.checked += 1
            r.fail(f"docs/README.md:{lineno}: State cell reads `{cells[-1].strip()}`, which is "
                   f"neither `written` nor `empty` -- rule 6 keys its deferral on this cell and "
                   f"cannot read it")
            continue

        # A row naming several folders is one claim about all of them: `part written` is the
        # honest cell when some have content, and a bare `empty`/`written` must hold for every
        # folder the row names.
        found = [(f"{num} {name}", has_content(f"{num} {name}")) for num, name in pairs]
        if "part" in state:
            r.checked += 1
            if not any(c for _, c in found):
                r.fail(f"docs/README.md:{lineno}: State says `part written`, but none of "
                       f"{', '.join(f for f, _ in found)} has any file in the tree")
            continue
        for folder, content in found:
            r.checked += 1
            if content is not expect:
                got = "has files" if content else "has no file but `.gitkeep`"
                r.fail(f"docs/README.md:{lineno}: State says `{word}` for `docs/{folder}`, "
                       f"which {got} in the repo tree"
                       + ("  <- a stale `empty` also SWITCHES OFF rule 6's path checks on "
                          "this row" if not expect else ""))
    if not r.checked:
        r.skip("the folder table names no folder the tool can resolve")
    return r


RULES = [rule_1_adr, rule_2_open, rule_3_clauses, rule_4_errata,
         rule_5_fingerprints, rule_6_readme_paths, rule_7_prep_queue,
         rule_8_ledger_header, rule_9_readme_state]


def check_all(root: str) -> list[Rule]:
    corpus = corpus_of(root)
    return [fn(root, corpus) for fn in RULES]


# ── selftest: plant a real violation of each rule, prove each rule fires ─────────
def _edit(path: str, fn) -> bool:
    old = read(path) if os.path.isfile(path) else ""
    new = fn(old)
    if new == old:
        return False
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(new)
    return True


def _plant_1(w: str) -> bool:
    return _edit(j(w, *DOCS_README),
                 lambda t: t + "\n\nPlanted: this decision is recorded under `FR-ADR-994`.\n")


def _plant_2(w: str) -> bool:
    return _edit(j(w, *DOCS_README),
                 lambda t: t + "\n\nPlanted: blocked on `OPEN-NOTAROW-01`.\n")


# The two shapes the pre-2026-08-15 pattern could not see. They are plants in their own right
# rather than variations of _plant_2, because a pattern that cannot match an id fails SILENTLY:
# it reports nothing rather than reporting a miss, so only a plant of that exact shape can tell
# a widened rule from a narrow one. Both of these pass a narrow `OPEN-[A-Z]+-\d+` untouched.
def _plant_2b(w: str) -> bool:
    """A subject with a SECOND HYPHEN -- the `OPEN-SEATMAP-DEGRADED-01` shape."""
    return _edit(j(w, *DOCS_README),
                 lambda t: t + "\n\nPlanted: blocked on `OPEN-NOT-AROW-01`.\n")


def _plant_2c(w: str) -> bool:
    """A subject containing a DIGIT -- the `OPEN-CACHE503-01` shape."""
    return _edit(j(w, *DOCS_README),
                 lambda t: t + "\n\nPlanted: blocked on `OPEN-NOTAROW404-01`.\n")


def _plant_3(w: str) -> bool:
    return _edit(j(w, *DOCS_README),
                 lambda t: t + "\n\nPlanted: per `SRC-001 §999.9`, which was never written.\n")


def _plant_4(w: str) -> bool:
    # Rename E-9 where it is FILED. SRC-003 still tables E-9 (direction A fires) and the
    # source now files an E-99 nobody tabled (direction B fires). Both directions, one plant.
    return _edit(j(w, *SRC_DIR, SRC_FILES["SRC-001"]),
                 lambda t: t.replace("**`E-9` —", "**`E-99` —", 1))


def _plant_5(w: str) -> bool:
    return _edit(j(w, *SRC_DIR, SRC_FILES["SRC-002"]),
                 lambda t: t + "\n\nPlanted: a frozen source was edited under its fingerprint.\n")


def _plant_6(w: str) -> bool:
    # Into the FIRST row the table marks `written`, so the deferral exemption cannot excuse
    # it. (Said `the ONE row` until 2026-08-15, when five more rows were corrected to
    # `written` -- the comment was true when written and silently stopped being true.)
    return _edit(j(w, *DOCS_README),
                 lambda t: t.replace("| **written** |",
                                     "and `docs/00 SourceOfTruth/NOT_A_FILE.md`. | **written** |",
                                     1))


def _plant_7(w: str) -> bool:
    return _edit(j(w, *PREP_QUEUE), lambda t: t.replace("| `REQUESTED` |", "|  |", 1))


def _plant_8(w: str) -> bool:
    """Swap two columns of the ledger header against the order the README documents.

    The rule can only be red-proofed once both halves exist, and most of docs/ is still
    empty — so where a half is missing the plant BUILDS it, then violates the real thing.
    Adaptive on purpose: as soon as the ADR README and the ledger are written for real, the
    plant swaps two of THEIR columns rather than a fixture's.
    """
    readme_p, ledger_p = j(w, *ADR_README), j(w, *LEDGER)
    documented = _documented_columns(read(readme_p)) if os.path.isfile(readme_p) else []
    if not documented:
        documented = ["ledger_id", "adr_id", "title", "decision_status",
                      "release_status", "decision_date", "notes"]
        if not _edit(readme_p, lambda t: t + (
                "\n\n## Ledger column order\n\n"
                + "\n".join(f"{i + 1}. `{c}`" for i, c in enumerate(documented)) + "\n")):
            return False
    if os.path.isfile(ledger_p):
        def swap(t: str) -> str:
            lines = t.split("\n")
            head = lines[0].rstrip("\r").split("\t")
            if len(head) < 2 or head[0] == head[1]:
                return t
            head[0], head[1] = head[1], head[0]
            return "\n".join(["\t".join(head)] + lines[1:])
        return _edit(ledger_p, swap)
    swapped = list(documented)
    swapped[0], swapped[1] = swapped[1], swapped[0]
    return _edit(ledger_p, lambda t: "\t".join(swapped) + "\n"
                 + "\t".join(["planted"] * len(swapped)) + "\n")


def _plant_9(w: str) -> bool:
    """Mark a folder that HAS content `empty` -- the stale cell, as it actually occurred.

    This is the defect that let five written folders sit behind a green rule 6 for a day, and
    it plants the cause rather than the symptom: flipping the cell is what a session does when
    it writes a folder and forgets the table.
    """
    return _edit(j(w, *DOCS_README),
                 lambda t: t.replace("| **written** |", "| empty |", 1))


PLANTS = [
    (1, "a reference to `FR-ADR-994`, which has neither a file nor a ledger row", _plant_1),
    (2, "a reference to `OPEN-NOTAROW-01`, which is in no Article X row and no SRC-003 section",
     _plant_2),
    (2, "a two-hyphen id `OPEN-NOT-AROW-01` \u2014 the shape the pre-widening pattern could not see",
     _plant_2b),
    (2, "a digit-bearing id `OPEN-NOTAROW404-01` \u2014 the other shape it could not see",
     _plant_2c),
    (3, "a citation of `SRC-001 §999.9`, a clause anchor that does not exist", _plant_3),
    (4, "`E-9` renamed where it is filed — SRC-003 still tables E-9, the source now files E-99",
     _plant_4),
    (5, "a line appended to a FROZEN source, moving it off its recorded sha256", _plant_5),
    (6, "a path quoted in the FIRST table row marked `written` that is not in the tree", _plant_6),
    (7, "a prep-queue row whose Status cell is blanked", _plant_7),
    (8, "a ledger header that swaps two of the columns docs/01 ADR/README.md documents",
     _plant_8),
    (9, "a folder that has content, still marked `empty` \u2014 the stale cell that also "
        "switches off rule 6's path checks", _plant_9),
]


def selftest(root: str) -> int:
    """Red-proof every rule by DELTA.

    Requiring a clean baseline would mean the tool can only be trusted on a green
    repository — which is never the day you need it. So the baseline is measured, not
    demanded, and each plant must make ITS OWN rule's failure count RISE.
    """
    base = {r.num: r for r in check_all(root)}
    reds = sum(1 for r in base.values() if r.failures)
    print(f"baseline: {reds} rule(s) already failing, "
          f"{sum(1 for r in base.values() if r.skip_reason)} skipped — red-proofing by delta")
    print()

    passed = 0
    for num, what, plant in PLANTS:
        with tempfile.TemporaryDirectory() as tmp:
            work = os.path.join(tmp, "repo")
            shutil.copytree(root, work, ignore=shutil.ignore_patterns(*SKIP_DIRS))
            if not plant(work):
                print(f"  FAIL  rule {num}  the plant was a no-op — it proved nothing")
                continue
            after = {r.num: r for r in check_all(work)}
            b, a = len(base[num].failures), len(after[num].failures)
            key = base[num].key
            if a > b:
                passed += 1
                print(f"  ok    rule {num}  {key:<18} {b} -> {a} failure(s)   planted: {what}")
            else:
                print(f"  FAIL  rule {num}  {key:<18} {b} -> {a} failure(s)   DID NOT FIRE. "
                      f"A check that cannot fail is decoration. Planted: {what}")
    print()
    print(f"{passed}/{len(PLANTS)} checks red-proofed")
    return 0 if passed == len(PLANTS) else 1


# ── report ──────────────────────────────────────────────────────────────────────
ORDER = {"FAIL": 0, "SKIP": 1, "PASS": 2}


def report(rules: list[Rule]) -> int:
    width = max(len(r.key) for r in rules)
    for r in sorted(rules, key=lambda x: (ORDER[x.status], x.num)):
        print(f"{r.status}  rule {r.num}  {r.key:<{width}}  {r.rate}")
    print()
    for r in sorted(rules, key=lambda x: x.num):
        if not r.failures:
            continue
        print(f"[{r.key}] {len(r.failures)} failure(s) — {r.what}")
        for d in r.failures:
            print(f"   {d}")
        print()

    n_fail = sum(1 for r in rules if r.status == "FAIL")
    n_skip = sum(1 for r in rules if r.status == "SKIP")
    n_pass = sum(1 for r in rules if r.status == "PASS")
    total = sum(len(r.failures) for r in rules)
    print(f"rules: {len(rules)}  ·  {n_pass} pass  ·  {n_fail} fail  ·  {n_skip} skip")
    if n_fail:
        print(f"VERDICT: FAIL — {total} unresolved cross-reference(s) across {n_fail} rule(s).")
        return 1
    print("VERDICT: PASS — every cross-reference that can be checked today resolves.")
    print("         This is the cheap layer only (Art IX.6). It cannot see two documents")
    print("         that each resolve fine and contradict each other — that is GOAL_13.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    help="repository root (defaults to the parent of tools/)")
    ap.add_argument("--selftest", action="store_true",
                    help="plant a real violation of every rule and require each one to fire")
    args = ap.parse_args()
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:                                             # noqa: BLE001
        pass
    if args.selftest:
        return selftest(args.root)
    return report(check_all(args.root))


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception:                                             # noqa: BLE001
        traceback.print_exc()
        print("\nVERDICT: ERROR — the tool itself failed. This is exit 2, not a finding "
              "about the repository.", file=sys.stderr)
        sys.exit(2)

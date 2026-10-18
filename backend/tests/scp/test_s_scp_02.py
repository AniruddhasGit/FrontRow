"""S-SCP-02 (PRD P-SCP-06/07/09/14/17): no excluded machinery. The self-standing clauses only.

Not here: the compose clause (it reads "exactly three services" while S-XCT-35 and S-XCT-36 read
six - reported as a document defect) and the outbound-request sublist for one end-to-end checkout
(no checkout exists until Phase 4).
"""

from __future__ import annotations

import json
import re

from ..xct._support import REPO, rg

TREES = ("backend/app", "backend/migrations", "frontend/src", "scripts")


def _not_comment(hit) -> bool:
    return not hit[2].lstrip().startswith(("#", "//"))


def test_no_scheduler_library_or_call_outside_comments():
    hits = rg(r"apscheduler|celery|dramatiq|BackgroundScheduler|schedule\.every|crontab", *TREES, ignore_case=True)
    assert [h for h in hits if _not_comment(h)] == []


def test_no_manifest_dependency_on_excluded_machinery():
    excluded = re.compile(r"qrcode|segno|barcode|zxing|reportlab|openpyxl|xlsxwriter|weasyprint|openai|anthropic|langchain|tmdb", re.IGNORECASE)
    names = []
    for line in (REPO / "backend" / "requirements.txt").read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            names.append(re.split(r"[\[=<>~! ]", line, 1)[0])
    pkg = json.loads((REPO / "frontend" / "package.json").read_text(encoding="utf-8"))
    names += list(pkg.get("dependencies", {})) + list(pkg.get("devDependencies", {}))
    assert names, "no dependency parsed - a vacuous pass is not a pass"
    assert [n for n in names if excluded.search(n)] == []


def test_no_model_or_movie_api_host_is_named():
    pattern = r"api\.openai\.com|api\.anthropic\.com|generativelanguage\.googleapis|bedrock-runtime|api\.themoviedb\.org"
    assert rg(pattern, *TREES, ignore_case=True) == []

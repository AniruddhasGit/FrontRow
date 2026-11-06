"""S-TKT-14 (P-TKT-11): the runbook says that sent means SES accepted, never that the customer received."""

from __future__ import annotations

import re

from tests.xct._support import REPO, rg

RUNBOOK = "docs/35 Hypercare/runbook.md"
REQUIRED = ("evidence of dispatch, never of receipt", "depth is not alarmed", "nothing scrapes it",
            "indistinguishable from one that reached the inbox", "running task count below 1", "dead letter queue depth",
            "outbox_message pending count", "SES bounce and complaint rate",
            "no endpoint, screen or job in v1 re-sends a receipt on an operator's behalf",
            "a dead letter redrive is a Zone C console action")
FORBIDDEN = ("means the customer received", "confirms delivery", "proves delivery", "the receipt was delivered",
             "the customer has received", "confirms the customer got", "the receipt reached")


def test_the_runbook_has_a_receipt_heading_and_every_required_sentence():
    text = (REPO / RUNBOOK).read_text(encoding="utf-8")
    assert any(line.startswith("#") and "Receipt" in line for line in text.splitlines())
    for phrase in REQUIRED:
        assert len(rg(phrase, RUNBOOK, fixed=True)) >= 1, phrase


def test_the_two_sql_blocks_and_no_delivery_claim():
    text = (REPO / RUNBOOK).read_text(encoding="utf-8")
    blocks = re.findall(r"```sql\n(.*?)```", text, re.S)
    assert any("FROM receipt_dispatch" in b and "GROUP BY status" in b for b in blocks)
    assert any("FROM outbox_message" in b and "status = 'pending'" in b for b in blocks)
    for phrase in FORBIDDEN:
        assert rg(phrase, RUNBOOK, fixed=True, ignore_case=True) == [], phrase

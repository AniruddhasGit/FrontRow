"""S-XCT-42 (PRD P-XCT-28): the four open rows stay open, asserted as absences. Phase 1's share.

Not here (the row stays Blocked on them): the OPEN-ATTRIB-01 seed/movie-table clauses, the booking.cancelled_at
information_schema read, the SCR-XCT-01 copy-table parse, the booking screen rendering FR-K7M2-QX9C after a confirm,
and the withdraw-beside-showtime clause (see below).
"""

from __future__ import annotations

import re

from app.core.config import Settings
from app.main import create_app

from ..conftest import VALID_ENV
from ..test_health import ok_probe
from ._support import mounted_routes, rg


def test_open_tls_01_cookie_secure_has_no_default_and_nothing_claims_tls():
    assert Settings.model_fields["COOKIE_SECURE"].is_required()
    decl = [h for h in rg(r"COOKIE_SECURE", "backend/app/core/config.py") if h[2].lstrip().startswith("COOKIE_SECURE")]
    assert decl and all("=" not in h[2] for h in decl)
    phrases = r"tls is terminated|tls will be terminated|https listener exists|behind https"
    assert rg(phrases, "docs/03 PRD", "docs/30 Deployment", "backend/app", "backend/migrations", "frontend/src", ignore_case=True) == []


def test_open_showcancel_01_no_route_and_no_code_for_cancelling_or_refunding(valid_env, clock):
    app = create_app(Settings(**VALID_ENV), clock=clock, probes=[ok_probe("postgres"), ok_probe("redis")])
    paths = [p for _, p in mounted_routes(app)]
    assert paths
    assert [p for p in paths if re.search(r"cancel|withdraw|refund", p)] == []
    assert rg(r"cancel_showtime", "backend/app", "frontend/src", ignore_case=True) == []
    # The amended criterion: 'refund' only on a line carrying a PRD-published copy string that states the absence -
    # SCR-TKT-01's policy line (P-PAY-12), the receipt's final line (E4), and the hall and film withdrawal
    # confirmations' "nothing is refunded" (SCR-ADM-05 / P-ADM-16, E6) - and on no identifier, route or function.
    published = ("This booking cannot be changed, cancelled or refunded.",
                 "This booking is final. There is no cancellation and no refund.", "nothing is refunded")
    hits = rg(r"refund", "backend/app", "frontend/src", ignore_case=True)
    assert hits and [h for h in hits if not any(p in h[2] for p in published)] == []
    # NOT asserted (the row stays Blocked on it): 'withdraw' on no line that also matches showtime. Published E6 copy
    # (the film publish confirmation, the lookup withdraw confirmation) and the showtimes router's own "there is no
    # withdraw or cancel route" docstring all name both words; filed as an AC over-reach.
    assert rg(r"cancelled_at", "backend/app/api") == []


def test_open_emailfail_01_no_copy_for_a_definitively_failed_receipt():
    assert rg(r"receipt (could not|failed|was not sent)", "frontend/src", ignore_case=True) == []
    assert rg("OPEN-EMAILFAIL-01", "docs/03 PRD/FrontRow_PRD.md", fixed=True)

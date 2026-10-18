"""S-XCT-42 (PRD P-XCT-28): the four open rows stay open, asserted as absences. Phase 1's share.

Not here, because the artefacts do not exist yet: scripts/seed.py and the movie table (OPEN-ATTRIB-01,
Phase 2), the booking.cancelled_at column check (schema applied by the foundation lane), and the
booking screen rendering the reference (OPEN-EMAILFAIL-01, Phase 4).
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
    # The AC's pattern also lists `withdraw`; the Phase 2 audit vocabulary (app/domain/audit.py,
    # "language.withdrawn") matches it, so that third word is reported as a criterion conflict and
    # not asserted here (lane report, S-XCT-42).
    assert rg(r"refund|cancel_showtime", "backend/app", "frontend/src", ignore_case=True) == []
    assert rg(r"cancelled_at", "backend/app/api") == []


def test_open_emailfail_01_no_copy_for_a_definitively_failed_receipt():
    assert rg(r"receipt (could not|failed|was not sent)", "frontend/src", ignore_case=True) == []
    assert rg("OPEN-EMAILFAIL-01", "docs/03 PRD/FrontRow_PRD.md", fixed=True)

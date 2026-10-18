"""S-SCP-10 (P-SCP-04/08/17): no upcoming section, no language switch, no recommendation; one order for everyone.

Not here (browser harness): /upcoming and /coming-soon RENDERING the 404 view, the rendered accessibility tree
of the shell, and the html lang / navigation names before and after a Language change. The route table is
checked at source level below, which is weaker than a render.
"""

from __future__ import annotations

import re

import pytest

from app.core.security import SESSION_COOKIE, issue_session_token
from tests.brw.kit import SetClock, api, flush_redis, make_movie, one, owner_sql, reset_catalogue, settings_for
from tests.dbkit import FAKE_HASH
from tests.xct._support import REPO, rg

pytestmark = pytest.mark.anyio


def test_no_route_path_names_an_upcoming_section():
    paths = [m.group(1) for f in (REPO / "frontend" / "src").rglob("*.tsx")
             for m in re.finditer(r'path:\s*"([^"]+)"', f.read_text(encoding="utf-8"))]
    assert "/" in paths  # the walk found the route tables
    assert [p for p in paths if re.match(r"^/(upcoming|coming-soon)$", p)] == []


def test_no_translation_or_recommendation_machinery():
    assert rg(r"i18n|react-intl|formatjs|gettext|recommend", "frontend/package.json", "frontend/src", ignore_case=True) == []


async def test_anonymous_and_signed_in_listings_share_one_order(migrated_db):
    reset_catalogue(migrated_db)
    flush_redis()
    db = migrated_db
    for at in ("2026-08-12T10:00:00+05:30", "2026-08-14T09:00:00+05:30", "2026-08-14T09:00:00+05:30", "2026-08-11T09:00:00+05:30"):
        make_movie(db, published_at=at)
    expected = [r[0] for r in owner_sql(db, "SELECT id FROM movie ORDER BY published_at DESC, id DESC")]
    clock = SetClock()
    clock.set("2026-08-15T12:00:00+05:30")
    user = one(db, "INSERT INTO users (email, password_hash, role, password_version) VALUES ('o@example.invalid', %s, "
                   "'customer', 1) RETURNING id", (FAKE_HASH,))
    token = issue_session_token(user_id=user, role="customer", password_version=1, now=clock.now(), settings=settings_for(db))
    async with api(db, clock) as c:
        anonymous = [m["id"] for m in (await c.get("/api/movies")).json()["movies"]]
        signed_in = [m["id"] for m in (await c.get("/api/movies", cookies={SESSION_COOKIE: token})).json()["movies"]]
    assert anonymous == signed_in == expected

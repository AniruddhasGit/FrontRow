"""S-ACC-13 (P-ACC-12, P-ACC-14, EP-ACC-07/08): every /api/me/ route is scoped to the caller on the router, and the
reference lookup is limited."""

from __future__ import annotations

import inspect
import re

import pytest
from sqlalchemy import event

from app.api import me
from app.api.deps import CurrentUser
from app.core.config import Settings
from app.main import create_app
from tests.conftest import VALID_ENV
from tests.pay.kit import add_seats, api, book, clock_at, cookies, user, world7

pytestmark = pytest.mark.anyio
NOW = "2026-08-14T14:00:00+00:00"
NOT_YOURS = "No booking with that reference is on your account."


@pytest.fixture
def world(migrated_db):
    w = world7(migrated_db)
    add_seats(migrated_db, w["screen"], w["standard"], [(4000 + n, "K", n) for n in range(1, 9)], [7])
    return w


def _no_rid(r) -> dict:
    body = r.json()
    body["error"].pop("request_id")
    return body


async def test_the_three_assertions_own_denied_and_the_other_direction(world):
    db = world["db"]
    a, b = user(db), user(db)
    _, ref_a = book(db, a, 7, [4001])
    _, ref_b = book(db, b, 7, [4002])
    async with api(db, clock_at(NOW)) as c:
        mine = (await c.get("/api/me/bookings", cookies=cookies(c, a))).json()["upcoming"]
        assert mine and ref_a in [r["reference"] for r in mine]  # 1: the query works
        denied = await c.get(f"/api/me/bookings/{ref_b}", cookies=cookies(c, a))
        assert denied.status_code == 404 and denied.json()["error"] == {**denied.json()["error"], "code": "NOT_FOUND",
                                                                         "message": NOT_YOURS}  # 2: it is scoped
        theirs = await c.get(f"/api/me/bookings/{ref_b}", cookies=cookies(c, b))
        assert theirs.status_code == 200 and theirs.json()["reference"] == ref_b  # 3: by identity, not by absence
        never = await c.get("/api/me/bookings/FR-2345-6789", cookies=cookies(c, a))
        assert never.status_code == 404 and _no_rid(never) == _no_rid(denied)


async def test_a_manager_and_an_admin_see_only_their_own(world):
    db = world["db"]
    customer, manager, admin = user(db), user(db, "manager"), user(db, "admin")
    book(db, customer, 7, [4001])
    _, ref_m = book(db, manager, 7, [4002])
    _, ref_x = book(db, admin, 7, [4003])
    async with api(db, clock_at(NOW)) as c:
        for who, role, ref in ((manager, "manager", ref_m), (admin, "admin", ref_x)):
            rows = (await c.get("/api/me/bookings", cookies=cookies(c, who, role))).json()["upcoming"]
            assert [r["reference"] for r in rows] == [ref]


def test_the_two_operations_take_exactly_their_published_parameters_and_no_body():
    schema = create_app(Settings(**VALID_ENV)).openapi()["paths"]
    listing, lookup = schema["/api/me/bookings"]["get"], schema["/api/me/bookings/{reference}"]["get"]
    assert sorted(p["name"] for p in listing["parameters"]) == ["group", "page", "page_size"]
    assert [p["name"] for p in lookup["parameters"]] == ["reference"]
    assert "requestBody" not in listing and "requestBody" not in lookup


def test_the_dependency_is_on_the_router_and_no_handler_takes_the_caller():
    assert [d.dependency for d in me.router.dependencies] == [me.caller]
    for route in me.router.routes:
        assert me.caller in [d.call for d in route.dependant.dependencies], route.path
        params = inspect.signature(route.endpoint).parameters.values()
        assert not [p for p in params if p.annotation in (CurrentUser, "CurrentUser")], route.path


async def test_the_ownership_predicate_is_in_the_lookups_one_statement(world):
    db = world["db"]
    a, b = user(db), user(db)
    _, ref_b = book(db, b, 7, [4002])
    async with api(db, clock_at(NOW)) as c:
        recorded: list[str] = []
        engine = c.application.state.db_engine

        def listener(conn, cursor, statement, parameters, context, executemany):
            recorded.append(statement)

        event.listen(engine.sync_engine, "before_cursor_execute", listener)
        try:
            r = await c.get(f"/api/me/bookings/{ref_b}", cookies=cookies(c, a))
        finally:
            event.remove(engine.sync_engine, "before_cursor_execute", listener)
    assert r.status_code == 404
    from_booking = [s for s in recorded if re.search(r"FROM booking\b(?!_)", s)]
    assert len(from_booking) == 1
    where = from_booking[0].split("WHERE", 1)[1].split("ORDER BY")[0]
    assert "booking.reference" in where and "booking.user_id" in where and where.count("WHERE") == 0


async def test_the_reference_is_normalised_and_nothing_is_corrected(world):
    db = world["db"]
    u = user(db)
    _, ref = book(db, u, 7, [4001])
    bare = ref.replace("FR-", "").replace("-", "")
    async with api(db, clock_at(NOW)) as c:
        for typed in (ref, ref.lower(), bare, f" {bare[:4]} {bare[4:]} ", f"fr{bare.lower()}"):
            r = await c.get(f"/api/me/bookings/{typed}", cookies=cookies(c, u))
            assert r.status_code == 200 and r.json()["reference"] == ref, typed
        unknown = await c.get("/api/me/bookings/FR-2345-6789", cookies=cookies(c, u))
        zero = await c.get("/api/me/bookings/FR-0BCD-EFGH", cookies=cookies(c, u))
    assert zero.status_code == 404 and _no_rid(zero) == _no_rid(unknown)
    from app.domain.booking import normalise_reference

    assert "".join(ch for ch in "FR-0BCD-EFGH" if ch != "-")[2:] == "0BCDEFGH" and normalise_reference("FR-0BCD-EFGH") is None


async def test_the_21st_lookup_for_one_user_is_429_after_3(world):
    db = world["db"]
    u = user(db)
    _, ref = book(db, u, 7, [4001])
    async with api(db, clock_at(NOW)) as c:
        for _ in range(20):
            assert (await c.get(f"/api/me/bookings/{ref}", cookies=cookies(c, u))).status_code == 200
        r = await c.get(f"/api/me/bookings/{ref}", cookies=cookies(c, u))
    assert r.status_code == 429 and r.headers["Retry-After"] == "3"
    assert r.json()["error"]["message"] == "Too many lookups. Try again in 3 seconds."


async def test_the_61st_lookup_from_one_ip_is_429_after_1_second(world):
    db = world["db"]
    customers = [user(db) for _ in range(5)]
    async with api(db, clock_at(NOW)) as c:
        for n in range(60):
            r = await c.get("/api/me/bookings/FR-2345-6789", cookies=cookies(c, customers[n // 15]))
            assert r.status_code == 404, (n, r.text)
        r = await c.get("/api/me/bookings/FR-2345-6789", cookies=cookies(c, customers[4]))
    assert r.status_code == 429 and r.headers["Retry-After"] == "1"
    assert r.json()["error"]["message"] == "Too many lookups. Try again in 1 second."


async def test_the_list_itself_is_unlimited(world):
    db = world["db"]
    u = user(db)
    async with api(db, clock_at(NOW)) as c:
        for _ in range(100):
            r = await c.get("/api/me/bookings", cookies=cookies(c, u))
            assert r.status_code == 200 and "retry-after" not in r.headers

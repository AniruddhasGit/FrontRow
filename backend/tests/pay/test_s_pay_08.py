"""S-PAY-08 (EP-PAY-01, P-PAY-01, P-PAY-06): POST /api/bookings serves its published contract, auth and error set."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from app.api import bookings
from tests.pay.kit import C1, F7, FIVE, api, clock_at, confirm, cookies, count, hold, owner_sql, user, world7

pytestmark = pytest.mark.anyio
APP = Path(__file__).resolve().parents[2] / "app"
SOURCE = (APP / "api" / "bookings.py").read_text(encoding="utf-8")
REF = r"^FR-[23456789ACDEFHJKMNPQRTVWXY]{4}-[23456789ACDEFHJKMNPQRTVWXY]{4}$"
ELEVEN = sorted(["REQUEST_INVALID", "AUTH_REQUIRED", "HOLD_EXPIRED", "HOLD_NOT_OWNED", "SEAT_UNAVAILABLE", "IDEMPOTENCY_IN_FLIGHT",
                 "IDEMPOTENCY_KEY_REUSED", "PAYMENT_FAILED", "RATE_LIMITED", "DEPENDENCY_UNAVAILABLE", "INTERNAL_ERROR"])


@pytest.fixture
def world(migrated_db):
    return world7(migrated_db)


async def test_no_session_or_an_expired_one_is_401_with_this_endpoints_sentence(world):
    db = world["db"]
    u = user(db)
    async with api(db, clock_at()) as c:
        r = await c.post("/api/bookings", json={"hold_token": "x" * 43, "showtime_id": 7}, headers={"Idempotency-Key": "k"})
        assert r.status_code == 401 and r.json()["error"] == {**r.json()["error"], "code": "AUTH_REQUIRED",
                                                              "message": "Sign in to complete this booking."}
        stale = cookies(c, u)
        c.clock.advance(c.settings.SESSION_TTL_SECONDS + 1)
        r = await c.post("/api/bookings", json={"hold_token": "x" * 43, "showtime_id": 7}, headers={"Idempotency-Key": "k"},
                         cookies=stale)
        assert r.status_code == 401 and r.json()["error"]["message"] == "Sign in to complete this booking."


def test_authorisation_is_the_routers_dependency_and_no_handler_checks_a_role():
    hits = re.findall(r"APIRouter\(dependencies=.*", SOURCE)
    assert len(hits) == 1 and "confirm_session" in hits[0]
    assert not re.search(r"require_role|current_user\.role|has_role|is_admin", SOURCE)


async def test_a_malformed_token_is_400_with_redis_stopped(world):
    db = world["db"]
    u = user(db)
    async with api(db, clock_at(), REDIS_URL="redis://127.0.0.1:1/0") as c:
        for token in ("a" * 42, "a" * 44, "a" * 42 + "+", "a" * 42 + "="):
            r = await confirm(c, u, token)
            assert r.status_code == 400 and r.json()["error"]["code"] == "REQUEST_INVALID", (token, r.text)
        # A well-formed one reaches Redis, which is down: 503, and the confirm never looks for a hold anywhere else.
        r = await confirm(c, u, "a" * 43)
        assert r.status_code == 503 and r.json()["error"]["code"] == "DEPENDENCY_UNAVAILABLE"
        assert r.json()["error"]["message"].startswith("We cannot complete your booking right now. You have not been charged.")
    assert count(db, "SELECT count(*) FROM booking") == 0
    assert count(db, "SELECT count(*) FROM payment") == count(db, "SELECT count(*) FROM idempotency_record") == 0
    assert count(db, "SELECT count(*) FROM information_schema.tables WHERE table_name IN ('seat_hold','hold','seat_lock','lock')") == 0


async def test_redis_failing_after_the_bucket_is_503_and_writes_nothing(world):
    db = world["db"]
    u = user(db)
    async with api(db, clock_at()) as c:
        h = await hold(c, u, [F7])
        real = c.application.state.redis

        class HalfDown:
            """The bucket's EVAL succeeds; the hold read fails as an unreachable node would."""

            def __getattr__(self, name):
                return getattr(real, name)

            async def hgetall(self, *a, **k):
                from redis.exceptions import ConnectionError

                raise ConnectionError("down")

        c.application.state.redis = HalfDown()
        r = await confirm(c, u, h["hold_token"])
        c.application.state.redis = real
    assert r.status_code == 503 and r.json()["error"]["code"] == "DEPENDENCY_UNAVAILABLE"
    assert count(db, "SELECT count(*) FROM booking") == count(db, "SELECT count(*) FROM payment") == 0
    assert count(db, "SELECT count(*) FROM idempotency_record") == 0


async def test_the_body_is_exactly_hold_token_and_showtime_id(world):
    db = world["db"]
    u = user(db)
    owner_sql(db, "INSERT INTO showtime (id, movie_id, screen_id, starts_at, ends_at, base_price_paise, seat_count_at_creation, version) "
                  "OVERRIDING SYSTEM VALUE SELECT 8, movie_id, screen_id, starts_at, ends_at, base_price_paise, 0, 1 FROM showtime WHERE id = 7")
    async with api(db, clock_at()) as c:
        h = await hold(c, u, [F7])
        wrong = await confirm(c, u, h["hold_token"], showtime_id=8)
        assert wrong.status_code == 400 and wrong.json()["error"]["code"] == "REQUEST_INVALID"
        seats = await confirm(c, u, h["hold_token"], body={"hold_token": h["hold_token"], "showtime_id": 7, "seats": [F7]})
        assert seats.status_code == 400 and seats.json()["error"]["code"] == "REQUEST_INVALID"
    assert count(db, "SELECT count(*) FROM booking") == 0


async def test_the_201_body_has_exactly_the_published_keys_and_the_cinemas_offset(world):
    db = world["db"]
    u = user(db)
    async with api(db, clock_at()) as c:
        h = await hold(c, u, FIVE)
        r = await confirm(c, u, h["hold_token"])
        assert r.status_code == 201, r.text
        body = r.json()
        assert set(body) == {"booking_id", "booking_reference", "showtime_id", "movie_title", "screen_name", "starts_at", "seats",
                             "total_paise", "currency_code", "payment_status", "created_at"}
        assert re.match(REF, body["booking_reference"])
        assert (body["currency_code"], body["payment_status"], body["showtime_id"]) == ("USD", "captured", 7)
        assert (body["movie_title"], body["screen_name"]) == ("The Long Night", "Hall 2")
        for field in ("starts_at", "created_at"):
            assert body[field].endswith("+05:30") and not body[field].endswith("Z"), body[field]
        assert body["starts_at"] == "2026-08-14T20:00:00+05:30"
        assert [s["seat_label"] for s in body["seats"]] == ["F7", "F8", "F9", "J3", "J4"]
        assert set(body["seats"][0]) == {"seat_id", "seat_label", "seat_category_name", "price_paise", "base_price_paise_applied",
                                         "uplift_basis_points_applied"}
        owner_sql(db, "UPDATE cinema SET timezone = 'Asia/Dubai'")
        h2 = await hold(c, u, [C1])
        r2 = await confirm(c, u, h2["hold_token"], key="second-attempt")
        assert r2.status_code == 201, r2.text
        assert r2.json()["starts_at"].endswith("+04:00") and r2.json()["created_at"].endswith("+04:00")


def test_the_emitted_error_set_is_exactly_the_contracts_eleven():
    found = sorted(set(re.findall(r"ErrorCode\.([A-Z_]+)", SOURCE)))
    assert found == ELEVEN and "SALES_CLOSED" not in found
    assert sorted(code.value for code in bookings.EMITS) == ELEVEN
    contract = json.loads((Path("/docs") / "03 PRD" / "api" / "contract.json").read_text(encoding="utf-8"))
    ep = next(e for e in contract["endpoints"] if e["id"] == "EP-PAY-01")
    assert sorted(ep["errors"]) == ELEVEN


async def test_the_eleventh_confirm_in_a_minute_from_one_user_is_429_after_6_and_replays_spend_tokens(world):
    db = world["db"]
    u = user(db)
    async with api(db, clock_at()) as c:
        h = await hold(c, u, [F7])
        first = await confirm(c, u, h["hold_token"])
        assert first.status_code == 201
        for _ in range(9):  # nine replays of an already-seen key: each still spends a token
            assert (await confirm(c, u, h["hold_token"])).status_code == 201
        r = await confirm(c, u, h["hold_token"])
        assert r.status_code == 429 and r.headers["Retry-After"] == "6"
        assert r.json()["error"] == {**r.json()["error"], "code": "RATE_LIMITED", "message": "Too many attempts. Try again in 6 seconds."}


async def test_the_thirty_first_from_one_ip_is_429_after_2(world):
    db = world["db"]
    customers = [user(db) for _ in range(4)]
    async with api(db, clock_at()) as c:
        statuses = []
        for n in range(30):
            statuses.append((await confirm(c, customers[n % 4], "a" * 43, key=f"k{n}")).status_code)
        assert statuses == [409] * 30  # no such hold - but every one was counted
        last = await confirm(c, customers[0], "a" * 43, key="k-last")  # the 31st from this IP; no user is near 10
        assert last.status_code == 429 and last.headers["Retry-After"] == "2"
        assert last.json()["error"]["message"] == "Too many attempts. Try again in 2 seconds."


def test_the_openapi_body_is_closed_with_exactly_two_properties():
    from app.main import create_app
    from tests.conftest import VALID_ENV
    from app.core.config import Settings

    schema = create_app(Settings(**VALID_ENV)).openapi()
    body = schema["paths"]["/api/bookings"]["post"]["requestBody"]["content"]["application/json"]["schema"]
    assert body["additionalProperties"] is False and sorted(body["properties"]) == ["hold_token", "showtime_id"]


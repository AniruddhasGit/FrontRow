"""S-SEA-19 (P-HLD-14): the lane's message set - one envelope, a stable code, one substitution rule.

Every row the four HOLD endpoints can produce is driven end to end, once as a first hold and once as an extend.
Rows 4, 4b and 18 are the CONFIRM's (EP-PAY-01, lane PAY, not mounted) and row 10 is a client banner; those four
are swept for wording below but no request produces them here.
"""

from __future__ import annotations

import re

import pytest

from app.domain import holds
from tests.sea.kit import SHOWTIME, T0, SetClock, api, flush, owner_sql, r_call, session, user, world77
from tests.xct._support import REPO

pytestmark = pytest.mark.anyio
URL = f"/api/showtimes/{SHOWTIME}/holds"
ENDED = ("The hold on your seats has ended and they have been released. You have not been charged. "
         "Choose them again if they are still free.")
# The 24 published rows, verbatim from P-HLD-14 (at MAX_SEATS_PER_BOOKING 10, the PRD's labels and counts).
PUBLISHED = {
    "1": "Sign in to hold seats. Your selection has been kept.",
    "2": "C12 was taken by another customer. No seats were held. Choose a different seat and press Hold these seats again.",
    "2b": "C12 was taken by another customer. Your hold is unchanged. Choose a different seat and try again.",
    "3": "C12 and C13 were taken by another customer. No seats were held. Your other choices are still selected — change these two and press Hold these seats again.",
    "3b": "C12 and C13 were taken by another customer. Your hold is unchanged. Your other choices are still selected — change these two and try again.",
    "4": "C12 was taken by another customer before your payment finished. Your booking was not made and you have not been charged.",
    "4b": "C12 and C13 were taken by another customer before your payment finished. Your booking was not made and you have not been charged.",
    "5": ENDED, "6": ENDED,
    "7": "You can hold up to 10 seats for one showtime. You chose 11.",
    "8": "You can hold up to 10 seats for one showtime. You are holding 6 and chose 5 more.",
    "9": "Sales for this showtime closed at 7:45 pm. Choose another showtime.",
    "10": "Sales for this showtime have closed. You can still pay for the seats you are holding.",
    "11": "Seat C12 was listed twice. Each seat can only be chosen once. No seats were held.",
    "12": "Seat C12 is not part of this hall. No seats were held.",
    "13": "Choose at least one seat.",
    "14": "That seat is not part of your hold.",
    "15": "That showtime could not be found.",
    "16": "Too many attempts. Try again in 3 seconds.",
    "17": "Seat holds are unavailable right now. You can still browse showtimes. Try again in a few minutes.",
    "18": "We cannot complete your booking right now. You have not been charged. Try again in a few minutes. If you need help, quote a1b2c3d4.",
    "19": "Something went wrong and your seats were not held. You have not been charged. If you need help, quote a1b2c3d4.",
    "20": "Seat C12 is out of service. No seats were held.",
    "21": "Seats C12 and C13 were listed more than once. Each seat can only be chosen once. No seats were held.",
    "22": "Seats C12 and C13 are not part of this hall. No seats were held.",
    "23": "Seats C12 and C13 are out of service. No seats were held.",
    "24": "This request could not be processed. Return to the seat map and choose your seats again.",
}


@pytest.fixture
def world(migrated_db):
    """C12 (412) and C13 (413) are the protagonists. Seats 430/431 (C30, C31) are retired after showtime 77; seats
    432/433 are added to the hall after it - so the 'out of service' and 'not part of this hall' rows can name two."""
    from tests.sea.kit import seat

    w = world77(migrated_db, retire_412=False)
    db = w["db"]
    for n in (30, 31):
        seat(db, w["screen"], 400 + n, "C", n, 3, n, w["standard"])
        owner_sql(db, "INSERT INTO showtime_seat (showtime_id, seat_id) VALUES (77, %s)", (400 + n,))
        owner_sql(db, "UPDATE seat SET is_active = false WHERE id = %s", (400 + n,))
    for n in (32, 33):
        seat(db, w["screen"], 400 + n, "C", n, 3, n, w["standard"])
    return w


def _clock() -> SetClock:
    c = SetClock()
    c.set(T0)
    return c


async def _row(c, cookies, extend: bool, seat_ids, taken=()):
    for s in taken:
        r_call("SET", f"lock:seat:77:{s}", "another-customers-hold-token", "PX", "300000")
    r = await c.post(URL, json={"seat_ids": seat_ids}, cookies=cookies)
    for s in taken:
        r_call("DEL", f"lock:seat:77:{s}")
    return r


HOLD_ROWS = {  # row -> (seat_ids, seats taken by someone else, status, code)
    "2": ([412], [412], 409, "SEAT_UNAVAILABLE"),
    "3": ([412, 413], [412, 413], 409, "SEAT_UNAVAILABLE"),
    "11": ([412, 413, 414, 415, 412], [], 422, "VALIDATION_FAILED"),  # five seats, ONE duplicate: the singular
    "12": ([432], [], 422, "VALIDATION_FAILED"),
    "13": ([], [], 422, "VALIDATION_FAILED"),
    "20": ([430], [], 422, "VALIDATION_FAILED"),
    "21": ([412, 413, 414, 412, 413], [], 422, "VALIDATION_FAILED"),
    "22": ([432, 433], [], 422, "VALIDATION_FAILED"),
    "23": ([430, 431], [], 422, "VALIDATION_FAILED"),
}
LABELS = {"11": "C12", "12": "C32", "20": "C30", "21": "C12 and C13", "22": "C32 and C33", "23": "C30 and C31"}


def _expected(row: str, extend: bool) -> str:
    text = PUBLISHED[row + "b"] if extend and row in ("2", "3") else PUBLISHED[row]
    if row in LABELS:
        text = text.replace("C12 and C13" if "C12 and C13" in text else "C12", LABELS[row])
    if extend:
        text = text.replace("No seats were held.", "Your hold is unchanged.")
    return text


async def test_every_seat_level_row_as_a_first_hold_and_as_an_extend(world):
    first_user, extend_user = user(world["db"]), user(world["db"])
    differing = 0
    async with api(world["db"], _clock()) as c:
        first_cookies, extend_cookies = session(c, first_user), session(c, extend_user)
        assert (await c.post(URL, json={"seat_ids": [401]}, cookies=extend_cookies)).status_code == 201
        for row, (seat_ids, taken, status, code) in HOLD_ROWS.items():
            first = await _row(c, first_cookies, False, seat_ids, taken)
            extend = await _row(c, extend_cookies, True, seat_ids, taken)
            for r, is_extend in ((first, False), (extend, True)):
                err = r.json()["error"]
                assert (r.status_code, err["code"], err["message"]) == (status, code, _expected(row, is_extend)), row
                assert re.fullmatch(r"[0-9a-f]{8}", err["request_id"]) and set(r.json()) == {"error"}
                assert set(err) == {"code", "message", "details", "request_id"}
                if code == "SEAT_UNAVAILABLE":
                    assert err["details"]["unavailable_seats"]
            differing += first.json()["error"]["message"] != extend.json()["error"]["message"]
    assert differing == 8  # rows 2, 3, 11, 12, 20, 21, 22, 23 - and 13 is the one seat-level row with no clause


async def test_the_rows_with_no_clause(world, monkeypatch):
    customer, other = user(world["db"]), user(world["db"])
    clock = _clock()
    seen: dict[str, tuple] = {}
    async with api(world["db"], clock) as c:
        cookies = session(c, customer)
        r = await c.post(URL, json={"seat_ids": [412]})
        seen["1"] = (r, 401, "AUTH_REQUIRED")
        r = await c.post(URL, json={"seat_ids": list(range(401, 412))}, cookies=cookies)
        seen["7"] = (r, 422, "SEAT_LIMIT_EXCEEDED")
        await c.post(URL, json={"seat_ids": [401, 402, 403, 404, 405, 406]}, cookies=cookies)
        r = await c.post(URL, json={"seat_ids": [407, 408, 409, 410, 411]}, cookies=cookies)
        seen["8"] = (r, 422, "SEAT_LIMIT_EXCEEDED")
        hold = (await c.post(URL, json={"seat_ids": [416]}, cookies=session(c, other))).json()
        r = await c.get(f"/api/holds/{'A' * 43}", cookies=cookies)
        seen["5"] = (r, 409, "HOLD_EXPIRED")
        r = await c.get(f"/api/holds/{hold['hold_token']}", cookies=cookies)
        seen["6"] = (r, 403, "HOLD_NOT_OWNED")
        r = await c.delete(f"/api/holds/{hold['hold_token']}/seats/417", cookies=session(c, other))
        seen["14"] = (r, 422, "VALIDATION_FAILED")
        r = await c.post("/api/showtimes/999999/holds", json={"seat_ids": [412]}, cookies=cookies)
        seen["15"] = (r, 404, "NOT_FOUND")
        r = await c.get(f"/api/holds/{'A' * 42}", cookies=cookies)
        seen["24"] = (r, 400, "REQUEST_INVALID")

        async def boom(*args, **kwargs):
            raise RuntimeError("an unhandled failure")

        monkeypatch.setattr(holds, "acquire", boom)
        r = await c.post(URL, json={"seat_ids": [412]}, cookies=cookies)
        seen["19"] = (r, 500, "INTERNAL_ERROR")
        monkeypatch.undo()
        clock.set("2026-08-14T19:45:00+05:30")
        r = await c.post(URL, json={"seat_ids": [412]}, cookies=session(c, other))
        seen["9"] = (r, 409, "SALES_CLOSED")
    for row, (r, status, code) in seen.items():
        err = r.json()["error"]
        expected = PUBLISHED[row].replace("a1b2c3d4", err["request_id"])
        assert (r.status_code, err["code"], err["message"]) == (status, code, expected), row
        assert re.fullmatch(r"[0-9a-f]{8}", err["request_id"])
    assert "quote" not in seen["7"][0].text and "If you need help, quote " in seen["19"][0].text


async def test_429_names_the_bucket_that_refused_and_the_header_matches_the_sentence(world):
    one = user(world["db"])
    async with api(world["db"], _clock()) as c:
        cookies = session(c, one)
        statuses = [(await c.get(f"/api/holds/{'A' * 43}", cookies=cookies)) for _ in range(21)]
        per_user = statuses[-1]
    assert [r.status_code for r in statuses[:20]] == [409] * 20
    assert per_user.status_code == 429 and per_user.headers["Retry-After"] == "3"
    assert per_user.json()["error"]["message"] == "Too many attempts. Try again in 3 seconds."
    users = [user(world["db"]) for _ in range(61)]
    flush()  # a fresh set of buckets: the per-IP one above was part-spent
    async with api(world["db"], _clock()) as c:
        for u in users[:60]:
            assert (await c.get(f"/api/holds/{'A' * 43}", cookies=session(c, u))).status_code == 409
        per_ip = await c.get(f"/api/holds/{'A' * 43}", cookies=session(c, users[60]))
    assert per_ip.status_code == 429 and per_ip.headers["Retry-After"] == "1"
    assert per_ip.json()["error"]["message"] == "Too many attempts. Try again in 1 second."


def test_no_published_string_leaks_anything_internal_or_apologises():
    leak = re.compile(r'traceback|File "|SELECT |INSERT |UPDATE |psycopg|sqlalchemy|\.py\b|booking_seat|showtime_seat|'
                      r"redis://|postgres://|Error:", re.I)
    assert sorted(int(k) for k in PUBLISHED if k.isdigit()) == list(range(1, 25))  # 24 rows, plus 2b, 3b and 4b
    assert not [k for k, v in PUBLISHED.items() if leak.search(v)]


def test_the_codes_asserted_are_the_codes_the_four_endpoints_declare():
    import json

    contract = json.loads((REPO / "docs/03 PRD/api/contract.json").read_text(encoding="utf-8"))
    declared = {code for e in contract["endpoints"] if e["id"] in ("EP-HLD-01", "EP-HLD-02", "EP-HLD-03", "EP-HLD-04")
                for code in e["errors"]}
    asserted = {code for *_, code in HOLD_ROWS.values()} | {"AUTH_REQUIRED", "SEAT_LIMIT_EXCEEDED", "HOLD_EXPIRED",
                                                             "HOLD_NOT_OWNED", "NOT_FOUND", "REQUEST_INVALID",
                                                             "INTERNAL_ERROR", "SALES_CLOSED", "RATE_LIMITED",
                                                             "DEPENDENCY_UNAVAILABLE"}
    assert asserted == declared

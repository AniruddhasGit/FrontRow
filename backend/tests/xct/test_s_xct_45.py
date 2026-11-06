"""S-XCT-45 (PRD P-XCT-30): 720 showtimes from the injected clock, deterministic occupancy, 11,003 bookings,
idempotently. Every figure is read from docs/06 DataModel/seed/expected_summary.json, never copied here - except the
few CR-001 (four films on fixed screens, +105-minute second screens) and SRC-006 (base price 1299) moved before that
generated oracle was re-derived; each of those carries its citation.

The queue clause ("the queue's message count being 0 after the run") is asserted on the queue itself: this module's
seed runs with QUEUE_URL naming a fresh ElasticMQ queue, and that queue's message counts (visible, in flight and
delayed) are read after the run. The outbox, the only route a receipt job has onto the queue (FR-ADR-031), is
counted too.
"""

from __future__ import annotations

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.domain import reference
import os
import uuid

import pytest

from tests.dbkit import create_database, drop_database, owner_sql
from tests.seed.kit import NOW, SUMMARY, one, run_seed, seed, table_counts  # noqa: F401
from tests.xct._support import rg

IST = ZoneInfo("Asia/Kolkata")
QUEUE: dict[str, object] = {}


def _sqs():
    import boto3

    endpoint = os.environ.get("TEST_QUEUE_ENDPOINT")
    if not endpoint:
        pytest.fail("TEST_QUEUE_ENDPOINT is not set: run the suite with `docker compose --profile test run --rm test`", pytrace=False)
    return boto3.client("sqs", region_name="ap-south-1", endpoint_url=endpoint), endpoint


@pytest.fixture(scope="module")
def seeded():
    """tests/seed/kit.py's seeded, with QUEUE_URL naming a fresh ElasticMQ queue for the run, so the queue can be counted."""
    sqs, endpoint = _sqs()
    url = sqs.create_queue(QueueName=f"xct45-{uuid.uuid4().hex[:12]}")["QueueUrl"]
    QUEUE.update(sqs=sqs, url=endpoint + "/" + url.split("/", 3)[3])
    db = create_database(migrate=True)
    saved = os.environ.get("QUEUE_URL")
    os.environ["QUEUE_URL"] = QUEUE["url"]
    try:
        code, lines = run_seed(db.app_url)
        assert code == 0, lines
        yield db, lines
    finally:
        if saved is None:
            os.environ.pop("QUEUE_URL", None)
        else:
            os.environ["QUEUE_URL"] = saved
        drop_database(db)
TODAY_START = datetime.combine(NOW.astimezone(IST).date(), time(0), tzinfo=IST)


def test_720_showtimes_at_the_four_local_starts(seeded):
    db, _ = seeded
    assert one(db, "SELECT count(*) FROM showtime") == SUMMARY["schedule"]["showtimes"] == 720
    starts = {t for (t,) in owner_sql(db, "SELECT DISTINCT to_char(starts_at AT TIME ZONE 'Asia/Kolkata', 'HH24:MI') FROM showtime")}
    # the SLOTS, plus the second screen of a two-screen film 105 minutes later (CR-001 A.2)
    assert starts == set(SUMMARY["schedule"]["local_starts"]) | {"12:45", "16:15", "19:45", "23:15"}
    assert one(db, "SELECT data_type FROM information_schema.columns WHERE table_name = 'showtime' "
                   "AND column_name = 'starts_at'") == "timestamp with time zone"


def test_no_date_is_hardcoded_in_the_seed():
    assert rg(r"\b20[0-9]{2}-[0-9]{2}-[0-9]{2}\b", "scripts/seed.py") == []


def test_360_before_today_and_360_from_today_against_the_injected_clock(seeded):
    db, _ = seeded
    assert one(db, "SELECT count(*) FROM showtime WHERE starts_at < %s", (TODAY_START,)) == SUMMARY["schedule"]["past"]
    assert one(db, "SELECT count(*) FROM showtime WHERE starts_at >= %s", (TODAY_START,)) == SUMMARY["schedule"]["from_today"]
    first = one(db, "SELECT min(starts_at) FROM showtime").astimezone(IST).date()
    assert first == NOW.astimezone(IST).date() - timedelta(days=15)


def test_films_have_240_240_120_120_showtimes_and_the_runtimes_run_90_to_120(seeded):
    db, _ = seeded  # CR-001 A.2: films 1 and 2 on two screens each, films 3 and 4 on one
    assert [c for _, c in owner_sql(db, "SELECT m.title, count(*) FROM showtime s JOIN movie m ON m.id = s.movie_id "
                                        "GROUP BY 1 ORDER BY 1")] == [240, 240, 120, 120]
    assert [r for (r,) in owner_sql(db, "SELECT runtime_minutes FROM movie ORDER BY title")] == list(range(90, 121, 10))


def test_ends_at_is_start_plus_runtime_plus_changeover_and_nothing_overlaps(seeded):
    db, _ = seeded
    assert one(db, "SELECT count(*) FROM showtime s JOIN movie m ON m.id = s.movie_id "
                   "WHERE s.ends_at <> s.starts_at + make_interval(mins => m.runtime_minutes + 20)") == 0
    # the 23:15 start of the 100-minute film (Screen 3, CR-001 A.2) ends 01:15 the next local day
    late = owner_sql(db, "SELECT DISTINCT to_char(s.ends_at AT TIME ZONE 'Asia/Kolkata', 'HH24:MI') FROM showtime s "
                         "JOIN movie m ON m.id = s.movie_id WHERE m.runtime_minutes = 100 "
                         "AND to_char(s.starts_at AT TIME ZONE 'Asia/Kolkata', 'HH24:MI') = '23:15'")
    assert late == [("01:15",)]
    assert one(db, "SELECT max(extract(epoch FROM ends_at - starts_at)) / 60 FROM showtime") == 120 + 20  # CR-001: longest film 120
    assert one(db, "SELECT count(*) FROM showtime a JOIN showtime b ON a.screen_id = b.screen_id AND a.id < b.id "
                   "AND a.starts_at < b.ends_at AND b.starts_at < a.ends_at") == 0


def test_both_formats_are_carried(seeded):
    db, _ = seeded
    by_format = dict(owner_sql(db, "SELECT f.name, count(*) FROM showtime s JOIN format f ON f.id = s.format_id GROUP BY 1"))
    assert by_format == SUMMARY["schedule"]["by_format"]


def test_the_worked_example_k231(seeded):
    db, _ = seeded
    first = one(db, "SELECT min(starts_at) FROM showtime").astimezone(IST).date()
    starts = datetime.combine(first + timedelta(days=9), time(18, 0), tzinfo=IST)
    row = owner_sql(db, "SELECT m.title, (SELECT count(*) FROM booking_seat bs WHERE bs.showtime_id = s.id), "
                        "to_char(s.ends_at AT TIME ZONE 'Asia/Kolkata', 'HH24:MI') FROM showtime s "
                        "JOIN movie m ON m.id = s.movie_id JOIN screen sc ON sc.id = s.screen_id "
                        "WHERE sc.name = 'SCREEN 4' AND s.starts_at = %s", (starts,))
    assert row == [("DEMO MOVIE 02", 126, "20:00")]  # CR-001 A.2: Screen 4 plays film 2 (100 minutes)


def test_occupancy_never_reaches_0_or_100_and_is_taken_from_row_a_seat_1(seeded):
    db, _ = seeded
    assert one(db, "SELECT count(*) FROM showtime s WHERE (SELECT count(*) FROM booking_seat bs WHERE bs.showtime_id = s.id) "
                   "NOT BETWEEN 1 AND s.seat_count_at_creation - 1") == 0
    # contiguous from the front: no unbooked seat sits before a booked one in (grid_row, grid_col) order
    assert one(db, """SELECT count(*) FROM showtime_seat ss JOIN seat free ON free.id = ss.seat_id
                      WHERE NOT EXISTS (SELECT 1 FROM booking_seat bs WHERE bs.showtime_id = ss.showtime_id AND bs.seat_id = ss.seat_id)
                        AND EXISTS (SELECT 1 FROM booking_seat bs JOIN seat taken ON taken.id = bs.seat_id
                                    WHERE bs.showtime_id = ss.showtime_id
                                      AND (taken.grid_row, taken.grid_col) > (free.grid_row, free.grid_col))""") == 0


def test_the_inventory_figures(seeded):
    db, _ = seeded
    b = SUMMARY["bookings"]
    assert one(db, "SELECT count(*) FROM booking_seat") == b["booked_seats"] == 58800
    assert one(db, "SELECT count(*) FROM booking") == b["bookings"] == 11003
    assert owner_sql(db, "SELECT min(c), max(c) FROM (SELECT count(*) c FROM booking GROUP BY user_id) x") == [
        (b["per_customer_min"], b["per_customer_max"])]
    assert one(db, "SELECT count(DISTINCT user_id) FROM booking") == 50
    sizes = dict(owner_sql(db, "SELECT n, count(*) FROM (SELECT count(*) n FROM booking_seat GROUP BY booking_id) x GROUP BY 1"))
    assert {str(k): v for k, v in sizes.items()} == b["booking_size_histogram"]
    assert one(db, "SELECT count(*) FROM showtime_seat") == SUMMARY["tables"]["showtime_seat"]["rows"] == 115200
    assert round(58800 / 115200 * 100, 2) == float(next(c["derived"] for c in SUMMARY["published_figure_checks"]
                                                       if c["figure"] == "mean_occupancy_percent_2dp"))
    # SRC-006 base 1299 over CR-001's row widths: 45,800 Standard x 1299 + 12,400 Premium x 1461 + 600 Recliner x 1732
    assert one(db, "SELECT sum(total_paise) FROM booking") == 37400 * 1299 + 20120 * 1461 + 1280 * 1732 == 80194880  # CR-003 rows


def test_every_table_count_the_oracle_states(seeded):
    db, _ = seeded
    counts = table_counts(db)
    stated = {t: v["rows"] for t, v in SUMMARY["tables"].items() if v["rows"] is not None}
    stated.update(movie=4, movie_genre=8)  # CR-001 A.2: four films, two genres each
    assert {t: counts[t] for t in stated} == stated


def test_payments_captured_and_dispatch_rows_suppressed_and_no_receipt_job(seeded):
    db, _ = seeded
    assert one(db, "SELECT count(*) FROM booking b LEFT JOIN payment p ON p.id = b.payment_id "
                   "WHERE p.state IS DISTINCT FROM 'captured'") == 0
    assert one(db, "SELECT count(*) FROM booking b LEFT JOIN receipt_dispatch r ON r.booking_id = b.id "
                   "WHERE r.status IS DISTINCT FROM 'suppressed' OR r.attempts <> 0 OR r.sent_at IS NOT NULL "
                   "OR r.claimed_at IS NOT NULL") == 0
    assert one(db, "SELECT count(*) FROM outbox_message WHERE topic = 'receipt.send'") == 0
    names = ["ApproximateNumberOfMessages", "ApproximateNumberOfMessagesNotVisible", "ApproximateNumberOfMessagesDelayed"]
    attrs = QUEUE["sqs"].get_queue_attributes(QueueUrl=QUEUE["url"], AttributeNames=names)["Attributes"]
    assert {n: int(attrs[n]) for n in names} == dict.fromkeys(names, 0)


def test_the_oracle_invariants_hold(seeded):
    """Every oracle invariant written as a count-to-zero query, run verbatim. The prose ones (12, 14..18) are
    asserted by their own tests in this module, S-XCT-44 and S-XCT-48."""
    db, _ = seeded
    ran = []
    for inv in SUMMARY["invariants"]:
        sql, _, expect = inv["sql"].partition("--")
        if sql.startswith("SELECT count(*)") and expect.strip().startswith("0"):
            assert one(db, sql) == 0, inv["id"]
            ran.append(inv["id"])
    assert len(ran) == 12, ran


def test_every_reference_is_valid_under_r5(seeded):
    db, _ = seeded
    refs = [r for (r,) in owner_sql(db, "SELECT reference FROM booking")]
    assert len(refs) == 11003
    assert all(reference.is_valid(r) for r in refs)


def test_a_second_run_finds_all_720_and_inserts_nothing(seeded):
    db, _ = seeded
    before = table_counts(db)
    movies = dict(owner_sql(db, "SELECT id, movie_id FROM showtime"))
    later = NOW + timedelta(days=3)  # the clock moved; the anchor comes from the data, not the clock
    code, lines = run_seed(db.app_url, now=later)
    assert code == 0, lines
    assert table_counts(db) == before
    assert dict(owner_sql(db, "SELECT id, movie_id FROM showtime")) == movies
    assert one(db, "SELECT count(*) FROM showtime") == 720


def test_an_interrupted_run_is_completed_with_the_same_films(seeded, monkeypatch):
    """The plan is a pure function of the anchor: rows missing from it are the only ones a run inserts."""
    db, _ = seeded
    first = one(db, "SELECT min(starts_at) FROM showtime").astimezone(IST).date()
    films = [one(db, "SELECT id FROM movie WHERE title = %s", (f"DEMO MOVIE {i + 1:02d}",)) for i in range(4)]
    screens = [one(db, "SELECT id FROM screen WHERE name = %s", (f"SCREEN {n}",)) for n in range(1, 7)]
    formats = [one(db, "SELECT id FROM format WHERE name = %s", (f,)) for f in seed.FORMATS]
    plan = list(seed.schedule(first, screens, films, [90 + i * 10 for i in range(4)], formats, 20))
    stored = {(s, t): m for s, t, m in owner_sql(db, "SELECT screen_id, starts_at, movie_id FROM showtime")}
    assert {(p["screen_id"], p["starts_at"]): p["movie_id"] for p in plan} == stored

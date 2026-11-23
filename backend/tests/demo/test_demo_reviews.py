"""Owner 2026-11-23: the demo crowd's ratings and reviews (scripts/demo_reviews.py), and the one rule that keeps them
circulating - every rating read shows a row only from its created_at on (catalogue.rating_shown), so the future-dated
part of the crowd appears day by day with no job.

The pay lane's world (tests/pay/kit.py) plus three films named and cast like the owner's demo catalogue
(scripts/demo_films.py), one Coming soon and one draft. The clock is injected; the script gets `now` as an argument.
"""

from __future__ import annotations

import importlib.util
import re
from datetime import datetime, timedelta

import psycopg
import pytest

from tests.brw.kit import make_lookup
from tests.pay.kit import F7, F8, SHOWTIME, api, book, clock_at, cookies, count, owner_sql, user, world7
from tests.xct._support import REPO

pytestmark = pytest.mark.anyio
NOW = "2026-08-15T09:30:00+00:00"  # 15:00 IST on 15 Aug; the films are on show 14 Aug - 31 Dec
DOMAIN = "demo.frontrow.invalid"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, REPO / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


reviews, films = _load("demo_reviews"), _load("demo_films")


@pytest.fixture(scope="module")
def world(migrated_db):
    w = world7(migrated_db)
    db = w["db"]
    owner_sql(db, "UPDATE movie SET display_until = '2026-12-31T00:00:00+05:30' WHERE id = %s", (w["movie"],))  # weeks of reads
    genre = {}
    picked = [f for f in films.FILMS if f[0] in ("Apartment 4B", "The Marigold Reunion", "Aria and the Star Whales")]
    ids = [w["movie"]]
    for (title, _, _, _, genres, _), release in zip(picked, ("2026-08-01", "2026-07-20", "2026-08-13")):
        mid = owner_sql(db, "INSERT INTO movie (title, synopsis, runtime_minutes, certification_id, language_id, published_at, "
                            "display_from, display_until, release_date, cast_members, crew_members, version) SELECT %s, 'x', 100, "
                            "certification_id, language_id, published_at, display_from, display_until, %s, %s, %s, 1 FROM movie "
                            "WHERE id = %s RETURNING id", (title, release, *films.DETAILS[title], w["movie"]))[0][0]
        for g in genres:
            genre[g] = genre.get(g) or make_lookup(db, "genre", g)
            owner_sql(db, "INSERT INTO movie_genre (movie_id, genre_id) VALUES (%s, %s)", (mid, genre[g]))
        ids.append(mid)
    soon = owner_sql(db, "INSERT INTO movie (title, synopsis, runtime_minutes, certification_id, language_id, published_at, display_from, "
                         "display_until, release_date, version) SELECT 'Caldera', 'x', 100, certification_id, language_id, published_at, "
                         "display_from, display_until, '2026-08-30', 1 FROM movie WHERE id = %s RETURNING id", (w["movie"],))[0][0]
    draft = owner_sql(db, "INSERT INTO movie (title, synopsis, runtime_minutes, certification_id, language_id, display_from, "
                          "display_until, version) SELECT 'Voidbound', 'x', 100, certification_id, language_id, display_from, "
                          "display_until, 1 FROM movie WHERE id = %s RETURNING id", (w["movie"],))[0][0]
    seed_customer = user(db, email=f"customer-01@{DOMAIN}")
    lines: list[str] = []
    with psycopg.connect(db.app_url) as conn:  # the application role, so a missing grant fails here
        done = reviews.run(conn, datetime.fromisoformat(NOW), lines.append)
    return {**w, "films": ids, "soon": soon, "draft": draft, "seed_customer": seed_customer, "done": done, "lines": lines}


def _shown(db, film: int, at: str = NOW, text: bool = False) -> int:
    extra = " AND review_text IS NOT NULL" if text else ""
    return count(db, f"SELECT count(*) FROM movie_rating WHERE movie_id = %s AND created_at <= %s{extra}", (film, at))


def _fragments_only(text: str, pool: list[str]) -> bool:
    for line in sorted(pool, key=len, reverse=True):
        text = text.replace(line, "")
    return text.strip() == ""


def test_hundreds_per_released_film_a_real_spread_and_none_for_coming_soon_or_drafts(world):
    db = world["db"]
    assert set(world["done"]) == {"The Long Night", "Apartment 4B", "The Marigold Reunion", "Aria and the Star Whales"}
    for film in world["films"]:
        shown, total = _shown(db, film), count(db, "SELECT count(*) FROM movie_rating WHERE movie_id = %s", (film,))
        assert 120 <= shown <= 450 and total > shown, (film, shown, total)  # the rest arrive over the next 120 days
        assert count(db, "SELECT count(*) FROM movie_rating WHERE movie_id = %s AND created_at > %s::timestamptz + interval "
                         "'120 days 1 minute'", (film, NOW)) == 0
        scores = [s for (s,) in owner_sql(db, "SELECT score FROM movie_rating WHERE movie_id = %s", (film,))]
        assert sum(s <= 4 for s in scores) >= 5 and sum(5 <= s <= 6 for s in scores) >= 5 and sum(s >= 9 for s in scores) >= 5
        assert 4.5 <= sum(scores) / len(scores) <= 9.2
        texts = _shown(db, film, text=True)
        assert 0.18 * shown <= texts <= 0.47 * shown, (film, texts, shown)
    # a film released two days ago only has ratings since its release
    assert count(db, "SELECT count(*) FROM movie_rating WHERE movie_id = %s AND created_at < '2026-08-13T04:30:00Z'",
                 (world["films"][3],)) == 0
    for film in (world["soon"], world["draft"]):
        assert count(db, "SELECT count(*) FROM movie_rating WHERE movie_id = %s", (film,)) == 0
    assert count(db, "SELECT count(*) FROM movie_rating WHERE user_id = %s", (world["seed_customer"],)) == 0
    raters = count(db, "SELECT count(DISTINCT user_id) FROM movie_rating")
    assert raters <= reviews.CROWD_SIZE and count(db, "SELECT max(n) FROM (SELECT count(*) n FROM movie_rating "
                                                      "GROUP BY user_id, movie_id) x") == 1


def test_the_text_follows_the_score_and_names_nothing_from_the_catalogue(world):
    db = world["db"]
    rows = owner_sql(db, "SELECT score, review_text FROM movie_rating WHERE review_text IS NOT NULL")
    assert len(rows) > 300
    for score, text in rows:
        assert _fragments_only(text, reviews.tone(score)), (score, text)
    assert len({t for _, t in rows}) > 0.7 * len(rows)  # sentences are mixed, so exact repeats are rare
    assert len(reviews.POSITIVE) >= 120 and len(reviews.MIXED) >= 70 and len(reviews.NEGATIVE) >= 70
    forbidden = {t for (t,) in owner_sql(db, "SELECT title FROM movie")} | {g for (g,) in owner_sql(db, "SELECT name FROM genre")}
    for cast, crew in owner_sql(db, "SELECT cast_members, crew_members FROM movie WHERE cast_members IS NOT NULL"):
        for line in cast.splitlines():
            name, _, role = line.partition(":")
            forbidden |= {name.strip(), role.replace("(voice)", "").strip()}
        forbidden |= {line.partition(":")[0].strip() for line in crew.splitlines()}
    forbidden |= {"scary", "funny", "laugh", "explosion", "explosions", "animation", "animated", "cartoon", "kids", "monster",
                  "ghost", "alien", "dragon", "magic", "battle", "fight", "hero", "villain", "effects"}
    assert len(forbidden) > 60
    pattern = re.compile("|".join(rf"(?<!\w){re.escape(w)}(?!\w)" for w in forbidden if w), re.IGNORECASE)
    names = [n for (n,) in owner_sql(db, "SELECT display_name FROM users WHERE display_name IS NOT NULL")]
    assert [t for t in reviews.POSITIVE + reviews.MIXED + reviews.NEGATIVE + names if pattern.search(t)] == []


def test_helpful_votes_rank_some_reviews_never_by_the_author_and_never_before_the_review(world):
    db = world["db"]
    assert count(db, "SELECT count(*) FROM review_vote v JOIN movie_rating r ON r.id = v.rating_id WHERE v.user_id = r.user_id") == 0
    assert count(db, "SELECT count(*) FROM review_vote v JOIN movie_rating r ON r.id = v.rating_id "
                     "WHERE v.created_at <= r.created_at OR r.review_text IS NULL") == 0
    per = [n for (n,) in owner_sql(db, "SELECT count(v.id) FROM movie_rating r LEFT JOIN review_vote v ON v.rating_id = r.id "
                                       "WHERE r.review_text IS NOT NULL GROUP BY r.id")]
    assert sum(n == 0 for n in per) > len(per) / 3 and max(per) >= 5


def test_a_second_run_writes_nothing(world):
    db = world["db"]
    before = [count(db, f"SELECT count(*) FROM {t}") for t in ("users", "movie_rating", "review_vote")]
    lines: list[str] = []
    with psycopg.connect(db.app_url) as conn:
        assert reviews.run(conn, datetime.fromisoformat(NOW) + timedelta(days=3), lines.append) == {}
    assert [count(db, f"SELECT count(*) FROM {t}") for t in ("users", "movie_rating", "review_vote")] == before


def test_the_crowd_is_the_one_the_seat_fill_books_for():
    from app.domain import demo_fill

    assert (reviews.CROWD_FIRST, reviews.CROWD_SIZE) == (demo_fill.CROWD_FIRST, demo_fill.CROWD_SIZE)


async def test_a_future_dated_rating_is_invisible_on_every_read_path_until_its_day(world):
    db, film = world["db"], world["movie"]
    clock = clock_at(NOW)
    async with api(db, clock) as c:
        def card(listing):
            return next(m for m in listing["movies"] if m["id"] == film)["rating"]

        shown = _shown(db, film)
        assert card((await c.get("/api/movies")).json())["count"] == shown
        detail = (await c.get(f"/api/movies/{film}")).json()["rating"]
        assert detail["count"] == sum(detail["breakdown"]) == shown
        page = (await c.get(f"/api/movies/{film}/reviews")).json()
        assert page["count"] == _shown(db, film, text=True)
        assert all(datetime.fromisoformat(i["written_at"]) <= clock.now() for i in page["items"])
        top = (await c.get(f"/api/movies/{film}/reviews", params={"sort": "helpful"})).json()["items"][0]
        assert top["helpful"] == count(db, "SELECT count(*) FROM review_vote WHERE rating_id = %s AND created_at <= %s",
                                       (top["id"], NOW)) > 0
        # A review dated next month: not listed, not counted, and cannot be voted on yet
        ahead = owner_sql(db, "SELECT id FROM movie_rating WHERE movie_id = %s AND review_text IS NOT NULL AND created_at > "
                              "%s::timestamptz + interval '20 days' ORDER BY created_at LIMIT 1", (film, NOW))[0][0]
        voter = user(db)
        r = await c.post(f"/api/me/reviews/{ahead}/helpful", cookies=cookies(c, voter))
        assert r.status_code == 404
        later = (datetime.fromisoformat(NOW) + timedelta(days=45)).isoformat()
        clock.set(later)
        assert card((await c.get("/api/movies")).json())["count"] == _shown(db, film, later) > shown
        assert (await c.get(f"/api/movies/{film}")).json()["rating"]["count"] == _shown(db, film, later)
        assert ahead in [i["id"] for i in (await c.get(f"/api/movies/{film}/reviews")).json()["items"]]
        assert (await c.post(f"/api/me/reviews/{ahead}/helpful", cookies=cookies(c, voter))).status_code == 200


async def test_a_writers_own_rating_shows_at_once_even_over_a_future_dated_crowd_row(world):
    db, film = world["db"], world["movie"]
    clock = clock_at("2026-08-14T15:00:00+00:00")  # after showtime 7 started
    viewer = user(db)
    book(db, viewer, SHOWTIME, [F7])
    async with api(db, clock) as c:
        before = (await c.get(f"/api/movies/{film}")).json()["rating"]["count"]
        r = await c.put(f"/api/me/ratings/{film}", json={"score": 3}, cookies=cookies(c, viewer))
        assert r.status_code == 200 and r.json()["rating"]["count"] == before + 1
        assert (await c.get(f"/api/movies/{film}")).json()["rating"]["count"] == before + 1
        # a crowd account whose rating is dated weeks ahead re-rates after seeing the film: it shows now
        crowd, ahead = owner_sql(db, "SELECT user_id, id FROM movie_rating WHERE movie_id = %s AND created_at > %s::timestamptz "
                                     "+ interval '10 days' LIMIT 1", (film, NOW))[0]
        book(db, crowd, SHOWTIME, [F8])
        r = await c.put(f"/api/me/reviews/{film}", json={"score": 9, "text": "Better than I expected."}, cookies=cookies(c, crowd))
        assert r.status_code == 200 and r.json()["rating"]["count"] == before + 2
        assert ahead in [i["id"] for i in (await c.get(f"/api/movies/{film}/reviews")).json()["items"]]


async def test_the_listing_cache_holds_a_rating_count_no_longer_than_its_ttl(world):
    from tests.pay.kit import r_call

    async with api(world["db"], clock_at(NOW), LISTING_CACHE_TTL_SECONDS="60") as c:
        assert (await c.get("/api/movies")).status_code == 200
        keys = [k for k in r_call("KEYS", "cache:listing:*") if not str(k).endswith("generation")]
        assert keys and all(0 < r_call("TTL", k) <= 60 for k in keys)

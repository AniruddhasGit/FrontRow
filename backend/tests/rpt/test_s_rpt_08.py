"""S-RPT-08 - per-film rows inside the caller's scope, under a total order and a 100-row cap (P-RPT-05)."""

from __future__ import annotations

import pytest

from tests.dbkit import create_database, drop_database
from tests.rpt.kit import DAY, client, film, get, make_client, prd_world, sell, show, user_row, venue  # noqa: F401


@pytest.fixture(scope="module")
def world(migrated_db):
    return prd_world(migrated_db)


def test_one_film_for_m_two_for_the_admin(client, world):
    films = get(client, world["M"], DAY).json()["films"]
    assert films == [{"movie_id": 1, "title": "DEMO MOVIE 01", "shows": 2, "seats_sold": 109, "capacity": 370,
                      "occupancy_pct": 29.5, "takings_paise": 2783331}]
    admin = get(client, world["admin"], DAY).json()["films"]
    assert {f["title"] for f in admin} == {"DEMO MOVIE 01", "DEMO MOVIE 02"}


def test_scoped_figures_differ_from_the_cinema(client, world):
    show(world, 107, 1, 1, "2026-08-14T08:00:00Z")
    sell(world, 107, 4, 25000)
    m = next(f for f in get(client, world["M"], DAY).json()["films"] if f["movie_id"] == 1)
    a = next(f for f in get(client, world["admin"], DAY).json()["films"] if f["movie_id"] == 1)
    assert m["seats_sold"] == 109 < a["seats_sold"]


def test_a_total_order_on_a_title_tie(client, world):
    twin_a, twin_b = film(world, "DEMO TWIN"), film(world, "DEMO TWIN")
    for i, m in enumerate((twin_b, twin_a)):
        st = show(world, None, 6, m, f"2026-08-14T0{2 + i}:00:00Z")
        sell(world, st, 2, 25000)
    orders = {tuple(f["movie_id"] for f in get(client, world["admin"], DAY).json()["films"]) for _ in range(10)}
    assert len(orders) == 1
    (order,) = orders
    assert order.index(min(twin_a, twin_b)) < order.index(max(twin_a, twin_b))


def films_world(db, n: int) -> dict:
    """n distinct films, each with one showtime on screen 3 or 5 inside the Friday window and one captured booking."""
    w = venue(db, {3: 10, 5: 10})
    w["movies"] = []
    for i in range(n):
        m = film(w, f"DEMO MOVIE {i + 1:03d}")
        st = show(w, None, 3 if i % 2 else 5, m, f"2026-08-14T{i % 18:02d}:{(i // 18) * 5:02d}:00Z")
        sell(w, st, 1, 25000 + i)
        w["movies"].append(m)
    return w


@pytest.mark.parametrize("count, truncated", [(100, False), (101, True)])
def test_the_cap(count, truncated):
    db = create_database(migrate=True)
    try:
        w = films_world(db, count)
        admin = user_row(db, "admin")
        with make_client(db) as c:
            body = get(c, admin, DAY).json()
    finally:
        drop_database(db)
    assert len(body["films"]) == 100 and body["films_truncated"] is truncated
    if not truncated:
        assert {f["movie_id"] for f in body["films"]} == set(w["movies"])
    else:
        assert body["takings_paise"] > sum(f["takings_paise"] for f in body["films"])
        assert body["seats_sold"] > sum(f["seats_sold"] for f in body["films"])

"""Fixtures and row builders shared by the admin-lane tests (tests/adm/).

A real app on a throwaway migrated database (tests/dbkit.py), connected as frontrow_app, with a FakeClock.
Sessions are minted with the product's own token function, because sign-in belongs to the account lane.
Fixture rows are written as the OWNER, directly: they are the state a test starts from, not the thing it
proves. Names are demonstration values; nothing here is the seed's ASSUMED vocabulary.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from app.core.security import SESSION_COOKIE, issue_session_token
from app.main import create_app
from tests.dbkit import app_settings, insert_user, owner_sql
from tests.test_health import ok_probe


def tag() -> str:
    return uuid.uuid4().hex[:8]


@pytest.fixture
def client(migrated_db, clock):
    application = create_app(app_settings(migrated_db), clock=clock, probes=[ok_probe("postgres"), ok_probe("redis")])
    with TestClient(application, raise_server_exceptions=False) as c:
        c.clock, c.db = clock, migrated_db
        yield c


def sign_in(client, role: str = "admin") -> int:
    user_id = insert_user(client.db, role=role)
    token = issue_session_token(user_id=user_id, role=role, password_version=1, now=client.clock.now(),
                                settings=app_settings(client.db))
    client.cookies.set(SESSION_COOKIE, token)
    return user_id


def one(db, statement: str, params=None):
    return owner_sql(db, statement, params)[0][0]


def count(db, table: str, where: str = "true", params=None) -> int:
    return one(db, f"SELECT count(*) FROM {table} WHERE {where}", params)


def audit_rows(db, where: str = "true", params=None) -> list[tuple]:
    return owner_sql(db, f"SELECT action, entity_type, entity_id, before, after, actor_user_id FROM audit_log "
                         f"WHERE {where} ORDER BY id", params)


def make_cinema(db, timezone: str = "Asia/Kolkata", name: str | None = None) -> int:
    return one(db, "INSERT INTO cinema (name, timezone, version) VALUES (%s, %s, 1) RETURNING id",
               (name or f"Venue {tag()}", timezone))


def make_screen(db, cinema_id: int | None = None, name: str | None = None, active: bool = True) -> int:
    cinema_id = cinema_id or make_cinema(db)
    return one(db, "INSERT INTO screen (cinema_id, name, is_active, version) VALUES (%s, %s, %s, 1) RETURNING id",
               (cinema_id, name or f"Hall {tag()}", active))


def make_category(db, uplift: int = 0, name: str | None = None) -> int:
    return one(db, "INSERT INTO seat_category (name, uplift_basis_points, version) VALUES (%s, %s, 1) RETURNING id",
               (name or f"Cat {tag()}", uplift))


def make_seat(db, screen_id: int, label: str, category_id: int, grid: tuple[int, int] | None = None,
              active: bool = True) -> int:
    row, number = label[0], int(label[1:])
    grid = grid or (ord(row) - 64, number)
    return one(db, "INSERT INTO seat (screen_id, row_label, seat_number, grid_row, grid_col, seat_category_id, is_active) "
                   "VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id", (screen_id, row, number, grid[0], grid[1],
                                                                         category_id, active))


def make_seats(db, screen_id: int, n: int, category_id: int | None = None) -> list[int]:
    category_id = category_id or make_category(db)
    return [make_seat(db, screen_id, f"{chr(65 + i // 20)}{i % 20 + 1}", category_id) for i in range(n)]


def make_movie(db, runtime: int = 148, title: str | None = None, window: tuple[str, str] | None = None) -> int:
    cert = one(db, "INSERT INTO certification (name, is_active) VALUES (%s, true) RETURNING id", (f"Cert {tag()}",))
    lang = one(db, "INSERT INTO language (name, is_active) VALUES (%s, true) RETURNING id", (f"Lang {tag()}",))
    lo, hi = window or (None, None)
    return one(db, "INSERT INTO movie (title, synopsis, runtime_minutes, certification_id, language_id, display_from, "
                   "display_until, version) VALUES (%s, 'Demonstration film.', %s, %s, %s, %s, %s, 1) RETURNING id",
               (title or f"DEMO {tag()}", runtime, cert, lang, lo, hi))


def make_showtime(db, screen_id: int, movie_id: int, starts: str, ends: str, price: int = 25000,
                  with_seats: bool = True) -> int:
    """A stored showtime, its seat set written the same way the product writes it."""
    st = one(db, "INSERT INTO showtime (movie_id, screen_id, starts_at, ends_at, base_price_paise, seat_count_at_creation, "
                 "version) VALUES (%s, %s, %s, %s, %s, 0, 1) RETURNING id", (movie_id, screen_id, starts, ends, price))
    if with_seats:
        owner_sql(db, "INSERT INTO showtime_seat (showtime_id, seat_id) SELECT %s, id FROM seat WHERE screen_id = %s "
                      "AND is_active", (st, screen_id))
        owner_sql(db, "UPDATE showtime SET seat_count_at_creation = (SELECT count(*) FROM showtime_seat "
                      "WHERE showtime_id = %s) WHERE id = %s", (st, st))
    return st


def routes(app) -> list:
    """Every mounted route object, with its resolved dependant. FastAPI 0.143 wraps each included router
    in an _IncludedRouter, so `app.routes` alone holds no APIRoute and a walk over it passes vacuously."""
    found = []

    def walk(items) -> None:
        for r in items:
            nested = []
            for attr in ("effective_candidates", "effective_low_priority_routes"):
                got = getattr(r, attr, ())
                nested.extend(got() if callable(got) else got)
            if nested:
                walk(nested)
            elif hasattr(r, "dependant"):
                found.append(r)

    walk(app.routes)
    assert found, "the route walk found nothing - it would pass vacuously"
    return found


def body_fields(route) -> set[str]:
    """The field names of the route's declared request body model (empty if it takes no body)."""
    names: set[str] = set()
    for param in route.dependant.body_params:
        model = param.field_info.annotation
        names |= set(getattr(model, "model_fields", {}))
    return names


def strip_request_id(body: dict) -> dict:
    body["error"].pop("request_id")
    return body


# ---- Phase 6: films, lookups, posters (S-ADM-21..28) ---------------------------------------------------------------


def set_clock(clock, instant: str) -> None:
    """Put the injected clock at an exact instant (never the wall clock)."""
    from datetime import datetime

    clock._now = datetime.fromisoformat(instant)


def make_lookup(db, kind: str, name: str | None = None, active: bool = True) -> int:
    assert kind in ("language", "certification", "genre", "format")
    return one(db, f"INSERT INTO {kind} (name, is_active) VALUES (%s, %s) RETURNING id", (name or f"{kind} {tag()}", active))


def vocab(db, genres: int = 2) -> dict:
    return {"language_id": make_lookup(db, "language"), "certification_id": make_lookup(db, "certification"),
            "genre_ids": [make_lookup(db, "genre") for _ in range(genres)]}


def film_body(db, **over) -> dict:
    return {"title": f"DEMO MOVIE {tag()}", "synopsis": "Demonstration film.", "runtime_minutes": 148, **vocab(db), **over}


def new_film(client, **over) -> dict:
    r = client.post("/api/admin/movies", json=film_body(client.db, **over))
    assert r.status_code == 201, r.text
    return r.json()


def movie_row(db, movie_id: int) -> tuple:
    return owner_sql(db, "SELECT * FROM movie WHERE id = %s", (movie_id,))[0]


def png(width: int, height: int, size: int | None = None) -> bytes:
    """A real 1-bit greyscale PNG, padded with an ancillary tEXt chunk to exactly `size` bytes when given."""
    import struct
    import zlib

    def chunk(kind: bytes, body: bytes) -> bytes:
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body))

    raw = (b"\x00" + b"\x00" * ((width + 7) // 8)) * height
    head = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 1, 0, 0, 0, 0))
    tail = chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b"")
    if size is None:
        return head + tail
    pad = size - len(head) - len(tail) - 12
    assert pad >= 0
    return head + chunk(b"tEXt", b"c\x00" + b"x" * (pad - 2)) + tail


def multipart(*parts: tuple) -> tuple[bytes, str]:
    """(name, filename-or-None, content-type-or-None, bytes) parts -> (body, Content-Type header)."""
    boundary = "frontrowboundary7d1"
    out = b""
    for name, filename, ctype, data in parts:
        disposition = f'form-data; name="{name}"' + (f'; filename="{filename}"' if filename is not None else "")
        out += f"--{boundary}\r\nContent-Disposition: {disposition}\r\n".encode()
        out += (f"Content-Type: {ctype}\r\n" if ctype else "").encode() + b"\r\n" + data + b"\r\n"
    return out + f"--{boundary}--\r\n".encode(), f"multipart/form-data; boundary={boundary}"


class MemoryPosters:
    """The in-memory stand-in for the private bucket: PutObject, GetObject and ListObjectsV2 by prefix."""

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    async def put(self, key: str, data: bytes, content_type: str) -> None:
        self.objects[key] = data

    def presign(self, key: str) -> str:
        return f"https://posters.invalid/{key}?X-Amz-Expires=3600"

    def keys(self, prefix: str) -> list[str]:
        return sorted(k for k in self.objects if k.startswith(prefix))


def cached_redis_url() -> str:
    """Redis database 9 of this compose project's Redis for the listing-cache tests (other lanes hard-code 10-15)."""
    import os
    import re

    return re.sub(r"/\d+$", "/9", os.environ["TEST_REDIS_URL"])


@pytest.fixture
def cached_client(migrated_db, clock):
    """The real app with a live Redis and the listing cache ON (60 s), so 'the first GET after the write' is a real
    cache read, not a cache miss. Database 9 is flushed first: listings are keyed by generation, not by database."""
    import redis

    flush = redis.Redis.from_url(cached_redis_url())
    flush.flushdb()
    flush.close()
    settings = app_settings(migrated_db, REDIS_URL=cached_redis_url(), LISTING_CACHE_TTL_SECONDS="60")
    application = create_app(settings, clock=clock, probes=[ok_probe("postgres"), ok_probe("redis")])
    with TestClient(application, raise_server_exceptions=False) as c:
        c.clock, c.db = clock, migrated_db
        yield c

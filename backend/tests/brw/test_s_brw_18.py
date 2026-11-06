"""S-BRW-18 - serve posters from our own bucket by redirect, and never hotlink (EP-BRW-03).
The real S3 adapter signs offline (botocore needs no network to presign), as in tests/adm/test_s_adm_25.py.
NOT covered here: the card's rendered fallback for a film with no poster (no img element, card text exactly the
title) - frontend, and no render test asserts it yet.
"""
from __future__ import annotations

import os
import socket
import subprocess
import sys
from urllib.parse import urlparse, urlsplit

import pytest

from app.domain.posters import S3Posters
from tests.adm.kit import client, new_film, owner_sql, sign_in  # noqa: F401
from tests.brw.kit import without_request_id
from tests.conftest import VALID_ENV
from tests.dbkit import BACKEND_DIR


def _film_with_key(client):
    sign_in(client)
    film = new_film(client)  # a draft: this endpoint applies no visibility gate (stated in the story)
    client.app.state.posters = S3Posters(client.app.state.settings)
    key = f"posters/{film['id']}/{'c' * 32}"
    owner_sql(client.db, "UPDATE movie SET poster_object_key = %s WHERE id = %s", (key, film["id"]))
    client.cookies.clear()  # a guest
    return film, key


def test_the_poster_is_a_302_to_a_one_hour_presigned_url_on_the_bucket_host_cached_300s(client):
    film, key = _film_with_key(client)
    r = client.get(f"/api/movies/{film['id']}/poster", follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["content-length"] == "0"
    location = r.headers["location"]
    assert client.app.state.settings.S3_BUCKET_NAME in urlparse(location).netloc + urlparse(location).path
    assert "X-Amz-Expires=3600" in location and "X-Amz-Signature=" in location and key in location
    assert r.headers["cache-control"] == "max-age=300"


def test_a_film_without_a_poster_and_an_unknown_film_are_404_not_found(client):
    sign_in(client)
    film = new_film(client)
    client.cookies.clear()
    no_poster, unknown = (client.get(f"/api/movies/{m}/poster", follow_redirects=False) for m in (film["id"], 987654321))
    for r in (no_poster, unknown):
        assert r.status_code == 404 and r.json()["error"]["code"] == "NOT_FOUND"
    a, b = no_poster.json(), unknown.json()
    assert without_request_id(a) == without_request_id(b) and set(a["error"]) == set(b["error"])
    assert a["error"]["request_id"] and b["error"]["request_id"] and a["error"]["request_id"] != b["error"]["request_id"]


def test_a_key_parameter_cannot_steer_the_object_key(client):
    film, key = _film_with_key(client)
    plain = client.get(f"/api/movies/{film['id']}/poster", follow_redirects=False)
    steered = client.get(f"/api/movies/{film['id']}/poster?key=../../etc/passwd", follow_redirects=False)
    assert plain.status_code == steered.status_code == 302
    path = urlsplit(steered.headers["location"]).path
    assert path == urlsplit(plain.headers["location"]).path
    # The object-key component: the path less its leading slash and, for a path-style URL, the bucket segment.
    assert path.lstrip("/").removeprefix(client.app.state.settings.S3_BUCKET_NAME + "/") == key
    assert "etc/passwd" not in steered.headers["location"] and ".." not in steered.headers["location"]


def test_presigning_issues_no_network_call(client, monkeypatch):
    film, key = _film_with_key(client)
    plain = client.get(f"/api/movies/{film['id']}/poster", follow_redirects=False)

    def blocked(self, address):
        raise OSError(f"outbound connection to {address} blocked by the test")

    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket.socket, "connect_ex", blocked)
    monkeypatch.setattr(socket, "create_connection", lambda *a, **k: blocked(None, a[0] if a else None))
    # The film's row is already read: the database connection is pooled and open, so only NEW sockets are blocked.
    r = client.get(f"/api/movies/{film['id']}/poster", follow_redirects=False)
    assert r.status_code == 302, r.text
    location = r.headers["location"]
    assert urlsplit(location).netloc == urlsplit(plain.headers["location"]).netloc
    assert client.app.state.settings.S3_BUCKET_NAME in urlsplit(location).netloc + urlsplit(location).path
    assert urlsplit(location).path == urlsplit(plain.headers["location"]).path
    assert "X-Amz-Signature=" in urlsplit(location).query and "X-Amz-Expires=3600" in urlsplit(location).query


@pytest.mark.parametrize("window", [("2026-01-01T00:00:00+05:30", "2026-01-08T00:00:00+05:30"),  # long over
                                    ("2099-01-01T00:00:00+05:30", "2099-01-08T00:00:00+05:30")])  # not yet open
def test_a_published_film_outside_its_window_still_redirects(client, window):
    film, key = _film_with_key(client)
    owner_sql(client.db, "UPDATE movie SET published_at = '2025-12-01T00:00:00Z', display_from = %s, display_until = %s "
                         "WHERE id = %s", (*window, film["id"]))
    r = client.get(f"/api/movies/{film['id']}/poster", follow_redirects=False)
    assert r.status_code == 302 and key in r.headers["location"]


@pytest.mark.parametrize("value", ["3600", "4000"])
def test_a_redirect_cache_not_below_the_presign_expiry_refuses_to_boot(tmp_path, value):
    env = {**os.environ, **VALID_ENV, "POSTER_REDIRECT_CACHE_SECONDS": value, "PYTHONPATH": str(BACKEND_DIR)}
    proc = subprocess.run([sys.executable, "-m", "app", "api"], cwd=tmp_path, env=env, capture_output=True, text=True, timeout=30)
    assert proc.returncode != 0, (proc.stdout, proc.stderr)
    assert "POSTER_REDIRECT_CACHE_SECONDS" in proc.stderr, (proc.stdout, proc.stderr)

"""S-BRW-18 - serve posters from our own bucket by redirect, and never hotlink (EP-BRW-03).
The real S3 adapter signs offline (botocore needs no network to presign), as in tests/adm/test_s_adm_25.py.
NOT covered here: the boot refusal of POSTER_REDIRECT_CACHE_SECONDS >= the presign expiry (config check 11, already
asserted by the config tests) and the card's rendered fallback (Poster.tsx, frontend).
"""
from __future__ import annotations

from urllib.parse import urlparse

from app.domain.posters import S3Posters
from tests.adm.kit import client, new_film, owner_sql, sign_in  # noqa: F401


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
    for movie_id in (film["id"], 987654321):
        r = client.get(f"/api/movies/{movie_id}/poster", follow_redirects=False)
        assert r.status_code == 404 and r.json()["error"]["code"] == "NOT_FOUND"

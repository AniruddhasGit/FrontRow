"""S-ADM-25 - upload a poster to private object storage (P-ADM-03, EP-ADM-05/06).

Locally there is no bucket (FR-ADR-061: no local S3 stand-in, no MinIO). So:
  - the request path runs against MemoryPosters (tests/adm/kit.py), an in-memory PutObject/GetObject/ListObjectsV2;
  - the REAL S3 adapter (app/domain/posters.py S3Posters) is exercised offline: its presigned URL is signed by
    botocore with no network call, and its error mapping runs against botocore's own Stubber.
NOT covered, because only the client's real bucket can answer them (Zone C, docs/30 Deployment): GetPublicAccessBlock,
GetBucketPolicy, an unauthenticated GET of the object URL returning 403, GetBucketLifecycleConfiguration, and
ListObjectsV2 / GetObject against S3 itself. GET /api/movies/{id}/poster (EP-BRW-03) is not mounted by any lane yet,
so its 404 for a draft is asserted but is the unmounted-route 404 today.
"""

from __future__ import annotations

import json
import os
import re
import struct
import tempfile

import pytest
from botocore.exceptions import EndpointConnectionError
from botocore.stub import Stubber

from app.api.errors import ApiError
from app.core.security import SESSION_COOKIE
from app.domain.posters import S3Posters, check_image
from tests.adm.kit import (MemoryPosters, client, count, movie_row, multipart, new_film, owner_sql, png,  # noqa: F401
                           routes, sign_in)

LIMIT = 2_097_152
RID = re.compile(r"^[0-9a-f]{8}$")


@pytest.fixture
def bucket(client):
    client.app.state.posters = MemoryPosters()
    sign_in(client)
    return client.app.state.posters


def _upload(client, movie_id, *parts, params=None, headers=None):
    body, ctype = multipart(*parts)
    return client.post(f"/api/admin/movies/{movie_id}/poster", content=body, params=params,
                       headers={"Content-Type": ctype, **(headers or {})})


def _file(data=None, ctype="image/png", filename="my poster.png"):
    return ("file", filename, ctype, png(200, 300) if data is None else data)


def _raw(client, path: str, headers: dict, body: bytes) -> tuple[int, dict, int]:
    """One request straight into the ASGI app, recording how many body bytes the app pulled from the stream."""
    consumed = []
    pending = [{"type": "http.request", "body": body, "more_body": False}]

    async def call():
        sent = []

        async def receive():
            if pending:
                message = pending.pop(0)
                consumed.append(len(message["body"]))
                return message
            return {"type": "http.disconnect"}

        async def send(message):
            sent.append(message)

        cookie = f"{SESSION_COOKIE}={client.cookies.get(SESSION_COOKIE)}"
        scope = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": "POST", "scheme": "http",
                 "path": path, "raw_path": path.encode(), "query_string": b"", "root_path": "", "client": ("127.0.0.1", 50000),
                 "server": ("testserver", 80),
                 "headers": [(b"cookie", cookie.encode())] + [(k.lower().encode(), v.encode()) for k, v in headers.items()]}
        await client.app(scope, receive, send)
        return sent

    sent = client.portal.call(call)
    return sent[0]["status"], json.loads(b"".join(m.get("body", b"") for m in sent[1:])), sum(consumed)


def test_content_length_is_checked_at_the_header_before_a_byte_is_read(client, bucket):
    film = new_film(client)
    body, ctype = multipart(("version", None, None, b"1"), _file())
    path = f"/api/admin/movies/{film['id']}/poster"
    status, error, consumed = _raw(client, path, {"content-type": ctype, "content-length": str(LIMIT + 1)}, body)
    assert (status, error["error"]["code"], error["error"]["message"], consumed) == (
        413, "PAYLOAD_TOO_LARGE", "That file is larger than 2 MB. Choose a smaller image.", 0)
    status, error, consumed = _raw(client, path, {"content-type": ctype}, body)  # no Content-Length at all
    assert (status, error["error"]["code"], consumed) == (422, "VALIDATION_FAILED", 0)
    assert error["error"]["message"] == "The upload did not declare its size and was not accepted. Try again."


def test_exactly_two_mebibytes_is_accepted(client, bucket):
    film = new_film(client)
    overhead = len(multipart(("version", None, None, b"1"), _file(b""))[0])
    body, ctype = multipart(("version", None, None, b"1"), _file(png(200, 300, size=LIMIT - overhead)))
    assert len(body) == LIMIT
    r = client.post(f"/api/admin/movies/{film['id']}/poster", content=body, headers={"Content-Type": ctype})
    assert r.status_code == 201, r.text


def test_the_declared_type_the_magic_bytes_and_the_decode(client, bucket):
    film = new_film(client)
    good = png(200, 300)
    cases = [(_file(good, "image/gif"), "Posters must be a JPEG, PNG or WebP image."),
             (_file(b"\xff\xd8\xff\xe0" + good[4:]), "That file is not the image type it says it is. Choose a JPEG, PNG or WebP image."),
             (_file(good[:8] + b"\x00garbage" * 50), "That file could not be read as an image. Choose a JPEG, PNG or WebP image."),
             (_file(good[:-20] + b"\x00" * 20), "That file could not be read as an image. Choose a JPEG, PNG or WebP image.")]
    for part, message in cases:
        r = _upload(client, film["id"], ("version", None, None, b"1"), part)
        assert (r.status_code, r.json()["error"]["code"], r.json()["error"]["message"]) == (415, "UNSUPPORTED_MEDIA_TYPE", message)
    assert bucket.objects == {}


def test_pixel_dimensions(client, bucket):
    film = new_film(client)
    version = 1
    for (w, h), status in (((200, 300), 201), ((199, 300), 422), ((4000, 6000), 201), ((4001, 6000), 422)):
        r = _upload(client, film["id"], ("version", None, None, str(version).encode()), _file(png(w, h)))
        assert r.status_code == status, (w, h, r.text)
        if status == 201:
            version += 1
        else:
            assert r.json()["error"]["message"] == "Poster images must be between 200 by 300 and 4000 by 6000 pixels."


def test_exactly_one_file_part_and_the_version_only_as_a_form_part(client, bucket):
    film = new_film(client)
    one = ("version", None, None, b"1")
    for parts in ((one,), (one, _file(), _file())):
        r = _upload(client, film["id"], *parts)
        assert (r.status_code, r.json()["error"]["message"]) == (422, "Choose exactly one image file."), len(parts)
    for kwargs in ({}, {"headers": {"version": "1"}}, {"params": {"version": "1"}}):
        r = _upload(client, film["id"], _file(), **kwargs)
        assert (r.status_code, r.json()["error"]["code"]) == (422, "VALIDATION_FAILED"), kwargs
    r = _upload(client, film["id"], one, _file(), ("colour", None, None, b"red"))
    assert (r.status_code, r.json()["error"]["code"]) == (400, "REQUEST_INVALID")
    assert bucket.objects == {} and movie_row(client.db, film["id"])[-2] == 1


def test_a_stale_version_is_409_and_writes_no_object(client, bucket):
    film = new_film(client)
    before = len(bucket.keys(f"posters/{film['id']}/"))
    r = _upload(client, film["id"], ("version", None, None, b"9"), _file())
    assert (r.status_code, r.json()["error"]["code"]) == (409, "VERSION_CONFLICT")
    assert len(bucket.keys(f"posters/{film['id']}/")) == before


def test_the_earlier_check_always_wins_when_two_fail_at_once(client, bucket):
    film = new_film(client)
    body, ctype = multipart(_file(ctype="image/gif"))  # no version AND a bad type
    status, _, _ = _raw(client, f"/api/admin/movies/{film['id']}/poster", {"content-type": ctype,
                                                                          "content-length": str(LIMIT + 5)}, body)
    assert status == 413  # Content-Length before everything
    assert _upload(client, film["id"], ("version", None, None, b"9"), _file(ctype="image/gif")).status_code == 409
    assert _upload(client, film["id"], ("version", None, None, b"1"), _file(png(10, 10), "image/gif")).status_code == 415
    r = _upload(client, film["id"], ("version", None, None, b"1"), _file(png(10, 10)[:-20] + b"\x00" * 20))
    assert r.status_code == 415  # undecodable is reported before the dimensions are


def test_a_success_stores_a_random_key_increments_once_and_never_deletes_the_previous_object(client, bucket):
    film = new_film(client)
    first_bytes = png(200, 300)
    r = _upload(client, film["id"], ("version", None, None, b"1"), _file(first_bytes))
    assert (r.status_code, r.json()["version"], r.json()["poster_present"]) == (201, 2, True)
    key = owner_sql(client.db, "SELECT poster_object_key FROM movie WHERE id = %s", (film["id"],))[0][0]
    assert re.fullmatch(rf"posters/{film['id']}/[0-9a-f]{{32}}", key)
    assert "my" not in key and key.count("poster") == 1 and key.startswith("posters/")
    r = _upload(client, film["id"], ("version", None, None, b"2"), _file(png(300, 450)))
    assert r.status_code == 201
    second = owner_sql(client.db, "SELECT poster_object_key FROM movie WHERE id = %s", (film["id"],))[0][0]
    assert bucket.objects[key] == first_bytes  # GetObject on the previous key: still there, original bytes
    assert owner_sql(client.db, "SELECT action, before, after FROM audit_log WHERE entity_id = %s AND action LIKE "
                                "'movie.poster%%' ORDER BY id", (film["id"],)) == [
        ("movie.poster_uploaded", None, {"poster_object_key": key}),
        ("movie.poster_replaced", {"poster_object_key": key}, {"poster_object_key": second})]


def test_nothing_reaches_the_local_disk(client, bucket):
    film = new_film(client)
    snapshot = lambda: (sorted(os.listdir(os.getcwd())), sorted(os.listdir(tempfile.gettempdir())))  # noqa: E731
    before = snapshot()
    assert _upload(client, film["id"], ("version", None, None, b"1"), _file()).status_code == 201
    assert snapshot() == before


def test_the_admin_read_is_a_302_to_a_one_hour_presigned_url_even_for_a_draft(client):
    sign_in(client)
    film = new_film(client)
    client.app.state.posters = S3Posters(client.app.state.settings)  # the real adapter; signing needs no network
    owner_sql(client.db, "UPDATE movie SET poster_object_key = %s WHERE id = %s", (f"posters/{film['id']}/{'b' * 32}", film["id"]))
    r = client.get(f"/api/admin/movies/{film['id']}/poster", follow_redirects=False)
    assert r.status_code == 302
    location = r.headers["location"]
    assert "X-Amz-Expires=3600" in location and f"posters/{film['id']}/{'b' * 32}" in location
    assert "frontrow-posters-test" in location and "X-Amz-Signature=" in location
    client.cookies.clear()
    assert client.get(f"/api/movies/{film['id']}/poster").status_code == 404
    sign_in(client)
    bare = new_film(client)
    assert client.get(f"/api/admin/movies/{bare['id']}/poster", follow_redirects=False).status_code == 404


@pytest.mark.parametrize("code,http,status", [("SlowDown", 503, 503), ("InternalError", 500, 503), ("Throttling", 400, 503),
                                              ("AccessDenied", 403, 500), ("NoSuchBucket", 404, 500)])
def test_s3_failures_split_into_retryable_503_and_refused_500(client, code, http, status):
    sign_in(client)
    film = new_film(client)
    real = S3Posters(client.app.state.settings)
    client.app.state.posters = real
    with Stubber(real.client) as stub:
        stub.add_client_error("put_object", service_error_code=code, http_status_code=http)
        r = _upload(client, film["id"], ("version", None, None, b"1"), _file())
    assert r.status_code == status, r.text
    error = r.json()["error"]
    if status == 503:
        assert (error["code"], error["message"]) == (
            "DEPENDENCY_UNAVAILABLE", "The system cannot reach its file storage right now. The poster was not saved. Try again in a moment.")
    else:
        rid = error["request_id"]
        assert RID.match(rid) and rid == r.headers["x-request-id"]
        assert (error["code"], error["message"]) == (
            "INTERNAL_ERROR", f"The server could not complete this request. If you need help, quote {rid}.")
    assert movie_row(client.db, film["id"])[-2] == 1  # version: the film was not touched


def test_an_unreachable_endpoint_is_503(client, monkeypatch):
    sign_in(client)
    film = new_film(client)
    real = S3Posters(client.app.state.settings)
    client.app.state.posters = real

    def down(**kwargs):
        raise EndpointConnectionError(endpoint_url="https://s3.ap-south-1.amazonaws.com")

    monkeypatch.setattr(real.client, "put_object", down)
    r = _upload(client, film["id"], ("version", None, None, b"1"), _file())
    assert (r.status_code, r.json()["error"]["code"]) == (503, "DEPENDENCY_UNAVAILABLE")


def test_nothing_in_the_product_reports_or_prunes_the_storage_allowance(client):
    paths = [(m, r.path) for r in routes(client.app) for m in r.methods]
    assert [p for _, p in paths if re.search(r"bucket|storage|usage|quota", p, re.IGNORECASE)] == []
    assert [p for m, p in paths if m == "DELETE" and "poster" in p] == []


def _jpeg(w: int, h: int, end: bytes = b"\xff\xd9") -> bytes:
    sof = b"\xff\xc0" + struct.pack(">HBHHB", 11, 8, h, w, 1) + b"\x01\x11\x00"
    sos = b"\xff\xda" + struct.pack(">HB", 8, 1) + b"\x01\x00\x00\x3f\x00"
    return b"\xff\xd8" + b"\xff\xe0" + struct.pack(">H", 16) + b"JFIF\x00" + b"\x00" * 9 + sof + sos + b"\x12\x34" + end


def _webp(kind: bytes, header: bytes) -> bytes:
    body = kind + struct.pack("<I", len(header)) + header
    return b"RIFF" + struct.pack("<I", 4 + len(body)) + b"WEBP" + body


@pytest.mark.parametrize("declared,data,status", [
    ("image/jpeg", _jpeg(200, 300), None), ("image/jpeg", _jpeg(199, 300), 422), ("image/jpeg", _jpeg(200, 300, end=b""), 415),
    ("image/webp", _webp(b"VP8L", b"\x2f" + struct.pack("<I", (200 - 1) | ((300 - 1) << 14)) + b"\x00" * 8), None),
    ("image/webp", _webp(b"VP8X", b"\x00" * 4 + (4000 - 1).to_bytes(3, "little") + (6000 - 1).to_bytes(3, "little")), None),
    ("image/webp", _webp(b"VP8 ", b"\x00" * 3 + b"\x9d\x01\x2a" + struct.pack("<HH", 200, 299) + b"\x00" * 4), 422),
    ("image/webp", _webp(b"VP8 ", b"\x00" * 16)[:-3], 415),
])
def test_the_jpeg_and_webp_header_decoders(declared, data, status):
    if status is None:
        check_image(declared, data)
        return
    with pytest.raises(ApiError) as exc:
        check_image(declared, data)
    assert exc.value.status == status


def test_no_storage_credentials_as_on_the_render_copy_is_503_on_upload_and_on_the_admin_read(client, monkeypatch):
    # [JUDGMENT CALL] The Render copy has no bucket and no AWS credentials: botocore raises NoCredentialsError before
    # any request is made. That is "file storage unreachable" (503 with P-ADM-03's sentence), never a bare 500.
    from botocore.exceptions import NoCredentialsError

    sign_in(client)
    film = new_film(client)
    real = S3Posters(client.app.state.settings)
    client.app.state.posters = real

    def none(*args, **kwargs):
        raise NoCredentialsError()

    monkeypatch.setattr(real.client, "put_object", none)
    monkeypatch.setattr(real.client, "generate_presigned_url", none)
    r = _upload(client, film["id"], ("version", None, None, b"1"), _file())
    assert (r.status_code, r.json()["error"]["code"]) == (503, "DEPENDENCY_UNAVAILABLE")
    assert movie_row(client.db, film["id"])[-2] == 1
    owner_sql(client.db, "UPDATE movie SET poster_object_key = %s WHERE id = %s", (f"posters/{film['id']}/{'c' * 32}", film["id"]))
    r = client.get(f"/api/admin/movies/{film['id']}/poster", follow_redirects=False)
    assert (r.status_code, r.json()["error"]["code"]) == (503, "DEPENDENCY_UNAVAILABLE")

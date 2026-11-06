"""Posters (P-ADM-03, FR-ADR-061): the image checks, the server-generated key, and the private S3 bucket.

THE CHECKS, in P-ADM-03's order after the size and the version: declared type -> magic bytes -> decode and pixel
dimensions. Each refusal carries P-ADM-03's own sentence.

DECODING WITHOUT A NEW DEPENDENCY. No image library is approved (SRC-002 §13.1; Pillow would be one), so the decode
is the standard library's: a PNG is walked chunk by chunk with every CRC checked and its IDAT stream is actually
inflated by zlib and measured against the size IHDR promises; a JPEG's marker segments are walked to its frame
header, scan and end marker; a WebP's RIFF container and its VP8/VP8L/VP8X header are read.
ponytail: a JPEG or WebP whose container and headers are valid but whose entropy-coded pixel data is corrupt passes
here (a PNG's does not). Upgrade path: Pillow's Image.verify() + .size, once the client approves the dependency.

STORAGE. One PutObject from the bounded in-memory buffer; nothing touches the container's disk (SRC-002 §7.3). The
key is `posters/{movie_id}/{32 hex}`: random, server-made, never the client's filename. Objects are never deleted
(FR-ADR-012), so an audit row's previous key still resolves. boto3 is imported on first use only (JC-R7-01).
The endpoint is the SDK's own: AWS_ENDPOINT_URL_S3 (a botocore setting, read from the environment) points the same
code at any S3-compatible store, which is how the Render copy could get a bucket without a code change.
[JUDGMENT CALL] The Render copy has no S3 and no credentials: upload and the admin poster read answer 503 "cannot reach
its file storage" (NoCredentialsError), and every other film action works. ponytail: no local-disk or database fallback
store - the container is read-only and posters are never kept on its disk (SRC-002 §7.3).
"""

from __future__ import annotations

import asyncio
import secrets
import struct
import zlib

from app.api.errors import ApiError
from app.core.config import Settings

ACCEPTED = ("image/jpeg", "image/png", "image/webp")
MIN_W, MIN_H, MAX_W, MAX_H = 200, 300, 4000, 6000  # P-ADM-03 "technical": the 2:3 poster ratio's bounds

TYPE = "Posters must be a JPEG, PNG or WebP image."
MISMATCH = "That file is not the image type it says it is. Choose a JPEG, PNG or WebP image."
UNREADABLE = "That file could not be read as an image. Choose a JPEG, PNG or WebP image."
DIMENSIONS = "Poster images must be between 200 by 300 and 4000 by 6000 pixels."
STORAGE_DOWN = "The system cannot reach its file storage right now. The poster was not saved. Try again in a moment."

_MAGIC = {"image/png": (b"\x89PNG\r\n\x1a\n",), "image/jpeg": (b"\xff\xd8\xff",)}


class _Bad(Exception):
    """The bytes do not decode as the declared type."""


def _magic_ok(declared: str, data: bytes) -> bool:
    if declared == "image/webp":
        return data[:4] == b"RIFF" and data[8:12] == b"WEBP"
    return data.startswith(_MAGIC[declared])


# PNG colour type -> samples per pixel (PNG spec table 11.1).
_PNG_SAMPLES = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}


def _png(data: bytes) -> tuple[int, int]:
    pos, size, idat, ihdr, ended = 8, len(data), zlib.decompressobj(), None, False
    produced = 0
    while pos + 12 <= size and not ended:
        length, kind = struct.unpack(">I4s", data[pos:pos + 8])
        body = data[pos + 8:pos + 8 + length]
        if len(body) != length or pos + 12 + length > size:
            raise _Bad
        (crc,) = struct.unpack(">I", data[pos + 8 + length:pos + 12 + length])
        if zlib.crc32(kind + body) != crc:
            raise _Bad
        if ihdr is None and kind != b"IHDR":
            raise _Bad
        if kind == b"IHDR":
            w, h, depth, colour, _, _, interlace = struct.unpack(">IIBBBBB", body)
            if colour not in _PNG_SAMPLES or interlace not in (0, 1) or not w or not h:
                raise _Bad
            ihdr = (w, h, depth, colour, interlace)
        elif kind == b"IDAT":
            # Inflate in bounded steps and count, never holding the decoded image: a 4000x6000 RGBA poster is 96 MB
            # decoded, half the API's whole memory budget (P-ADM-03's worked figures).
            chunk = body
            while chunk:
                produced += len(idat.decompress(chunk, 1 << 16))
                chunk = idat.unconsumed_tail
        elif kind == b"IEND":
            ended = True
        pos += 12 + length
    if ihdr is None or not ended or not idat.eof:
        raise _Bad
    w, h, depth, colour, interlace = ihdr
    row = (w * _PNG_SAMPLES[colour] * depth + 7) // 8 + 1  # one filter byte per scanline
    # ponytail: an interlaced PNG's seven passes are not re-counted; its stream is still fully inflated above.
    if interlace == 0 and produced != row * h:
        raise _Bad
    return w, h


def _jpeg(data: bytes) -> tuple[int, int]:
    pos, size, dims = 2, len(data), None
    while pos + 4 <= size:
        if data[pos] != 0xFF:
            raise _Bad
        marker = data[pos + 1]
        if marker == 0xFF:  # fill byte
            pos += 1
            continue
        (length,) = struct.unpack(">H", data[pos + 2:pos + 4])
        if length < 2 or pos + 2 + length > size:
            raise _Bad
        if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):  # a start-of-frame segment
            h, w = struct.unpack(">HH", data[pos + 5:pos + 9])
            dims = (w, h)
        if marker == 0xDA:  # start of scan: entropy-coded data follows, then the end-of-image marker
            if dims is None or not all(dims) or not data.rstrip(b"\x00").endswith(b"\xff\xd9"):
                raise _Bad
            return dims
        pos += 2 + length
    raise _Bad


def _webp(data: bytes) -> tuple[int, int]:
    (riff,) = struct.unpack("<I", data[4:8])
    if riff + 8 != len(data) or len(data) < 30:
        raise _Bad
    kind, body = data[12:16], data[20:]
    if kind == b"VP8 " and body[3:6] == b"\x9d\x01\x2a":
        w, h = struct.unpack("<HH", body[6:10])
        return w & 0x3FFF, h & 0x3FFF
    if kind == b"VP8L" and body[0] == 0x2F:
        (bits,) = struct.unpack("<I", body[1:5])
        return (bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1
    if kind == b"VP8X":
        return int.from_bytes(body[4:7], "little") + 1, int.from_bytes(body[7:10], "little") + 1
    raise _Bad


_DECODE = {"image/png": _png, "image/jpeg": _jpeg, "image/webp": _webp}


def check_image(declared: str, data: bytes) -> None:
    """P-ADM-03 steps 5 to 7. 415 for the type, the magic and the decode; 422 for the dimensions."""
    if declared not in ACCEPTED:
        raise ApiError(415, "UNSUPPORTED_MEDIA_TYPE", TYPE, {"field": "file"})
    if not _magic_ok(declared, data):
        raise ApiError(415, "UNSUPPORTED_MEDIA_TYPE", MISMATCH, {"field": "file"})
    try:
        w, h = _DECODE[declared](data)
    except (_Bad, struct.error, zlib.error, IndexError, ValueError):
        raise ApiError(415, "UNSUPPORTED_MEDIA_TYPE", UNREADABLE, {"field": "file"}) from None
    if not (MIN_W <= w <= MAX_W and MIN_H <= h <= MAX_H):
        raise ApiError(422, "VALIDATION_FAILED", DIMENSIONS, {"field": "file"})


def new_key(movie_id: int) -> str:
    return f"posters/{movie_id}/{secrets.token_hex(16)}"


# A refusal a retry can clear: S3's own throttle codes. Any 5xx is also retryable (P-ADM-03 exception 12).
_THROTTLES = frozenset({"SlowDown", "Throttling", "ThrottlingException", "RequestLimitExceeded", "TooManyRequestsException",
                        "RequestThrottled", "RequestTimeout"})


class S3Posters:
    """The private bucket. One client per process, made on first use."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._s3 = None

    @property
    def client(self):
        if self._s3 is None:
            import boto3  # lazy, JC-R7-01
            from botocore.config import Config

            # max_attempts=1: the admin is the retry, and a bounded call stays bounded (as app/workers/queue.py).
            self._s3 = boto3.client("s3", region_name=self.settings.AWS_REGION,
                                    config=Config(retries={"max_attempts": 1, "mode": "standard"}, signature_version="s3v4"))
        return self._s3

    async def put(self, key: str, data: bytes, content_type: str) -> None:
        from botocore.exceptions import ClientError, ConnectionError as SdkConnectionError, NoCredentialsError, ReadTimeoutError

        try:
            await asyncio.to_thread(self.client.put_object, Bucket=self.settings.S3_BUCKET_NAME, Key=key, Body=data,
                                    ContentType=content_type)
        except ClientError as exc:
            status = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode") or 0
            if status >= 500 or exc.response.get("Error", {}).get("Code") in _THROTTLES:
                raise ApiError(503, "DEPENDENCY_UNAVAILABLE", STORAGE_DOWN) from exc
            raise  # 12b: a refusal no retry clears (credential, bucket, policy) - the 500 quoting the request id
        except (SdkConnectionError, ReadTimeoutError, NoCredentialsError) as exc:
            # NoCredentialsError: [JUDGMENT CALL] the Render copy has no bucket and no credentials, so storage is
            # unreachable there - 503 with the published sentence, never a bare 500 (the films themselves still work).
            raise ApiError(503, "DEPENDENCY_UNAVAILABLE", STORAGE_DOWN) from exc

    def presign(self, key: str) -> str:
        """A GET URL valid for PRESIGNED_URL_TTL_SECONDS, signed locally - no network call."""
        from botocore.exceptions import NoCredentialsError

        try:
            return self.client.generate_presigned_url("get_object", Params={"Bucket": self.settings.S3_BUCKET_NAME,
                                                                            "Key": key},
                                                      ExpiresIn=self.settings.PRESIGNED_URL_TTL_SECONDS)
        except NoCredentialsError as exc:  # the Render copy, as in put() above
            raise ApiError(503, "DEPENDENCY_UNAVAILABLE", STORAGE_DOWN) from exc


def store(state) -> S3Posters:
    """The process's poster store, on app.state (a test puts an in-memory double there)."""
    if getattr(state, "posters", None) is None:
        state.posters = S3Posters(state.settings)
    return state.posters

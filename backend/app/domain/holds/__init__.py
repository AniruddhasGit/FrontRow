"""Seat holds (P-HLD-01..14, EP-HLD-01..04, 03_concurrency_model.md). Redis is the only record of a live hold.

    lock:seat:{showtime_id}:{seat_id}             the hold token, PX = the hold's remaining life (app/core/locks.py)
    hold:{hold_token}                             hash: user_id, showtime_id, expires_at, and one field per seat,
                                                  seat:{seat_id} -> JSON {label, category, category_id,
                                                  price_paise, base_price_paise, uplift_bp, instance}
    holds:user:{user_id}:showtime:{showtime_id}   set of this customer's hold token(s) - the cap and token reuse
    instance:{instance_id}:holds                  set of lock keys THIS api process granted - the SIGTERM release

Every structure carries the hold's TTL, so an instance dying anywhere in here costs time and never correctness.
[JUDGMENT CALL] `hold:{token}` as the record's key name and one hash field per seat (03_concurrency_model.md names
the key; no source names the layout): an extend appends seats with one HSET and never rewrites existing prices.

EXPIRY IS DECIDED BY REDIS. Nothing here compares a clock against expires_at to decide whether a hold is alive
(P-HLD-03). The injected clock is read in exactly two places: to compute expires_at once at acquisition, and to
compute the PX of a seat that joins an existing hold (the milliseconds remaining to that same instant, P-HLD-01).

REDIS DOWN IS AN ERROR (SRC-002 §7.9). No path here reads PostgreSQL in place of a lock. Callers turn RedisError
into 503 DEPENDENCY_UNAVAILABLE and the failure path issues no further Redis command (P-HLD-10).

THE CONFIRM PATH (EP-PAY-01, lane PAY) uses: load(), liveness(), and release_all() after its commit.
"""

from __future__ import annotations

import asyncio
import json
import logging
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Literal
from zoneinfo import ZoneInfo

from redis.exceptions import RedisError
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncConnection

from app.api.errors import ApiError
from app.core import cache, locks
from app.core.config import Settings
from app.domain.pricing import UPLIFT_COLUMN, seat_price_paise
from app.models import booking_seat, cinema, screen, seat, seat_category, showtime, showtime_seat

log = logging.getLogger("app.holds")

# ---- the lane's message set (P-HLD-14). The server renders every sentence; the client composes none. ----------
SIGN_IN = "Sign in to hold seats. Your selection has been kept."
UNAVAILABLE = "Seat holds are unavailable right now. You can still browse showtimes. Try again in a few minutes."
FAILED = "Something went wrong and your seats were not held. You have not been charged. If you need help, quote {request_id}."
ENDED = ("The hold on your seats has ended and they have been released. You have not been charged. "
         "Choose them again if they are still free.")
BAD_TOKEN = "This request could not be processed. Return to the seat map and choose your seats again."
NOT_IN_HOLD = "That seat is not part of your hold."
NO_SEATS = "Choose at least one seat."
NO_SHOWTIME = "That showtime could not be found."
RATE_LIMITED = "Too many attempts. Try again in {span}."
# The closing clause (P-HLD-14 "one substitution"): a first hold left nothing held; an extend left the hold as it was.
FIRST, EXTEND = "No seats were held.", "Your hold is unchanged."

TOKEN_LENGTH = 43  # secrets.token_urlsafe(32)
_TOKEN_CHARS = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_")
_NUMBER_WORDS = {2: "two", 3: "three", 4: "four", 5: "five", 6: "six", 7: "seven", 8: "eight", 9: "nine", 10: "ten"}


def well_formed(token: str) -> bool:
    """Exactly 43 characters from the URL-safe base64 alphabet (EP-HLD-02..04). Checked before Redis is touched."""
    return len(token) == TOKEN_LENGTH and set(token) <= _TOKEN_CHARS


def joined(labels: list[str]) -> str:
    """`C12`, `C12 and C13`, `C12, C13 and C14` - no serial comma (P-HLD-14)."""
    return labels[0] if len(labels) == 1 else ", ".join(labels[:-1]) + " and " + labels[-1]


def seat_level(kind: str, labels: list[str], clause: str) -> str:
    """The six seat-level VALIDATION_FAILED sentences, singular at one offending seat and plural at two or more."""
    one, many = {
        "duplicate": ("Seat {} was listed twice. Each seat can only be chosen once.",
                      "Seats {} were listed more than once. Each seat can only be chosen once."),
        "not_in_hall": ("Seat {} is not part of this hall.", "Seats {} are not part of this hall."),
        "out_of_service": ("Seat {} is out of service.", "Seats {} are out of service."),
    }[kind]
    return (one if len(labels) == 1 else many).format(joined(labels)) + " " + clause


def taken(labels: list[str], extend: bool) -> str:
    """SEAT_UNAVAILABLE at the hold: rows 2, 3 (first hold) and 2b, 3b (extend)."""
    who = f"{joined(labels)} {'was' if len(labels) == 1 else 'were'} taken by another customer."
    if len(labels) == 1:
        advice = "Choose a different seat and try again." if extend else "Choose a different seat and press Hold these seats again."
    else:
        # [JUDGMENT CALL] P-HLD-14 publishes the plural only at two seats ("change these two"). The count is
        # interpolated as a word, exactly as the seat labels are, so three lost seats are not called two.
        these = f"change these {_NUMBER_WORDS.get(len(labels), str(len(labels)))}"
        advice = (f"Your other choices are still selected — {these} and try again." if extend
                  else f"Your other choices are still selected — {these} and press Hold these seats again.")
    return f"{who} {EXTEND if extend else FIRST} {advice}"


def cap_alone(max_seats: int, chose: int) -> str:
    return f"You can hold up to {max_seats} seats for one showtime. You chose {chose}."


def cap_with_existing(max_seats: int, holding: int, chose: int) -> str:
    return f"You can hold up to {max_seats} seats for one showtime. You are holding {holding} and chose {chose} more."


def clock_label(instant: datetime, zone: str) -> str:
    """`7:45 pm` in the cinema's zone, never the container's (P-HLD-06)."""
    local = instant.astimezone(ZoneInfo(zone))
    return f"{local.hour % 12 or 12}:{local.minute:02d} {'am' if local.hour < 12 else 'pm'}"


def sales_closed(close: datetime, zone: str) -> str:
    return f"Sales for this showtime closed at {clock_label(close, zone)}. Choose another showtime."


# ---- keys ------------------------------------------------------------------------------------------------------


def record_key(token: str) -> str:
    return f"hold:{token}"


def index_key(user_id: int, showtime_id: int) -> str:
    return f"holds:user:{user_id}:showtime:{showtime_id}"


def mutex_key(user_id: int, showtime_id: int) -> str:
    return f"{index_key(user_id, showtime_id)}:mutex"


# The cap is read-check-write across several commands, so two simultaneous requests from one customer would each
# see the other's hold missing and each take 10 seats. One short lock per customer and showtime serialises them.
# ponytail: a waiter polls every 20 ms; a blocking primitive is only worth it if one customer sends many at once.
MUTEX_TTL_MS = 5 * 1000  # five seconds; the bare four-digit figure is reserved to pricing.py (S-PAY-02 sweep)
MUTEX_POLL_S = 0.02


def registry_key(instance_id: str) -> str:
    return f"instance:{instance_id}:holds"


def utc_ms(instant: datetime) -> str:
    """ISO-8601 in UTC with milliseconds: 2026-08-14T14:05:37.412Z (P-HLD-09)."""
    return instant.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _s(value) -> str:
    return value.decode() if isinstance(value, bytes) else value


# ---- the hold record -------------------------------------------------------------------------------------------


@dataclass
class Hold:
    token: str
    user_id: int
    showtime_id: int
    expires_at: str
    seats: dict[int, dict] = field(default_factory=dict)

    def body(self) -> dict:
        """The wire shape of EP-HLD-01/02/03: EVERY seat under the token, ascending, each with its stored price."""
        seats = [{"seat_id": sid, "label": s["label"], "category": s["category"], "price_paise": s["price_paise"]}
                 for sid, s in sorted(self.seats.items())]
        return {"hold_token": self.token, "showtime_id": self.showtime_id, "expires_at": self.expires_at,
                "seats": seats, "total_paise": sum(s["price_paise"] for s in seats)}


async def load(redis, token: str) -> Hold | None:
    raw = await redis.hgetall(record_key(token))
    if not raw:
        return None
    fields = {_s(k): _s(v) for k, v in raw.items()}
    seats = {int(k.split(":", 1)[1]): json.loads(v) for k, v in fields.items() if k.startswith("seat:")}
    return Hold(token, int(fields["user_id"]), int(fields["showtime_id"]), fields["expires_at"], seats)


async def liveness(redis, showtime_id: int, seat_ids: list[int], token: str) -> Literal["live", "expired", "not_owned"]:
    """P-HLD-03: GET each seat's key. Absent = the hold is over; another token = someone else's seat now.
    Takes no clock and compares no instant: Redis never returns a key past its TTL, so presence is the answer."""
    for seat_id in seat_ids:
        value = await redis.get(locks.seat_key(showtime_id, seat_id))
        if value is None:
            return "expired"
        if _s(value) != token:
            return "not_owned"
    return "live"


async def _live_hold_for(redis, user_id: int, showtime_id: int) -> Hold | None:
    """P-HLD-01 step 4: this customer's live hold on this showtime, read from the index - at most a few known
    keys, never a SCAN."""
    for token in sorted(_s(t) for t in await redis.smembers(index_key(user_id, showtime_id))):
        hold = await load(redis, token)
        if hold is not None and hold.seats:
            return hold
    return None


async def _expire_set(redis, key: str, ttl_ms: int) -> None:
    """A set shared by holds with different deadlines keeps the LATEST one: NX on a fresh set, GT afterwards."""
    await redis.pexpire(key, ttl_ms, nx=True)
    await redis.pexpire(key, ttl_ms, gt=True)


# ---- PostgreSQL reads (no write anywhere in this module) --------------------------------------------------------


async def _showtime(conn: AsyncConnection, showtime_id: int):
    return (await conn.execute(
        select(showtime.c.id, showtime.c.starts_at, cinema.c.timezone)
        .select_from(showtime.join(screen, showtime.c.screen_id == screen.c.id).join(cinema, screen.c.cinema_id == cinema.c.id))
        .where(showtime.c.id == showtime_id))).first()


async def _seats(conn: AsyncConnection, showtime_id: int, seat_ids: set[int]) -> dict[int, object]:
    """Each named seat that exists anywhere, with its label, category, service flag and membership of THIS
    showtime's seat set (P-ADM-14: the materialised set, never the screen's current seats)."""
    rows = (await conn.execute(
        select(seat.c.id, seat.c.row_label, seat.c.seat_number, seat.c.is_active, seat_category.c.id.label("category_id"),
               seat_category.c.name.label("category"), showtime_seat.c.seat_id.label("member"))
        .select_from(seat.join(seat_category, seat.c.seat_category_id == seat_category.c.id)
                     .outerjoin(showtime_seat, and_(showtime_seat.c.seat_id == seat.c.id, showtime_seat.c.showtime_id == showtime_id)))
        .where(seat.c.id.in_(seat_ids)))).all()
    return {r.id: r for r in rows}


async def _price_and_sold(conn: AsyncConnection, showtime_id: int, seat_ids: list[int]) -> tuple[int, dict[int, int], set[int]]:
    """Read AFTER the locks are won: the base price and uplifts current at the moment of grant (P-HLD-11), and
    which of the won seats already carry a committed booking_seat row (P-HLD-01 step 7)."""
    base = (await conn.execute(select(showtime.c.base_price_paise).where(showtime.c.id == showtime_id))).scalar_one()
    rows = (await conn.execute(
        select(seat.c.id, seat_category.c[UPLIFT_COLUMN].label("uplift"), booking_seat.c.id.label("booked"))
        .select_from(seat.join(seat_category, seat.c.seat_category_id == seat_category.c.id)
                     .outerjoin(booking_seat, and_(booking_seat.c.seat_id == seat.c.id, booking_seat.c.showtime_id == showtime_id)))
        .where(seat.c.id.in_(seat_ids)))).all()
    await conn.rollback()  # end the read's implicit transaction; nothing was written
    return base, {r.id: r.uplift for r in rows}, {r.id for r in rows if r.booked is not None}


# ---- EP-HLD-01 -------------------------------------------------------------------------------------------------


def _label(row) -> str:
    return f"{row.row_label}{row.seat_number}"


def _offending(seat_ids: list[int], bad: set[int], info: dict) -> list[str]:
    """Offending seats named once each, in submission order (P-HLD-14)."""
    return [_label(info[i]) for i in dict.fromkeys(seat_ids) if i in bad]


async def acquire(redis, conn: AsyncConnection, *, settings: Settings, now: datetime, user_id: int, showtime_id: int,
                  seat_ids: list[int], instance_id: str) -> dict:
    existing = await _live_hold_for(redis, user_id, showtime_id)
    clause = EXTEND if existing else FIRST
    # 1. Validate, before any lock is touched.
    if not seat_ids:
        raise ApiError(422, "VALIDATION_FAILED", NO_SEATS, {"field": "seat_ids"})
    head = await _showtime(conn, showtime_id)
    if head is None:
        raise ApiError(404, "NOT_FOUND", NO_SHOWTIME)
    info = await _seats(conn, showtime_id, set(seat_ids))
    await conn.rollback()
    if any(i not in info for i in seat_ids):
        # An id naming no seat anywhere has no label to put in a sentence; the registry's own words, and no
        # invented one (P-HLD-14 publishes no sentence for it).
        raise ApiError(422, "VALIDATION_FAILED", None, {"field": "seat_ids"})
    seen: set[int] = set()
    duplicates = {i for i in seat_ids if i in seen or seen.add(i)}
    if duplicates:
        raise ApiError(422, "VALIDATION_FAILED", seat_level("duplicate", _offending(seat_ids, duplicates, info), clause))
    outside = {i for i in seat_ids if info[i].member is None}
    if outside:
        raise ApiError(422, "VALIDATION_FAILED", seat_level("not_in_hall", _offending(seat_ids, outside, info), clause))
    retired = {i for i in seat_ids if not info[i].is_active}
    if retired:
        raise ApiError(422, "VALIDATION_FAILED", seat_level("out_of_service", _offending(seat_ids, retired, info), clause))
    # Validation above sent no SET (S-SEA-06). From here to the index write, one request per customer and showtime.
    mutex, mine = mutex_key(user_id, showtime_id), secrets.token_urlsafe(16)
    for _ in range(int(MUTEX_TTL_MS / 1000 / MUTEX_POLL_S) + 10):  # past the TTL, a dead holder's key has expired
        if await locks.acquire(redis, mutex, mine, MUTEX_TTL_MS):
            break
        await asyncio.sleep(MUTEX_POLL_S)
    else:
        raise ApiError(503, "DEPENDENCY_UNAVAILABLE", UNAVAILABLE)
    try:
        # Re-read under the lock: the first read only chose the clause for the validation sentences.
        existing = await _live_hold_for(redis, user_id, showtime_id)
        clause = EXTEND if existing else FIRST
        result = await _acquire_locked(redis, conn, settings=settings, now=now, user_id=user_id, showtime_id=showtime_id,
                                       seat_ids=seat_ids, instance_id=instance_id, head=head, info=info,
                                       existing=existing, clause=clause)
    except ApiError:
        await locks.release(redis, mutex, mine)
        raise
    # On any other failure Redis may be down, and the failure path sends nothing more (P-HLD-10): the mutex expires.
    await locks.release(redis, mutex, mine)
    return result


async def _acquire_locked(redis, conn: AsyncConnection, *, settings: Settings, now: datetime, user_id: int,
                          showtime_id: int, seat_ids: list[int], instance_id: str, head, info: dict, existing,
                          clause: str) -> dict:
    # 2. The cap, counted against live holds only (P-HLD-04). A seat already in the hold is not counted twice.
    held = set(existing.seats) if existing else set()
    adding = [i for i in seat_ids if i not in held]
    cap = settings.MAX_SEATS_PER_BOOKING
    if existing and len(held) + len(adding) > cap:
        raise ApiError(422, "SEAT_LIMIT_EXCEEDED", cap_with_existing(cap, len(held), len(adding)))
    if not existing and len(adding) > cap:
        raise ApiError(422, "SEAT_LIMIT_EXCEEDED", cap_alone(cap, len(adding)))
    # 3. The sales cut-off, derived now and never stored: refused once now >= starts_at + SALES_CUTOFF_MINUTES.
    close = head.starts_at + timedelta(minutes=settings.SALES_CUTOFF_MINUTES)
    if now >= close:
        raise ApiError(409, "SALES_CLOSED", sales_closed(close, head.timezone))
    # 4. Resolve the token: the live hold's token and expires_at, unchanged; else mint both once.
    if existing:
        token, expires_at = existing.token, existing.expires_at
        remaining = datetime.fromisoformat(expires_at.replace("Z", "+00:00")) - now
        # A seat joining the hold expires at the hold's instant, never a fresh full TTL (FR-ADR-027). Floored at
        # 1 ms only because PX must be positive; whether the hold is alive is still Redis's answer, not this one.
        ttl_ms = max(1, remaining // timedelta(milliseconds=1))
    else:
        token = secrets.token_urlsafe(32)
        ttl_ms = settings.SEAT_HOLD_TTL_SECONDS * 1000
        expires_at = utc_ms(now + timedelta(milliseconds=ttl_ms))
    # 5-6. Ascending seat-id order, one SET NX PX each. After the first loss nothing more is written; the rest are
    # only read, so every seat that went can be named.
    won: list[int] = []
    lost: list[int] = []
    try:
        for seat_id in sorted(seat_ids):
            key = locks.seat_key(showtime_id, seat_id)
            if not lost and await locks.acquire(redis, key, token, ttl_ms):
                won.append(seat_id)
                continue
            value = await redis.get(key)
            if value is not None and _s(value) == token and seat_id in held:
                continue  # already this customer's: a no-op, not a loss, not in the rollback set, TTL untouched
            if value is not None or not lost:
                lost.append(seat_id)
        if not lost and won:
            # 7. A booking leaves no key behind, so a lock can be won on a sold seat: the database says.
            base, uplifts, sold = await _price_and_sold(conn, showtime_id, won)
            lost = [i for i in won if i in sold]
        if lost:
            await _rollback(redis, showtime_id, won, token)
            labels = [_label(info[i]) for i in dict.fromkeys(seat_ids) if i in set(lost)]
            raise ApiError(409, "SEAT_UNAVAILABLE", taken(labels, bool(existing)), {"unavailable_seats": labels})
    except (ApiError, RedisError, OSError):
        # Redis failing is P-HLD-10's case: the failure path sends Redis nothing more, and what this request won
        # expires within ttl_ms on its own.
        raise
    except Exception:
        # PostgreSQL failed part-way and Redis is still answering: give back what this request won, best-effort.
        await _rollback(redis, showtime_id, won, token, quiet=True)
        raise
    # 8. Price ONLY the seats this request added, at the base and uplift current now, and append them.
    added = [i for i in won if i not in held]
    hold = existing or Hold(token, user_id, showtime_id, expires_at)
    fields: dict[str, str] = {} if existing else {"user_id": str(user_id), "showtime_id": str(showtime_id), "expires_at": expires_at}
    for seat_id in added:
        row = info[seat_id]
        entry = {"label": _label(row), "category": row.category, "category_id": row.category_id,
                 "price_paise": seat_price_paise(base, uplifts[seat_id]), "base_price_paise": base,
                 "uplift_bp": uplifts[seat_id], "instance": instance_id}
        hold.seats[seat_id] = entry
        fields[f"seat:{seat_id}"] = json.dumps(entry, separators=(",", ":"))
    if fields:
        await redis.hset(record_key(token), mapping=fields)
        await redis.pexpire(record_key(token), ttl_ms)
    # 9. Index the hold against the customer (a no-op on an extend), with the same TTL.
    await redis.sadd(index_key(user_id, showtime_id), token)
    await redis.pexpire(index_key(user_id, showtime_id), ttl_ms)
    # 10. This instance's registry, for the SIGTERM release (P-HLD-12).
    if won:
        registry = registry_key(instance_id)
        await redis.sadd(registry, *[locks.seat_key(showtime_id, i) for i in won])
        await _expire_set(redis, registry, ttl_ms)
    # 11. Invalidate the seat map AFTER every Redis write above, so no reader rebuilds it from a half-written state.
    await cache.invalidate_seatmap(redis, showtime_id)
    # 12. The whole hold.
    return hold.body()


async def _rollback(redis, showtime_id: int, won: list[int], token: str, quiet: bool = False) -> None:
    """Compare-and-delete every key THIS request won, and only those (P-HLD-01 rollback path)."""
    for seat_id in won:
        try:
            await locks.release(redis, locks.seat_key(showtime_id, seat_id), token)
        except Exception:  # noqa: BLE001 - best-effort: the key expires on its own
            if not quiet:
                raise
            log.warning("rollback release failed; the key expires within its TTL", extra={"showtime_id": showtime_id})


# ---- EP-HLD-02 / 03 / 04 ---------------------------------------------------------------------------------------


async def owned(redis, token: str, user_id: int) -> Hold:
    """The hold, or 409 HOLD_EXPIRED when its record is gone, or 403 when it is someone else's. The token alone
    never grants access (EP-HLD-02 authorisation_rule)."""
    hold = await load(redis, token)
    if hold is None:
        raise ApiError(409, "HOLD_EXPIRED", ENDED)
    if hold.user_id != user_id:
        raise ApiError(403, "HOLD_NOT_OWNED", ENDED)
    return hold


async def read(redis, token: str, user_id: int) -> dict:
    hold = await owned(redis, token, user_id)
    state = await liveness(redis, hold.showtime_id, sorted(hold.seats), token)
    if state == "expired":
        raise ApiError(409, "HOLD_EXPIRED", ENDED)
    if state == "not_owned":
        raise ApiError(403, "HOLD_NOT_OWNED", ENDED)
    return hold.body()


async def release_seat(redis, token: str, user_id: int, seat_id: int) -> dict:
    """P-HLD-08's per-seat procedure. The rest of the hold keeps its expires_at."""
    hold = await owned(redis, token, user_id)
    entry = hold.seats.get(seat_id)
    if entry is None:
        raise ApiError(422, "VALIDATION_FAILED", NOT_IN_HOLD, {"field": "seat_id"})
    key = locks.seat_key(hold.showtime_id, seat_id)
    await locks.release(redis, key, token)  # 0 = the key had already expired: still a success (exception 7)
    await redis.hdel(record_key(token), f"seat:{seat_id}")
    await redis.srem(registry_key(entry["instance"]), key)
    await cache.invalidate_seatmap(redis, hold.showtime_id)  # after the release, never before
    del hold.seats[seat_id]
    if not hold.seats:
        await redis.execute_command("DEL", record_key(token))
        await redis.srem(index_key(user_id, hold.showtime_id), token)
    return hold.body()


async def release_all(redis, hold: Hold) -> None:
    """The whole-hold release (P-HLD-08 EP-HLD-04 steps 2-6), also run after a booking commits (P-PAY-10 step 13).
    A compare-and-delete returning 0 is not an error and does not stop the loop."""
    keys = []
    for seat_id in sorted(hold.seats):
        key = locks.seat_key(hold.showtime_id, seat_id)
        await locks.release(redis, key, hold.token)
        keys.append((hold.seats[seat_id]["instance"], key))
    for instance_id in {i for i, _ in keys}:
        await redis.srem(registry_key(instance_id), *[k for i, k in keys if i == instance_id])
    await redis.execute_command("DEL", record_key(hold.token))
    await redis.srem(index_key(hold.user_id, hold.showtime_id), hold.token)
    await cache.invalidate_seatmap(redis, hold.showtime_id)  # after the releases, never before


async def release(redis, token: str, user_id: int) -> None:
    await release_all(redis, await owned(redis, token, user_id))


# ---- SIGTERM (P-HLD-12, FR-ADR-033) ----------------------------------------------------------------------------


async def release_instance(redis, instance_id: str) -> int:
    """Release every key this instance granted that still carries the token it granted. Best-effort per key and
    per hold: a failure is logged and the loop goes on, because expiry - not this - is the guarantee.
    Returns the number of keys released."""
    registry = registry_key(instance_id)
    touched: dict[str, int] = {}
    released = 0
    for key in sorted(_s(k) for k in await redis.smembers(registry)):
        try:
            showtime_id, seat_id = (int(p) for p in key.split(":")[2:4])
            token = await redis.get(key)
            if token is None:
                continue
            token = _s(token)
            entry = await redis.hget(record_key(token), f"seat:{seat_id}")
            # Ours only if the hold that owns the key NOW says this instance granted this seat: an expired seat
            # re-acquired by another hold is left alone (P-HLD-12 exception 4).
            if entry is None or json.loads(_s(entry)).get("instance") != instance_id:
                continue
            if await locks.release(redis, key, token):
                released += 1
                touched[token] = showtime_id
        except Exception:  # noqa: BLE001
            log.error("seat lock release failed at shutdown; it expires within its TTL", exc_info=True, extra={"key": key})
    for token, showtime_id in touched.items():
        try:
            hold = await load(redis, token)
            await redis.execute_command("DEL", record_key(token))
            if hold is not None:
                await redis.srem(index_key(hold.user_id, showtime_id), token)
        except Exception:  # noqa: BLE001
            log.error("hold record cleanup failed at shutdown; it expires within its TTL", exc_info=True)
    for showtime_id in set(touched.values()):
        await cache.invalidate_seatmap(redis, showtime_id)
    try:
        await redis.execute_command("DEL", registry)
    except Exception:  # noqa: BLE001
        log.error("registry delete failed at shutdown; it expires within its TTL", exc_info=True)
    log.info("released this instance's seat holds", extra={"released": released, "holds": len(touched)})
    return released

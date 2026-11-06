"""Token buckets in Redis for the credential endpoints (P-ACC-14, FR-ADR-058, SRC-002 §8.4).

One Lua script reads, refills and spends every bucket a request needs in a single atomic step, so two
simultaneous requests can never both take the last token. All buckets must hold a token or none is
spent and the request is refused by the first empty one, with Retry-After = the seconds until that
bucket's next token (so an emptied 10-per-900s bucket says 90, and 30 s later says 60).

The application's injected clock decides time: its instant is passed to the script as an argument and
the script never asks Redis what time it is. A key's PEXPIRE is only garbage collection - after a
full window an absent key and a full bucket are the same thing - never the mechanism that ends a
wait.

Redis unreachable = 503 DEPENDENCY_UNAVAILABLE. Fail closed (FR-ADR-028): a limiter that lets
everything through when Redis is down removes the control exactly when the system is least healthy.
"""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from fastapi import Request
from redis.exceptions import RedisError

from app.api.errors import ApiError
from app.core.config import Settings

# Units: a bucket's level is kept in "token-milliseconds" - tokens x window_ms - so the refill of
# capacity tokens per window_ms is `elapsed_ms x capacity` and every value stays an integer.
# ARGV[1] is the caller's instant in ms; then capacity and window_ms per key, in KEYS order.
# Returns {0, 0} when every bucket paid, else {i, ms until bucket i holds one token}.
_SCRIPT = """
local now = tonumber(ARGV[1])
local levels = {}
for i = 1, #KEYS do
  local cap = tonumber(ARGV[2 * i])
  local win = tonumber(ARGV[2 * i + 1])
  local stored = redis.call('HMGET', KEYS[i], 'level', 'at')
  local level = tonumber(stored[1])
  local at = tonumber(stored[2])
  if level == nil or at == nil then
    level = cap * win
    at = now
  end
  local elapsed = now - at
  if elapsed < 0 then elapsed = 0 end
  level = math.min(cap * win, level + elapsed * cap)
  if level < win then
    return {i, math.ceil((win - level) / cap)}
  end
  levels[i] = level
end
for i = 1, #KEYS do
  local win = tonumber(ARGV[2 * i + 1])
  redis.call('HSET', KEYS[i], 'level', levels[i] - win, 'at', now)
  redis.call('PEXPIRE', KEYS[i], win)
end
return {0, 0}
"""

_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


def render_span(seconds: int) -> str:
    """PRD S7.20: under 120 s in seconds, otherwise ceil(s / 60) minutes; singular for 1."""
    if seconds < 120:
        return "1 second" if seconds == 1 else f"{seconds} seconds"
    minutes = -(-seconds // 60)
    return f"{minutes} minutes"


@dataclass(frozen=True)
class Bucket:
    name: str  # "<bucket>:<dimension>" - the key's middle (S-XCT-15), e.g. "hold:user", "hold:ip"
    setting: str  # the Settings field holding the capacity
    window_seconds: int
    message: str  # "{span}" is replaced by render_span(Retry-After)
    capacity: int = 0  # filled from Settings by sized(); 0 only on the declarations below

    def sized(self, settings: Settings) -> Bucket:
        return Bucket(self.name, self.setting, self.window_seconds, self.message, getattr(settings, self.setting))


# The per-user sign-in bucket is keyed on the SUBMITTED address (no user is known before sign-in), hashed by the caller
# (app/api/auth.py) so an email address never sits in Redis in the clear.
LOGIN_EMAIL = Bucket("login:user", "RATE_LIMIT_LOGIN_USER_PER_15MIN", 900,
                     "Too many sign-in attempts for that email address. Try again in {span}.")
LOGIN_IP = Bucket("login:ip", "RATE_LIMIT_LOGIN_IP_PER_15MIN", 900,
                  "Too many sign-in attempts from this connection. Try again in {span}.")
REGISTER_IP = Bucket("register:ip", "RATE_LIMIT_REGISTER_IP_PER_HOUR", 3600,
                     "Too many accounts have been created from this connection. Try again in {span}.")
# P-ACC-07 row 4 and P-ACC-08 row 8: two buckets, never one (a recovery must not spend the request bucket twice).
RESET_REQUEST_IP = Bucket("reset_request:ip", "RATE_LIMIT_RESET_IP_PER_HOUR", 3600,
                          "Too many reset requests from this connection. Try again in {span}.")
RESET_CONFIRM_IP = Bucket("reset_confirm:ip", "RATE_LIMIT_RESET_CONFIRM_IP_PER_HOUR", 3600,
                          "Too many attempts from this connection. Try again in {span}.")


def _trusted(peer: str, allowed: str) -> bool:
    try:
        address = ipaddress.ip_address(peer)
    except ValueError:
        return False
    for item in allowed.split(","):
        try:
            if address in ipaddress.ip_network(item.strip(), strict=False):
                return True
        except ValueError:
            continue
    return False


def client_ip(request: Request, settings: Settings) -> str:
    """The real client address (FR-ADR-058): with exactly one trusted proxy - the load balancer, named
    by FORWARDED_ALLOW_IPS - it is the entry that proxy appended, the rightmost of X-Forwarded-For
    (rightmost-but-one of the whole chain, the proxy itself being the last hop). Anything to its left
    was written by the client and is ignored. From an untrusted peer the header is ignored entirely."""
    peer = request.client.host if request.client else ""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded and _trusted(peer, settings.FORWARDED_ALLOW_IPS):
        last = forwarded.split(",")[-1].strip()
        if last:
            return last
    return peer


def _key(bucket: Bucket, subject: str) -> str:
    # rl:<bucket>:<dimension>:<identifier> (S-XCT-15): the bucket name is required, or the sign-in bucket would spend
    # the seat-hold bucket's tokens. The identifier is a user id or an address - nothing a client chose.
    return f"rl:{bucket.name}:{subject or 'unknown'}"


async def enforce(request: Request, checks: list[tuple[Bucket, str]], unavailable: str) -> None:
    """Spend one token from every (bucket, subject) pair, or raise 429 / 503 as an ApiError."""
    settings: Settings = request.app.state.settings
    sized = [bucket.sized(settings) for bucket, _ in checks]
    keys = [_key(bucket, subject) for bucket, (_, subject) in zip(sized, checks)]
    now_ms = (request.app.state.clock.now() - _EPOCH) // timedelta(milliseconds=1)
    args: list[int] = [now_ms]
    for bucket in sized:
        args += [bucket.capacity, bucket.window_seconds * 1000]
    try:
        refused, wait_ms = await request.app.state.redis.eval(_SCRIPT, len(keys), *keys, *args)
    except (RedisError, OSError):
        raise ApiError(503, "DEPENDENCY_UNAVAILABLE", unavailable) from None
    if refused:
        retry_after = max(1, -(-int(wait_ms) // 1000))
        bucket = sized[int(refused) - 1]
        # The header and details.retry_after_seconds carry the same integer (P-XCT-07); the sentence renders it (S7.20).
        raise ApiError(429, "RATE_LIMITED", bucket.message.format(span=render_span(retry_after)),
                       {"retry_after_seconds": retry_after}, headers={"Retry-After": str(retry_after)})

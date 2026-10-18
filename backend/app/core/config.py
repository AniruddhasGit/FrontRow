# =====================================================================================================
# Environment configuration and validation  -  ZONE B (SRC-002 §6.2.4). Edited by the client.
#
# Every setting comes from an environment variable (SRC-002 §7.1, PRD P-XCT-15 / S7.9). There is no
# config file, and no single variable that names the deployment and switches behaviour by it: each
# behaviour gets its own variable (COOKIE_SECURE, PAYMENT_PROVIDER, MAIL_PROVIDER, LOG_LEVEL), so each
# one is separately visible and separately wrong.
#
# Validation runs before the server accepts a request. A missing or invalid value makes the process
# EXIT NON-ZERO with a message naming the variable. A container that starts, connects to nothing and
# reports healthy is worse than one that never starts, because the container runtime believes it is fine.
#
# THE INVENTORY IS COMPLETE (PRD S7.9 "How this inventory stays complete"). Every variable S7.9 lists
# is declared here from Phase 1, including those a later phase is the first to read, because the
# client's task definition is built from this list and `.env.example` must equal it. A required
# variable that nothing reads yet still has no correct guess, which is why it has no default.
#
# THE COMMENT RULE (S-XCT-40). Every statement in this file has a comment line directly above it,
# saying what breaks without it. Bounds marked [JUDGMENT CALL] are the build session's: no frozen
# source states them, and each one only refuses a value no ruling could mean.
# =====================================================================================================

# Postponed annotations: without it the `Settings` references inside the check lambdas' type hints
# would be evaluated at import, before the class exists.
from __future__ import annotations

# Regular expressions, for SECRET_NAME below: without it the boot log cannot tell which values to hide.
import re
# NamedTuple gives each cross-field check a name the boot error can print; Callable types its rule.
from collections.abc import Callable
# Annotated + StringConstraints let a required field carry a format rule without a Field() default.
from typing import Annotated, Literal, NamedTuple
# zoneinfo is the standard-library zone database. Without it check 3 cannot tell a real zone name
# from a typo, and "today's showtimes" land on the wrong day.
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

# Pydantic's settings module is the validation layer of a library FastAPI already depends on (S7.9).
from pydantic import AfterValidator, Field, StringConstraints, ValidationError
# BaseSettings reads the environment; SettingsConfigDict holds the reading rules below.
from pydantic_settings import BaseSettings, SettingsConfigDict

# A PostgreSQL URL. Without the pattern, a MySQL or HTTP URL pasted into the wrong parameter passes
# boot and fails later as a confusing driver error on the first probe.
PostgresUrl = Annotated[str, StringConstraints(pattern=r"^postgres(ql)?://")]
# A Redis URL; rediss:// is TLS. Anything else is a parameter pasted into the wrong slot.
RedisUrl = Annotated[str, StringConstraints(pattern=r"^rediss?://")]
# An HTTP(S) URL. Without it a bare host name produces receipt links that go nowhere.
HttpUrl = Annotated[str, StringConstraints(pattern=r"^https?://")]
# A port a non-root process can bind. Below 1024 the container exits at boot (both images run as a
# non-root user, P-XCT-18); above 65535 is not a port.
Port = Annotated[int, Field(ge=1024, le=65535)]

def _not_placeholder(value: str) -> str:
    if value.startswith("CHANGE_ME"):
        raise ValueError("is the placeholder from .env.example")
    return value


# A signing secret. Without the length floor a guessable key signs sessions; without the placeholder
# refusal a deployment copied from .env.example signs them with a key published in the repository.
SigningSecret = Annotated[str, StringConstraints(min_length=32), AfterValidator(_not_placeholder)]

# The value redacted in the boot log, in the same spelling the log formatter uses.
REDACTED = "[REDACTED]"
# A setting whose NAME matches this is never printed, at boot or anywhere else (S-XCT-29).
SECRET_NAME = re.compile(r"SECRET|PASSWORD|TOKEN|URL")


# Raised when the environment cannot produce valid settings. Without one exception type, the boot path
# cannot tell "the operator set something wrong" (exit 78) from a crash (exit 1).
class ConfigError(Exception):
    # Carries one line per problem and the variable names, so the boot line can list every bad
    # variable at once instead of making the operator fix them one restart at a time.
    def __init__(self, problems: list[str], names: list[str]) -> None:
        # The human-readable problems, one per variable or check.
        self.problems = problems
        # The variable names alone, for the boot line's machine-readable field.
        self.names = names
        # The joined message is what str(exc) and the boot line print.
        super().__init__("; ".join(problems))


# Every setting the API (and, from Phase 5, the worker) reads. PRD S7.9 is the source of every name,
# default and bound; where a row says ASSUMED, the value is ASSUMED here too.
class Settings(BaseSettings):
    # How the environment is read.
    model_config = SettingsConfigDict(
        # Without case_sensitive, `database_url` would also satisfy DATABASE_URL, and two spellings of
        # one variable is how a task definition and .env.example drift apart.
        case_sensitive=True,
        # Without env_ignore_empty, `DATABASE_URL=` (a blank Parameter Store value, a typo in a .env file) would
        # pass as a valid empty string instead of failing as missing.
        env_ignore_empty=True,
        # No env_file: the application never reads a file for configuration. Locally docker compose
        # injects the variables; in AWS the task definition does. One code path in both places.
        env_file=None,
        # Unknown variables are ignored: the container environment always holds PATH, HOSTNAME, etc.
        extra="ignore",
    )

    # ---- REQUIRED, NO DEFAULT (S7.9). A default here is the difference between a deployment that
    # ---- refuses to start and one that starts and is quietly wrong.

    # PostgreSQL connection string; carries the password, so a Parameter Store SecureString in AWS.
    # Wrong: /health/ready is 503 forever.
    DATABASE_URL: PostgresUrl
    # Redis for locks, cache and rate-limit buckets. Wrong: every hold returns 503, readiness is 503.
    REDIS_URL: RedisUrl
    # SQS in AWS, ElasticMQ locally. Wrong: receipts accumulate in the outbox and never leave.
    QUEUE_URL: HttpUrl
    # Signs the session token. A default signing secret is a forged session for anyone who reads
    # the source. Rotating it signs every customer out.
    JWT_SECRET: SigningSecret
    # The payment provider. The only permitted value is `simulated` (check 4); there is no fallback.
    PAYMENT_PROVIDER: str
    # The mail transport: exactly `ses` or `stub` (check 13). A default to the stub sends nothing.
    MAIL_PROVIDER: str
    # The private poster bucket. Wrong: poster upload fails and the redirect points at nothing.
    S3_BUCKET_NAME: str
    # Region for the SDK clients. Wrong: SQS, SES and S3 calls go to a region with none of them.
    AWS_REGION: str
    # The verified SES sender identity. Wrong: every receipt is rejected and the customer who has
    # paid cannot enter the hall.
    SES_SENDER_ADDRESS: str
    # The address used in emailed links. Wrong: the link in a receipt goes nowhere.
    PUBLIC_BASE_URL: HttpUrl
    # The session cookie's Secure flag. OPEN-TLS-01 is deferred and a default would decide it.
    COOKIE_SECURE: bool
    # The one trusted proxy for X-Forwarded-For. `*` trusts any peer, which is trusting the client,
    # and the rate limiter then protects nothing while appearing to work (check 6).
    FORWARDED_ALLOW_IPS: str
    # The Idempotency-Key prefix that makes the simulated payment fail on purpose. A default would be
    # a prefix an ordinary customer could hit by accident. 1-32 characters (S7.9).
    PAYMENT_SIMULATOR_FAIL_KEY_PREFIX: str = Field(min_length=1, max_length=32)

    # ---- WITH A DEFAULT, because the value is ruled and the default IS the ruled value (S7.9).

    # The seat hold, ruled at 3 minutes (SRC-003 OPEN-HOLD-01). A literal 180 anywhere else is a defect.
    SEAT_HOLD_TTL_SECONDS: int = Field(180, ge=1)
    # The ruled seat cap. Above 10 contradicts a ruling; below is stricter and allowed (check 7).
    MAX_SEATS_PER_BOOKING: int = 10
    # Signed minutes from the advertised start when sales close. PROVISIONAL: +15 is "after".
    SALES_CUTOFF_MINUTES: int = 15
    # The ruled currency (SRC-003 OPEN-LOCALE-01).
    CURRENCY_CODE: str = "INR"
    # Paise per rupee. A ONE-WAY DOOR: changing it rewrites what every past customer paid (check 2).
    CURRENCY_MINOR_UNIT_RATIO: int = 100
    # The zone every human-read time is rendered in (check 3).
    CINEMA_TIMEZONE: str = "Asia/Kolkata"
    # Seat-map cache lifetime. Zero means every poll rebuilds from PostgreSQL (check 10).
    SEATMAP_CACHE_TTL_SECONDS: int = Field(10, ge=0)
    # Movie and showtime list cache lifetime. Longer: an admin's publish takes longer to appear.
    LISTING_CACHE_TTL_SECONDS: int = Field(60, ge=0)
    # How often the client re-reads the seat map (check 10).
    SEATMAP_POLL_INTERVAL_SECONDS: int = Field(3, ge=1)
    # The per-key cache stampede guard. Too short and two callers rebuild.
    CACHE_REBUILD_LOCK_TTL_MS: int = Field(2000, ge=1)
    # The simulated payment's delay. It must never approach the hold (check 1).
    PAYMENT_SIMULATED_DELAY_MS: int = Field(1500, ge=0)
    # Without a connect timeout an unreachable Redis hangs requests instead of returning 503.
    REDIS_CONNECT_TIMEOUT_MS: int = Field(500, ge=50, le=10_000)
    # Without a command timeout a Redis that accepts and never answers hangs the request.
    REDIS_COMMAND_TIMEOUT_MS: int = Field(500, ge=50, le=10_000)
    # How long in-flight requests get after SIGTERM. Must be shorter than the ECS stop timeout, or
    # SIGKILL lands mid-drain (Zone C ordering, docs/30 Deployment/P1_TASK_DEFINITIONS.md).
    SHUTDOWN_DRAIN_TIMEOUT_SECONDS: int = Field(20, ge=1, le=120)
    # How long one readiness result is reused. 0 means every poll probes.
    READINESS_CACHE_TTL_SECONDS: float = Field(3, ge=0, le=30)
    # DEBUG in a deployed environment burns the 5 GB CloudWatch allowance and risks logging bodies.
    LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    # Connections held per process. db.t3.micro has roughly 110 in total, multiplied across processes.
    DB_POOL_SIZE: int = Field(5, ge=1)
    # Burst connections above the pool. Same ceiling.
    DB_POOL_MAX_OVERFLOW: int = Field(2, ge=0)
    # Server-side ceiling on one SQL statement. ASSUMED (S7.9). Absent, a slow aggregate holds a
    # pooled connection indefinitely and exhausts the pool.
    DB_STATEMENT_TIMEOUT_MS: int = Field(5000, ge=1)
    # Ceiling on connecting to PostgreSQL for the readiness probe. [JUDGMENT CALL] ASSUMED: neither the
    # variable nor the value is in S7.9 (reported as an inventory gap). Without it an unreachable
    # database hangs /health/ready instead of failing fast.
    DB_CONNECT_TIMEOUT_MS: int = Field(1000, ge=100, le=10_000)
    # Long-poll wait. Short polling burns the free-tier request allowance on empty receives.
    QUEUE_POLL_WAIT_SECONDS: int = Field(20, ge=0, le=20)
    # Ceiling on one SendMessage inside a customer's confirm request. ASSUMED (S7.9).
    QUEUE_SEND_TIMEOUT_MS: int = Field(2000, ge=1)
    # Ceiling on one SendEmail in the worker. ASSUMED (S7.9).
    SES_SEND_TIMEOUT_MS: int = Field(5000, ge=1)
    # Outbox rows relayed per worker loop. Too large starves the queue poll.
    OUTBOX_RELAY_BATCH_SIZE: int = Field(20, ge=1)
    # How old a pending outbox row must be before the relay claims it (check 9).
    OUTBOX_RELAY_MIN_AGE_SECONDS: int = Field(30, ge=0)
    # When a `sending` receipt claim counts as abandoned (check 9).
    RECEIPT_CLAIM_STALE_SECONDS: int = Field(900, ge=1)
    # Poster upload ceiling, rejected at the header.
    POSTER_MAX_BYTES: int = Field(2_097_152, ge=1)
    # Presigned poster URL lifetime (check 11).
    PRESIGNED_URL_TTL_SECONDS: int = Field(3600, ge=1)
    # The password length floor, in characters.
    PASSWORD_MIN_LENGTH: int = Field(12, ge=1)
    # Session lifetime, 12 hours. No frozen source names it (S7.9).
    SESSION_TTL_SECONDS: int = Field(43200, ge=1)
    # Single-use reset token lifetime, 30 minutes; the account section owns the number.
    PASSWORD_RESET_TTL_SECONDS: int = Field(1800, ge=1)
    # The stress script's self-concurrency threshold. Too loose and a serialised client passes.
    STRESS_CONCURRENCY_SPREAD_MS: int = Field(100, ge=1)
    # How many bcrypt hashes run at once: the concurrency at which sign-in starts returning 503. ASSUMED.
    BCRYPT_THREAD_POOL_SIZE: int = Field(2, ge=1)
    # How long one hash may take, including its wait for a pool slot. ASSUMED.
    BCRYPT_HASH_TIMEOUT_MS: int = Field(5000, ge=1)
    # bcrypt work factor. The build session's choice; measured in Phase 7.
    BCRYPT_COST: int = Field(12, ge=4, le=31)
    # Cache-Control max-age on the poster redirect. ASSUMED (check 11).
    POSTER_REDIRECT_CACHE_SECONDS: int = Field(300, ge=0)
    # The port the API binds inside the container. The target group, security group and container
    # port mapping must all use this number (check 12).
    API_PORT: Port = 8000
    # The port the worker's /metrics listener binds (check 12).
    WORKER_METRICS_PORT: Port = 8001
    # Minimum gap between two accepted receipt resends for one booking. ASSUMED.
    RECEIPT_RESEND_MIN_INTERVAL_SECONDS: int = Field(300, ge=1)

    # ---- RATE-LIMIT BUCKETS (S7.9 / S7.4). Every one is an estimate, replaced by Phase 7's load test.

    # Seat holds per user per minute.
    RATE_LIMIT_HOLD_USER_PER_MIN: int = Field(20, ge=1)
    # Seat holds per IP per minute.
    RATE_LIMIT_HOLD_IP_PER_MIN: int = Field(60, ge=1)
    # Booking confirmations per user per minute.
    RATE_LIMIT_CONFIRM_USER_PER_MIN: int = Field(10, ge=1)
    # Booking confirmations per IP per minute.
    RATE_LIMIT_CONFIRM_IP_PER_MIN: int = Field(30, ge=1)
    # Sign-in attempts per email per 15 minutes.
    RATE_LIMIT_LOGIN_USER_PER_15MIN: int = Field(10, ge=1)
    # Sign-in attempts per IP per 15 minutes.
    RATE_LIMIT_LOGIN_IP_PER_15MIN: int = Field(30, ge=1)
    # Registrations per IP per hour.
    RATE_LIMIT_REGISTER_IP_PER_HOUR: int = Field(5, ge=1)
    # Password-reset requests per IP per hour.
    RATE_LIMIT_RESET_IP_PER_HOUR: int = Field(5, ge=1)
    # Password-reset confirmations per IP per hour.
    RATE_LIMIT_RESET_CONFIRM_IP_PER_HOUR: int = Field(10, ge=1)
    # Booking-reference lookups per user per minute.
    RATE_LIMIT_LOOKUP_USER_PER_MIN: int = Field(20, ge=1)
    # Booking-reference lookups per IP per minute.
    RATE_LIMIT_LOOKUP_IP_PER_MIN: int = Field(60, ge=1)
    # Seat-map reads per IP per minute.
    RATE_LIMIT_SEATMAP_IP_PER_MIN: int = Field(120, ge=1)
    # Dashboard report requests per user per minute; the name is the contract's, not the pattern's.
    REPORTS_RATE_LIMIT_PER_USER_PER_MINUTE: int = Field(60, ge=1)


# Read by scripts/seed.py ONLY, never by the API or the worker (S7.9). A separate model, so the API
# never requires a variable it does not read and never holds the seed password.
class SeedSettings(BaseSettings):
    # The same reading rules as Settings.
    model_config = SettingsConfigDict(case_sensitive=True, env_ignore_empty=True, env_file=None, extra="ignore")
    # The one password on every seeded account. Required by the seed and by nothing else; never
    # committed, printed or logged. Absent: the seed exits before writing anything.
    SEED_DEFAULT_PASSWORD: str
    # Minutes added to a film's runtime for showtime.ends_at. ASSUMED. Over 50 the seeded schedule
    # overlaps itself at the 210-minute slot spacing.
    SEED_CHANGEOVER_MINUTES: int = Field(20, ge=0, le=50)
    # The domain every seeded address sits at. .invalid can never receive real mail (FR-ADR-067).
    SEED_EMAIL_DOMAIN: str = "demo.frontrow.invalid"


# The value .env.example ships for SEED_DEFAULT_PASSWORD. Refused by value, because the placeholder
# must never become the deployed password (S7.9). The length bounds are S-XCT-48's, in Phase 2.
SEED_PASSWORD_PLACEHOLDER = "CHANGE_ME_NOT_A_REAL_PASSWORD"


# One cross-field check: a name the boot error prints, the variables it reads, the rule, and the
# sentence an operator reads when it fails.
class CrossFieldCheck(NamedTuple):
    # Printed first in the boot error, so the failure is searchable.
    name: str
    # The variables involved, listed in the boot line's missing_or_invalid field.
    variables: tuple[str, ...]
    # True when the configuration is acceptable.
    holds: Callable[[Settings], bool]
    # What must be true, in the operator's words.
    rule: str


# Without this helper check 3 would need a try/except inside a lambda, which Python cannot express.
def _zone_exists(name: str) -> bool:
    # ZoneInfo raises for a name the zone database does not hold; an empty or odd string raises too.
    try:
        # Constructing the zone is the whole test.
        ZoneInfo(name)
    # A typo like Asia/Nowhere lands here; a malformed key (a path) raises ValueError.
    except (ZoneInfoNotFoundError, ValueError):
        # Not a zone: refuse at boot rather than at the first date comparison.
        return False
    # The zone resolved.
    return True


# THE CROSS-FIELD CHECKS RUN AT BOOT (PRD S7.9), in S7.9's own order. THIRTEEN, not twelve: S7.9's
# prose says twelve and is stale; an implementation built to twelve drops the mail-transport check
# (13), after which a typo in MAIL_PROVIDER runs the deployment with no transport and receipts vanish.
# Per-field types are not enough: each of these would otherwise be found in the deployed environment.
CROSS_FIELD_CHECKS: tuple[CrossFieldCheck, ...] = (
    # 1. A payment that outlives the hold is a customer paying for seats that have expired. Integer
    # arithmetic (delay x 10 < ttl x 1000) is the same rule as delay < ttl x 1000 x 0.1 without a float.
    CrossFieldCheck(
        "payment_delay_inside_hold",
        ("PAYMENT_SIMULATED_DELAY_MS", "SEAT_HOLD_TTL_SECONDS"),
        lambda s: s.PAYMENT_SIMULATED_DELAY_MS * 10 < s.SEAT_HOLD_TTL_SECONDS * 1000,
        "PAYMENT_SIMULATED_DELAY_MS must be less than SEAT_HOLD_TTL_SECONDS x 1000 x 0.1",
    ),
    # 2. A one-way door walked through by a typo.
    CrossFieldCheck(
        "inr_minor_unit_ratio",
        ("CURRENCY_MINOR_UNIT_RATIO", "CURRENCY_CODE"),
        lambda s: not (s.CURRENCY_CODE == "INR" and s.CURRENCY_MINOR_UNIT_RATIO != 100),
        "CURRENCY_MINOR_UNIT_RATIO must be 100 while CURRENCY_CODE is INR",
    ),
    # 3. An invalid zone fails at the first date comparison instead of at boot.
    CrossFieldCheck(
        "cinema_timezone_resolves",
        ("CINEMA_TIMEZONE",),
        lambda s: _zone_exists(s.CINEMA_TIMEZONE),
        "CINEMA_TIMEZONE must name a zone in the time zone database, e.g. Asia/Kolkata",
    ),
    # 4. This project never has a real payment provider (SRC-003 OPEN-PAY-01).
    CrossFieldCheck(
        "payment_provider_simulated",
        ("PAYMENT_PROVIDER",),
        lambda s: s.PAYMENT_PROVIDER == "simulated",
        "PAYMENT_PROVIDER must be 'simulated', the only permitted value",
    ),
    # 5. A Secure cookie over plain HTTP is never sent back, so nobody can stay signed in.
    CrossFieldCheck(
        "secure_cookie_needs_https",
        ("COOKIE_SECURE", "PUBLIC_BASE_URL"),
        lambda s: not s.COOKIE_SECURE or s.PUBLIC_BASE_URL.startswith("https://"),
        "COOKIE_SECURE must be false unless PUBLIC_BASE_URL begins https://",
    ),
    # 6. A rate limiter that trusts a forged header protects nothing.
    CrossFieldCheck(
        "no_wildcard_proxy",
        ("FORWARDED_ALLOW_IPS",),
        lambda s: s.FORWARDED_ALLOW_IPS.strip() != "*",
        "FORWARDED_ALLOW_IPS must not be '*'",
    ),
    # 7. Exceeding a client ruling. Below 10 is stricter and allowed.
    CrossFieldCheck(
        "seat_cap_within_ruling",
        ("MAX_SEATS_PER_BOOKING",),
        lambda s: 1 <= s.MAX_SEATS_PER_BOOKING <= 10,
        "MAX_SEATS_PER_BOOKING must be between 1 and 10 inclusive",
    ),
    # 8. Receipts failing at send time rather than at boot.
    CrossFieldCheck(
        "ses_needs_sender_and_region",
        ("MAIL_PROVIDER", "SES_SENDER_ADDRESS", "AWS_REGION"),
        lambda s: s.MAIL_PROVIDER != "ses" or bool(s.SES_SENDER_ADDRESS.strip() and s.AWS_REGION.strip()),
        "MAIL_PROVIDER=ses requires SES_SENDER_ADDRESS and AWS_REGION to be non-empty",
    ),
    # 9. The relay reclaiming a send that is still in progress.
    CrossFieldCheck(
        "claim_stale_after_relay_age",
        ("RECEIPT_CLAIM_STALE_SECONDS", "OUTBOX_RELAY_MIN_AGE_SECONDS"),
        lambda s: s.RECEIPT_CLAIM_STALE_SECONDS > s.OUTBOX_RELAY_MIN_AGE_SECONDS,
        "RECEIPT_CLAIM_STALE_SECONDS must be greater than OUTBOX_RELAY_MIN_AGE_SECONDS",
    ),
    # 10. Worst-case seat-map staleness drifting past "accurate within a few seconds".
    CrossFieldCheck(
        "seatmap_staleness_bound",
        ("SEATMAP_CACHE_TTL_SECONDS", "SEATMAP_POLL_INTERVAL_SECONDS"),
        lambda s: s.SEATMAP_CACHE_TTL_SECONDS + s.SEATMAP_POLL_INTERVAL_SECONDS <= 15,
        "SEATMAP_CACHE_TTL_SECONDS + SEATMAP_POLL_INTERVAL_SECONDS must be at most 15",
    ),
    # 11. A cached redirect outliving its presigned target breaks posters mid-page.
    CrossFieldCheck(
        "poster_redirect_inside_presign",
        ("POSTER_REDIRECT_CACHE_SECONDS", "PRESIGNED_URL_TTL_SECONDS"),
        lambda s: s.POSTER_REDIRECT_CACHE_SECONDS < s.PRESIGNED_URL_TTL_SECONDS,
        "POSTER_REDIRECT_CACHE_SECONDS must be less than PRESIGNED_URL_TTL_SECONDS",
    ),
    # 12. A privileged port, or two processes on one port where the second dies and takes receipts
    # with it. Checked in every process that loads settings, so each refuses its own bad value.
    CrossFieldCheck(
        "distinct_unprivileged_ports",
        ("API_PORT", "WORKER_METRICS_PORT"),
        lambda s: 1024 <= s.API_PORT <= 65535 and 1024 <= s.WORKER_METRICS_PORT <= 65535 and s.API_PORT != s.WORKER_METRICS_PORT,
        "API_PORT and WORKER_METRICS_PORT must each be between 1024 and 65535 and must differ",
    ),
    # 13. A mail transport nobody named: a typo makes check 8 never fire and receipts vanish.
    CrossFieldCheck(
        "mail_provider_named",
        ("MAIL_PROVIDER",),
        lambda s: s.MAIL_PROVIDER in ("ses", "stub"),
        "MAIL_PROVIDER must be exactly 'ses' or 'stub'",
    ),
)


# Turns pydantic's error list into ConfigError. The message NEVER echoes the value: DATABASE_URL
# carries a password, and a boot error is the first thing that lands in CloudWatch.
def _config_error(exc: ValidationError) -> ConfigError:
    # One problem line per error, one name per variable.
    problems: list[str] = []
    # Each variable listed once, in the order pydantic reports them.
    names: list[str] = []
    # include_input=False keeps the offending value out of every message.
    for err in exc.errors(include_input=False, include_url=False):
        # loc[0] is the field, i.e. the environment variable's name.
        name = str(err["loc"][0]) if err.get("loc") else "<unknown>"
        # Without the membership test a variable with two errors is listed twice.
        if name not in names:
            # Recorded for the boot line's machine-readable field.
            names.append(name)
        # "missing" covers both unset and set-but-empty (env_ignore_empty above).
        if err["type"] == "missing":
            # The operator's fix is to set it.
            problems.append(f"{name} is required and is not set (or is set to an empty string)")
        # Every other type: the rule broken, which names the bound ("greater than or equal to 1024").
        else:
            # err["msg"] describes the rule, never the input, because include_input=False.
            problems.append(f"{name} is invalid: {err['msg']}")
    # Raised by the caller, chained from nothing so pydantic's input-carrying traceback is dropped.
    return ConfigError(problems, names)


# Read and validate the process environment, or raise ConfigError naming every bad variable.
def load_settings() -> Settings:
    # Per-field types and bounds first; the cross-field checks need parsed values to compare.
    try:
        # Required fields come from the environment; there is nothing to pass.
        settings = Settings()  # type: ignore[call-arg]
    # A missing or ill-typed variable.
    except ValidationError as exc:
        # `from None`: the original exception carries pydantic's context, which can include input.
        raise _config_error(exc) from None
    # Every failing cross-field check, not just the first, so one restart shows them all.
    failed = [c for c in CROSS_FIELD_CHECKS if not c.holds(settings)]
    # A failure stops the boot exactly like a missing variable does.
    if failed:
        # Each line leads with the check's name and the rule, which names its variables.
        raise ConfigError([f"{c.name}: {c.rule}" for c in failed], [v for c in failed for v in c.variables])
    # Valid.
    return settings


# The seed's own boot validation (S7.9 "Read by the seed script only"). Phase 2's seed calls it.
def load_seed_settings() -> SeedSettings:
    # The same field validation as the API.
    try:
        # SEED_DEFAULT_PASSWORD has no default, so an unset one fails here.
        seed = SeedSettings()  # type: ignore[call-arg]
    # Missing or ill-typed.
    except ValidationError as exc:
        # Same message rules: the name, never the value.
        raise _config_error(exc) from None
    # The committed placeholder must never become a real password; refused by value.
    if seed.SEED_DEFAULT_PASSWORD == SEED_PASSWORD_PLACEHOLDER:
        # The message names the variable and does not repeat the value.
        raise ConfigError(["SEED_DEFAULT_PASSWORD is still the .env.example placeholder; set a real one"], ["SEED_DEFAULT_PASSWORD"])
    # Valid.
    return seed


# The resolved configuration for the one boot log line, every secret-named value replaced.
def redacted(settings: Settings) -> dict[str, object]:
    # By NAME, so a new secret-named variable is redacted without anyone remembering to.
    return {k: REDACTED if SECRET_NAME.search(k) else v for k, v in settings.model_dump().items()}

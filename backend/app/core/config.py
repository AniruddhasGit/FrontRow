"""Environment configuration and validation  -  ZONE B (SRC-002 §6.2.4).

Every setting comes from an environment variable (SRC-002 §7.1, PRD P-XCT-15 / S7.9). There is no
config file and no ENVIRONMENT=production|development switch: each behaviour gets its own variable so
each one is separately visible and separately wrong.

Validation runs before the server accepts a request. A missing or invalid value makes the process
EXIT NON-ZERO with a message naming the variable. That is the whole point: a container that starts,
connects to nothing and reports healthy is worse than one that never starts, because the container
runtime believes it is fine.

PHASE 1 SCOPE. Only the variables Phase 1 code actually reads are declared here. The rest of the
S7.9 inventory (JWT_SECRET, QUEUE_URL, PAYMENT_PROVIDER, SEAT_HOLD_TTL_SECONDS, ...) is added in the
phase that first reads it. Declaring a required variable nothing reads would force the operator to
invent a value for it now, which is the "sensible default" failure in a different shape.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field, ValidationError, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class ConfigError(Exception):
    """Raised when the environment cannot produce a valid Settings. Carries one line per problem."""

    def __init__(self, problems: list[str], names: list[str]) -> None:
        self.problems = problems
        self.names = names
        super().__init__("; ".join(problems))


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        # Without case_sensitive, `database_url` in the environment would also satisfy DATABASE_URL,
        # and two spellings of one variable is how a task definition and .env.example drift apart.
        case_sensitive=True,
        # Without env_ignore_empty, `DATABASE_URL=` (set but empty, the classic result
        # of a blank SSM value or a typo in a .env file) would pass as a valid empty string.
        env_ignore_empty=True,
        # No env_file: the application never reads a file for configuration. Locally docker compose
        # injects the variables; in AWS the task definition does. One code path in both places.
        env_file=None,
        # Unknown variables are ignored: the container environment always holds PATH, HOSTNAME, etc.
        extra="ignore",
    )

    # ---- required: NO default. There is no correct guess, and a guessed localhost value produces a
    # container that starts, connects to nothing and reports healthy.  (PRD S7.9)

    # PostgreSQL connection string. In AWS: an SSM SecureString injected by the task definition,
    # because it carries the password. Wrong value: /health/ready is 503 forever.
    DATABASE_URL: str
    # Redis connection string. Wrong value: /health/ready is 503 forever (and from Phase 4 every
    # seat hold returns 503, by design - SRC-002 §7.9 forbids falling back to the database).
    REDIS_URL: str

    # ---- with a default, because the default IS the ruled value (PRD S7.9) -----------------------

    # DEBUG in a deployed environment burns the 5 GB CloudWatch free tier and risks logging bodies.
    LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    # The port uvicorn binds inside the container. Below 1024 a non-root process cannot bind at all
    # and the container exits at boot; any other wrong value starts fine and fails every LB check.
    API_PORT: int = Field(8000, ge=1024, le=65535)
    # Without a connect timeout an unreachable database turns /health/ready into a hung request
    # instead of a fast 503. [JUDGMENT CALL] ASSUMED: no frozen source names this value or variable;
    # 1000 ms matches the order of the two Redis timeouts PRD S7.9 publishes.
    DB_CONNECT_TIMEOUT_MS: int = Field(1000, ge=100, le=10_000)
    # No timeout turns an unreachable Redis node into hung requests rather than a 503, and hung
    # requests exhaust the connection pool. (PRD S7.9)
    REDIS_CONNECT_TIMEOUT_MS: int = Field(500, ge=50, le=10_000)
    # Without a command timeout, a Redis that accepts the connection but never answers hangs the request.
    REDIS_COMMAND_TIMEOUT_MS: int = Field(500, ge=50, le=10_000)
    # How long in-flight requests get after SIGTERM. Must be SHORTER than the ECS stop timeout (which
    # starts at SIGTERM, after the deregistration delay has already run), or SIGKILL lands mid-drain
    # (Zone C ordering, PRD P-XCT-17, prep-queue row 23).
    SHUTDOWN_DRAIN_TIMEOUT_SECONDS: int = Field(20, ge=1, le=120)
    # How long one readiness result is reused. Longer than the load balancer's unhealthy-threshold
    # window and the LB reacts to stale information. 0 means every poll probes.
    READINESS_CACHE_TTL_SECONDS: float = Field(3, ge=0, le=30)

    @field_validator("DATABASE_URL")
    @classmethod
    def _postgres_scheme(cls, v: str) -> str:
        # Without this, a MySQL or HTTP URL pasted into the wrong parameter is accepted at boot and
        # fails later as a confusing driver error on the first probe.
        if not v.startswith(("postgresql://", "postgres://")):
            raise ValueError("must start with postgresql:// or postgres://")
        return v

    @field_validator("REDIS_URL")
    @classmethod
    def _redis_scheme(cls, v: str) -> str:
        # rediss:// is TLS. Both are accepted; anything else is a parameter pasted into the wrong slot.
        if not v.startswith(("redis://", "rediss://")):
            raise ValueError("must start with redis:// or rediss://")
        return v


def load_settings() -> Settings:
    """Read and validate the process environment, or raise ConfigError naming every bad variable.

    The message NEVER echoes the value: DATABASE_URL carries a password, and a boot error is the
    first thing that lands in CloudWatch.
    """
    try:
        return Settings()  # type: ignore[call-arg]  # required fields come from the environment
    except ValidationError as exc:
        problems: list[str] = []
        names: list[str] = []
        for err in exc.errors(include_input=False, include_url=False):
            name = str(err["loc"][0]) if err.get("loc") else "<unknown>"
            if name not in names:
                names.append(name)
            if err["type"] == "missing":
                problems.append(f"{name} is required and is not set (or is set to an empty string)")
            else:
                # err["msg"] describes the rule ("Input should be greater than or equal to 1024"),
                # never the input itself, because include_input=False above.
                problems.append(f"{name} is invalid: {err['msg']}")
        raise ConfigError(problems, names) from None

"""Process boot and graceful shutdown  -  ZONE B (SRC-002 §6.2.4, §6.2.5, §7.1, §7.5).

Boot order, and why it is this order:
  1. load + validate configuration  -> on failure: one JSON line naming the variable, exit 78
  2. configure JSON logging          -> only now, because the log level is itself configuration
  3. build the app, start uvicorn    -> the first request can only arrive after 1 and 2 succeeded

SIGTERM (what ECS sends on deploy, scale-in or `docker stop`), and what happens, in order:
  a. uvicorn closes the listening socket       -> no NEW connection is accepted
  b. in-flight requests run to completion      -> bounded by SHUTDOWN_DRAIN_TIMEOUT_SECONDS
  c. the lifespan shutdown runs the hooks      -> Phase 4: release this instance's seat holds
  d. the process exits 0
ECS waits out the target group's deregistration delay BEFORE it sends SIGTERM. If ECS's stop timeout
(counted from SIGTERM) is shorter than the drain timeout plus c, SIGKILL arrives during b and c never
runs; the strict safe bound is stop timeout > deregistration delay + drain timeout. That ordering is Zone C (docs/30 Deployment/), and it breaks silently.

MIGRATIONS ARE NOT HERE, AND MUST NEVER BE ADDED HERE (SRC-002 §7.8). Nothing in this file, in
app/main.py or in the lifespan may apply a migration. They are a separate `migrate` command of the
entrypoint, run by hand as a one-off task before the service is updated.
"""

from __future__ import annotations

import asyncio
import logging
import signal
import sys
from types import FrameType

import uvicorn

from app.core.clock import SystemClock
from app.core.config import ConfigError, Settings, load_settings, redacted, venue_zone_check
from app.core.logging import configure_logging, emit_fatal, new_request_id

log = logging.getLogger("app.lifecycle")

# sysexits.h EX_CONFIG. A distinct code, so "stopped because the configuration is wrong" is
# distinguishable from a crash (1) in the ECS stopped-task reason without reading a log.
EXIT_CONFIG = 78


class _Server(uvicorn.Server):
    """uvicorn's server, plus one log line when the stop signal arrives and the shutdown duration."""

    clock = SystemClock()
    signalled_at: float | None = None

    def handle_exit(self, sig: int, frame: FrameType | None) -> None:
        if self.signalled_at is None:
            self.signalled_at = self.clock.monotonic()
            # Without this line the log shows the process simply stop, and "was it killed or did it
            # shut down?" has no answer in CloudWatch.
            log.info("stop signal received; refusing new connections and draining", extra={"signal": signal.Signals(sig).name})
        super().handle_exit(sig, frame)


def _swallow(sig: int, frame: FrameType | None) -> None:
    """Installed as the 'previous' handler before uvicorn takes over the signals.

    uvicorn re-raises the captured signal after its own graceful shutdown, against whatever handler
    was there before it started. Without this no-op, that handler is the default one, the re-raised
    SIGTERM kills the process after it has ALREADY drained cleanly, and the exit code becomes 143
    instead of 0 - so ECS records every clean deploy as a task killed by a signal.
    """


def serve(settings: Settings, app: object) -> int:
    config = uvicorn.Config(
        app,  # type: ignore[arg-type]
        # 0.0.0.0, not 127.0.0.1: inside a container, loopback is unreachable from the load balancer
        # and from the Docker port mapping. The security group, not the bind address, is the fence.
        host="0.0.0.0",
        # API_PORT (default 8000), never a literal: the target group, the security group and the container
        # port mapping are built against this number, and if they disagree every health check fails.
        port=settings.API_PORT,
        # ONE worker process. Each uvicorn worker is a full Python process; two roughly double the
        # API's memory on a 1 GB host (PRD P-XCT-21). Scale with tasks, not workers.
        workers=1,
        # Without timeout_graceful_shutdown uvicorn waits for in-flight requests FOREVER, and the
        # only thing that ends a stuck drain is ECS's SIGKILL - which skips the release hooks.
        timeout_graceful_shutdown=settings.SHUTDOWN_DRAIN_TIMEOUT_SECONDS,
        # Without lifespan="on", a failure in startup is logged and ignored and the server serves
        # anyway; with it, a startup failure stops the process.
        lifespan="on",
        # log_config=None: uvicorn must not install its own plain-text handlers over our JSON one.
        log_config=None,
        # Our middleware writes the one completion line per request, with the request id. uvicorn's
        # access line has no request id and would double the volume.
        access_log=False,
        # Without it, every response names the server software and version, which tells a scanner
        # which published vulnerabilities to try.
        server_header=False,
        # uvicorn's own proxy handling stays OFF: with it on, request.client becomes whatever the header
        # says and the peer address is lost. The rate limiter reads X-Forwarded-For itself, and trusts it
        # only from the peer FORWARDED_ALLOW_IPS names (required at boot; app/core/ratelimit.py client_ip).
        proxy_headers=False,
    )
    # The subclass that records when the signal arrived, for the shutdown_ms field below.
    server = _Server(config)
    # No-op handlers installed BEFORE uvicorn starts: uvicorn re-raises the signal against these after its
    # graceful drain. Without them the re-raised SIGTERM kills an already-drained process and ECS records
    # exit 143 for every clean deploy (see _swallow above).
    signal.signal(signal.SIGTERM, _swallow)
    # Ctrl-C in a terminal: the same drain, the same clean exit.
    signal.signal(signal.SIGINT, _swallow)
    # Blocks until the drain is complete: stop accepting, finish in-flight requests (or hit the drain
    # timeout), run the lifespan shutdown (the release hooks), then return.
    server.run()
    if not server.started:
        # Port already bound, lifespan startup raised, ...: uvicorn has logged why. Non-zero, so the
        # orchestrator sees a failed start and not a clean stop.
        return 1
    # How long the drain took. Without it a deploy that keeps hitting the stop timeout looks identical in the
    # log to one that drained in milliseconds.
    fields = {}
    if server.signalled_at is not None:
        fields["shutdown_ms"] = round((server.clock.monotonic() - server.signalled_at) * 1000)
    log.info("api stopped cleanly", extra=fields)
    # 0 after a clean drain, so ECS records a deploy as a stop and not as a crash.
    return 0


def main(service: str = "api") -> int:
    """Boot one process: `api` (the default) or `worker`. Both take steps 1 and 2 above identically, so a bad value
    stops either one the same way, and each refuses its own configuration (check 12)."""
    clock = SystemClock()
    try:
        settings = load_settings()
    except ConfigError as exc:
        # Before logging is configured, so the line is written directly - still one JSON object on
        # stdout, so the awslogs driver captures it and the stopped-task reason can be found.
        emit_fatal(
            f"configuration invalid, refusing to start: {exc}",
            clock.now,
            # stderr as well as stdout: the operator running the container by hand reads stderr, and
            # S-XCT-29 / S-SCP-03 require the variable's name there. stdout keeps the JSON-lines rule.
            also_stderr=True,
            missing_or_invalid=exc.names,
            # Which process refused. Without it a worker's refusal reads as the api's in CloudWatch.
            service=service,
        )
        return EXIT_CONFIG
    # A fresh id per boot. Every line this process writes carries it, so "which container said
    # this" survives a restart that reuses the same host. (P-XCT-17 also keys the Phase 4 hold
    # registry on it.)
    instance_id = new_request_id()
    configure_logging(level=settings.LOG_LEVEL, service=service, instance_id=instance_id, now=clock.now)
    # The resolved configuration, exactly once per boot, so an operator can read what the process
    # actually loaded (PRD S7.9). Every value whose NAME matches SECRET|PASSWORD|TOKEN|URL is
    # [REDACTED] at the source. payment_provider is ALSO a top-level field (S-PAY-04): one query on the
    # field answers "are payments real here?" without parsing the nested settings object.
    log.info("configuration resolved", extra={"settings": redacted(settings), "payment_provider": settings.PAYMENT_PROVIDER})
    if service == "worker":
        # The SQS/ElasticMQ consumer (Phase 5). Imported here so the api process never loads it.
        from app.workers import run_worker

        return run_worker(settings, clock)
    from app.main import create_app  # after logging, so import-time log lines are JSON too

    # One read of the cinema rows, so a zone mismatch or an unseeded venue is said once at boot (S-ADM-04).
    asyncio.run(venue_zone_check(settings))
    app = create_app(settings, clock=clock)
    # The receipt fast path (P-TKT-04 step 3). Installed HERE, on the real process only, not in create_app: a test
    # app built by create_app has no queue unless the test installs one, so no test sends to a real queue by accident.
    from app.workers import RESET, receipt_port

    app.state.receipt_queue = receipt_port(app.state, settings, clock)
    # The reset message's post-commit send (P-ACC-07 step 6): the same port, the other topic.
    app.state.reset_queue = receipt_port(app.state, settings, clock, topic=RESET)
    if settings.MAIL_PROVIDER != "resend":
        # /metrics queue_depth (P-XCT-13). The Render copy has no queue, so there it renders NaN.
        from app.core.metrics import QueueDepth
        from app.workers.queue import SqsQueue

        app.state.queue_depth = QueueDepth(SqsQueue(settings).depth, clock.monotonic)
    return serve(settings, app)


if __name__ == "__main__":
    sys.exit(main())

#!/bin/sh
# =====================================================================================================
# FrontRow API container entrypoint  -  ZONE B (SRC-002 §6.2.2). Edited by the client.
#
#   frontrow-entrypoint api       start the API server (the image's default CMD)
#   frontrow-entrypoint worker    start the queue consumer: the outbox relay and the receipt / reset emails (Phase 5).
#                                 The SAME image as the api, a different command (SRC-003 OPEN-PROC-01: three processes).
#   frontrow-entrypoint migrate   apply database migrations, then EXIT. Run by hand, as a one-off
#                                 task, BEFORE updating the service. Never on boot (SRC-002 §7.8).
#   frontrow-entrypoint seed      write the demonstration data (scripts/seed.py), then EXIT. A one-off
#                                 task on its own task definition family (P-XCT-32), run once, by hand.
#
# Every line that exists for a production reason says what breaks without it.
# =====================================================================================================

# Without `set -eu`, a failing command or a misspelled variable is silently ignored and the script
# carries on to start a server in a half-configured state.
set -eu

# One JSON line on stdout, so even the entrypoint's own messages pass the "every line is JSON" check
# and land in CloudWatch in the same shape as the application's. The request id is 8 hex characters
# from /dev/urandom, the same format the application generates.
log() {
  # 4 random bytes as 8 hex characters. Without a fresh one per line, two entrypoint lines share an id.
  rid=$(od -An -N4 -tx1 /dev/urandom | tr -d ' \n')
  # The JSON line itself, in a fixed format, so CloudWatch can parse it like the application's lines.
  printf '{"timestamp":"%s","level":"%s","logger":"entrypoint","message":"%s","request_id":"%s","service":"%s","instance_id":null}\n' \
    "$(date -u +%Y-%m-%dT%H:%M:%S.000Z)" "$1" "$2" "$rid" "$service"
# End of log().
}

# The command, reduced to safe characters, is the "service" field of the entrypoint's own lines: without it a
# migration's line reads as the api's in CloudWatch (S-XCT-25: every migrate line carries service "migrate").
service=$(printf '%s' "${1:-api}" | tr -cd 'A-Za-z0-9_-')
# Dispatch on the command; with none given, start the API (the image's default CMD is `api`).
case "${1:-api}" in
  # The API server.
  api)
    # `exec` REPLACES this shell with Python, so Python becomes PID 1 and receives SIGTERM directly.
    # Without exec, the shell is PID 1, it does not forward SIGTERM, the app never drains, and ECS
    # SIGKILLs it after the stop timeout - mid-request, with no lock release.
    #
    # NOTHING may be added above this line that touches the database. In particular never chain the
    # migrate command in front of this exec: that is "migrations on boot", and two tasks starting
    # together then race on the same schema change (the migration tool takes no lock - GOTCHAS.md).
    exec python -m app api
    # End of the api branch (never reached: exec replaced the shell).
    ;;
  # The queue consumer. Long-running, like the api, and like the api it never touches the schema.
  worker)
    # `exec` for the same reason as the api: the worker must be PID 1 to receive SIGTERM, finish the message in hand
    # and exit 0. Behind a shell, SIGKILL lands mid-send and the claim is left `sending` until it goes stale (15 min).
    exec python -m app worker
    # End of the worker branch (never reached: exec replaced the shell).
    ;;
  # The one-off migration command, run by hand before a service update. Never on boot.
  migrate)
    # Applies every pending revision in ONE transaction, then EXITS with the migration's status: `exec`
    # makes alembic PID 1, so its exit code is the task's exit code. Step 3 of the deploy order reads
    # that code; without exec a failed migration could still end in exit 0.
    # DATABASE_URL must be the OWNER's connection string here (frontrow_owner), not the app's.
    # Paths are relative to /srv, the image's WORKDIR, where migrations/ is copied.
    log "INFO" "migrate: applying alembic revisions up to head"
    # exec, so the migration tool's exit status is the task's exit status.
    exec alembic -c migrations/alembic.ini upgrade head
    # End of the migrate branch (never reached: exec replaced the shell).
    ;;
  # The one-off demonstration seed (P-XCT-30, P-XCT-32). Never part of a long-running process.
  seed)
    # Drop the word `seed`, so any further arguments (e.g. --help) reach the script unchanged.
    shift
    # The seed reads SEED_DEFAULT_PASSWORD, which only the seed's own task definition carries. It runs as
    # its own process and exits; without a separate command the only way to seed would be a flag on the
    # api, and then every api task that booted would seed.
    log "INFO" "seed: writing the demonstration data"
    # exec, so the seed's exit status is the task's exit status: a refusal (78) or a failure (1) must reach
    # the stopped-task reason, never be masked as 0. Path relative to /srv, where the image puts scripts/.
    exec python scripts/seed.py "$@"
    # End of the seed branch (never reached: exec replaced the shell).
    ;;
  # Anything else is a typo in the task definition's command.
  *)
    # Without this, a typo in the task definition's command (e.g. "API") would fall through and the
    # task would exit with no explanation. EX_USAGE. The command is reduced to safe characters first:
    # a quote inside it would break the JSON line.
    log "CRITICAL" "unknown command '$(printf '%s' "$1" | tr -cd 'A-Za-z0-9_-')'; expected: api | worker | migrate | seed"
    # EX_USAGE: distinct from a crash (1) and a bad configuration (78) in the stopped-task reason.
    exit 64
    # End of the unknown-command branch.
    ;;
# End of the dispatch.
esac

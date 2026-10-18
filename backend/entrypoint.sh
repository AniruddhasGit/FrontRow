#!/bin/sh
# =====================================================================================================
# FrontRow API container entrypoint  -  ZONE B (SRC-002 §6.2.2). Edited by the client.
#
#   frontrow-entrypoint api       start the API server (the image's default CMD)
#   frontrow-entrypoint migrate   apply database migrations, then EXIT. Run by hand, as a one-off
#                                 task, BEFORE updating the service. Never on boot (SRC-002 §7.8).
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
  rid=$(od -An -N4 -tx1 /dev/urandom | tr -d ' \n')
  printf '{"timestamp":"%s","level":"%s","logger":"entrypoint","message":"%s","request_id":"%s","service":"api","instance_id":null}\n' \
    "$(date -u +%Y-%m-%dT%H:%M:%S.000Z)" "$1" "$2" "$rid"
}

case "${1:-api}" in
  api)
    # `exec` REPLACES this shell with Python, so Python becomes PID 1 and receives SIGTERM directly.
    # Without exec, the shell is PID 1, it does not forward SIGTERM, the app never drains, and ECS
    # SIGKILLs it after the stop timeout - mid-request, with no lock release.
    #
    # NOTHING may be added above this line that touches the database. In particular never
    # `alembic upgrade head && exec ...`: that is "migrations on boot", and two tasks starting
    # together then race on the same schema change (Alembic takes no lock - GOTCHAS.md).
    exec python -m app api
    ;;
  migrate)
    # Phase 1 has no migrations (no data model exists yet - SRC-002 §12.2). This branch exists now so
    # the command is already a separate, explicit path when Phase 2 adds `alembic upgrade head` here.
    # Exits 0 because nothing was asked of it that it failed to do - and it says so.
    log "INFO" "migrate: no migrations exist in Phase 1; nothing was applied"
    exit 0
    ;;
  *)
    # Without this, a typo in the task definition's command (e.g. "API") would fall through and the
    # task would exit with no explanation. EX_USAGE. The command is reduced to safe characters first:
    # a quote inside it would break the JSON line.
    log "CRITICAL" "unknown command '$(printf '%s' "$1" | tr -cd 'A-Za-z0-9_-')'; expected: api | migrate"
    exit 64
    ;;
esac

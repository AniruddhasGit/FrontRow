"""`python -m app api` starts the API server. This is what the entrypoint execs.

The worker (`python -m app worker`) arrives in Phase 5. Migrations are deliberately NOT a command of
this module: they are the entrypoint's separate `migrate` command (SRC-002 §7.8).
"""

import sys

from app.core.clock import SystemClock
from app.core.logging import emit_fatal
from app.server import main

if __name__ == "__main__":
    command = sys.argv[1] if len(sys.argv) > 1 else "api"
    if command != "api":
        # One JSON line on stdout, not plain stderr: without it this is the one line of the process
        # that the "every line is JSON" check and a CloudWatch JSON query cannot parse.
        emit_fatal(
            "unknown command; the only Phase 1 command is 'api'",
            SystemClock().now,
            command=command[:64],
        )
        sys.exit(64)  # EX_USAGE: distinct from a crash (1) and a bad configuration (78)
    sys.exit(main())

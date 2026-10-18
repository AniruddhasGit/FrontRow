"""S-XCT-31 (PRD P-XCT-17, S7.10): drain on SIGTERM. Phase 1's share.

The drain itself - SIGTERM mid-request, the request completes 200, exit 0 - is
tests/test_shutdown.py::test_sigterm_drains_an_in_flight_request_and_exits_zero. The Redis hold
registry, the compare-and-delete release and the worker's drain are Phase 4 and Phase 5.
"""

from __future__ import annotations

from ._support import rg


def test_the_deployment_spec_states_the_stop_timeout_ordering_and_the_sigkill_consequence():
    hits = rg("the ECS stop timeout must exceed the deregistration delay plus SHUTDOWN_DRAIN_TIMEOUT_SECONDS", "docs/30 Deployment", fixed=True)
    assert hits
    files = {h[0] for h in hits}
    assert any(rg("SIGKILL arriving during the drain skips the release", f, fixed=True) for f in files)

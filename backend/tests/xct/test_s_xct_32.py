"""S-XCT-32 (PRD P-XCT-18): stateless containers. Phase 1's share that a test process can hold.

The read-only root filesystem, `docker diff` and non-root uid clauses are container-level and were
run against the built images (recorded in the lane report). Poster upload (Phase 6), the guest
selection round trip (Phase 3), the rate-limit buckets and hold registry (Phases 4 and 7) and
SIGKILL mid-confirm (Phase 4) do not exist yet.
"""

from __future__ import annotations

from ._support import rg
from .test_s_xct_29 import _boot, _boot_env


def test_a_container_asked_to_bind_port_80_exits_nonzero_at_boot(tmp_path):
    proc = _boot(_boot_env(API_PORT="80"), tmp_path)
    assert proc.returncode != 0
    assert "API_PORT" in proc.stdout


def test_the_deployment_spec_names_api_port():
    assert rg("API_PORT", "docs/30 Deployment", fixed=True)

"""S-XCT-36 (PRD P-XCT-22): no scheduled job of any kind. The clauses Phase 1 can be held to.

Not here, because the code does not exist yet: the compose service list (no worker or ElasticMQ
service until Phase 5), hold expiry against real Redis (Phase 4), the outbox relay and the seat_locks
SCAN (Phase 5), and the seat-map cache TTL (Phase 3).
"""

from __future__ import annotations

from ._support import rg


def test_scheduler_words_appear_only_on_lines_saying_there_is_none():
    hits = rg(r"cron|apscheduler|celery|schedule\(|eventbridge|BackgroundScheduler|repeat_every", "backend/app", "backend/migrations", "frontend/src", "docker-compose.yml", ignore_case=True)
    assert [h for h in hits if "no scheduled job" not in h[2]] == []


def test_idempotency_records_are_never_expired():
    assert rg(r"DELETE FROM idempotency|EXPIRE idempotency", "backend/app", "backend/migrations", ignore_case=True) == []

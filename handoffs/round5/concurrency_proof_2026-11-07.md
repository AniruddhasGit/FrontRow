# Concurrency proof, local docker compose, merged main, 2026-11-07 night run (operator claude-night-run-2026-11-07)

## Stage A: 50 simultaneous holds on one seat
```json
{"operator": "claude-night-run-2026-11-07", "run_at": "2026-11-06T21:11:48.635Z", "stage": "A", "base_url": "http://api:8000", "showtime_id": 409, "seat_id": 90, "n": 50, "winners": 1, "losers": 49, "loser_unavailable_seats": ["[\"H6\"]"], "other_statuses": [], "spread_ms": 12.0, "spread_limit_ms": 100, "distinct_users": 50, "warmup_elapsed_seconds": 601.3, "limiter_enabled": null, "winner_confirm_status": 201, "unique_constraint_violations": 0, "booking_seat_rows": 1, "problems": []}
```

## Stage B with the unique constraint present (Redis lock bypassed): one 201, one 409
```json
{"operator": "claude-night-run-2026-11-07", "run_at": "2026-11-06T21:12:38.511Z", "stage": "B", "base_url": "http://127.0.0.1:8000", "hold_b_status": 201, "constraint_present": true, "constraints": [["uq_booking_seat__showtime_id_seat_id", "UNIQUE (showtime_id, seat_id)"]], "confirms_201": 1, "confirms_409_seat_unavailable": 1, "confirm_statuses": [201, 409], "booking_seat_rows": 1, "limiter_enabled": true}
```

## Stage B with the constraint DROPPED on purpose: two winners, two rows (the seat sold twice)
```json
{"operator": "claude-night-run-2026-11-07", "run_at": "2026-11-06T21:13:07.102Z", "stage": "B", "base_url": "http://127.0.0.1:8000", "hold_b_status": 201, "constraint_present": false, "constraints": [], "confirms_201": 2, "confirms_409_seat_unavailable": 0, "confirm_statuses": [201, 201], "booking_seat_rows": 2, "limiter_enabled": true}
```

## Restore: the duplicate test booking removed, constraint re-added, verified
```
uq_booking_seat__showtime_id_seat_id UNIQUE (showtime_id, seat_id)
rows for showtime 720 seat 959: 1
```

## Stage A again on the FINAL code (after every merge, a952500), 2026-11-07
```json
{"operator": "claude-night-run-2026-11-07-final", "run_at": "2026-11-06T22:42:57.146Z", "stage": "A", "base_url": "http://127.0.0.1:8000", "showtime_id": 409, "seat_id": 37, "n": 50, "winners": 1, "losers": 49, "loser_unavailable_seats": ["[\"D2\"]"], "other_statuses": [], "spread_ms": 13.7, "spread_limit_ms": 100, "distinct_users": 50, "warmup_elapsed_seconds": 601.2, "limiter_enabled": null, "winner_confirm_status": 201, "unique_constraint_violations": 0, "booking_seat_rows": 1, "problems": []}
```

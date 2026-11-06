"""The restore rehearsal's read-back (P-XCT-20, S-XCT-34; docs/30 Deployment/P7_BACKUP_RESTORE.md).

Run it AFTER restoring a backup to a NEW instance, with DATABASE_URL pointed at that instance and nothing else changed:

    RESTORE_OPERATOR=<your name> DATABASE_URL=postgresql://frontrow_app:...@<new endpoint>:5432/frontrow \
        python scripts/restore_rehearsal.py

It reads the known booking K7M2QX9C back with the specification's own SELECT and prints ONE JSON line - operator,
run_at, restored_instance and the three values read - because an undated claim that a restore was rehearsed is not
evidence. It exits 0 only when the booking is present and correct: FR-K7M2-QX9C, seats C12 and C13, both Premium at
28124 paise, 56248 in total. RESTORE_OPERATOR has no default: a run that cannot say who ran it exits 78 naming it.

It writes nothing. It never prints the password from DATABASE_URL: restored_instance is host:port/dbname only.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from urllib.parse import urlsplit

REFERENCE = "K7M2QX9C"
EXPECTED = {"reference": "FR-K7M2-QX9C", "seats": [["C12", "Premium", 28124], ["C13", "Premium", 28124]], "total_paise": 56248}
READ_BACK = ("SELECT b.reference, s.row_label, s.seat_number, bs.price_paise, sc.name "
             "FROM booking b JOIN booking_seat bs ON bs.booking_id = b.id JOIN seat s ON s.id = bs.seat_id "
             "JOIN seat_category sc ON sc.id = bs.seat_category_id "
             "WHERE b.reference = %s ORDER BY s.row_label, s.seat_number")


def _line(**fields) -> None:
    print(json.dumps(fields, separators=(",", ":")), flush=True)


def main() -> int:
    operator = os.environ.get("RESTORE_OPERATOR", "").strip()
    url = os.environ.get("DATABASE_URL", "").strip()
    missing = [name for name, value in (("RESTORE_OPERATOR", operator), ("DATABASE_URL", url)) if not value]
    if missing:
        message = f"refusing to run: {', '.join(missing)} is required and has no default"
        print(message, file=sys.stderr)
        _line(level="CRITICAL", message=message, missing=missing)
        return 78
    import psycopg

    parts = urlsplit(url)
    instance = f"{parts.hostname}:{parts.port or 5432}{parts.path}"
    with psycopg.connect(url) as conn:
        rows = conn.execute(READ_BACK, (REFERENCE,)).fetchall()
    ref = rows[0][0] if rows else None
    found = {"reference": f"FR-{ref[:4]}-{ref[4:]}" if ref else None,
             "seats": [[f"{r[1]}{r[2]}", r[4], r[3]] for r in rows],
             "total_paise": sum(r[3] for r in rows)}
    ok = found == EXPECTED
    _line(operator=operator, run_at=datetime.now(timezone.utc).isoformat(timespec="seconds"), restored_instance=instance,
          outcome="pass" if ok else "fail", **found)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

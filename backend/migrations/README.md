# backend/migrations/

Alembic migrations live here from **Phase 2** (`SRC-002 §12`). Phase 1 has no data model, so this
folder holds nothing else yet.

They run only through the entrypoint's separate `migrate` command, as a one-off task before the
service is updated. **Never on boot** (`SRC-002 §7.8`).

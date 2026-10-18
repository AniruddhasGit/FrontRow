# backend/

FastAPI on Python 3.12, PostgreSQL through SQLAlchemy Core + psycopg 3, Alembic for migrations.
The host Python is not used: everything runs in containers.

## Run the tests — the one command

```sh
docker compose --profile test run --rm --build test
```

Run it from the repository root. Pass a path or `-k` to narrow it, for example
`docker compose --profile test run --rm test python -m pytest tests/xct/test_s_xct_10.py`
(`--build` is only needed after a change to `requirements*.txt` or the `Dockerfile`; source is
mounted read-only, so code edits are picked up without a rebuild). On Git Bash for Windows, prefix
the command with `MSYS_NO_PATHCONV=1` or Git Bash rewrites the container paths.

What it does:

- builds the `test` stage of `backend/Dockerfile` (same interpreter, OS and wheels as production, plus
  pytest and `psql`);
- starts the compose `postgres` and `redis` if they are not running;
- for **each test module that asks for `migrated_db`**, creates a throwaway database `fr_test_<random>`,
  runs `docs/06 DataModel/checks/roles_local.sql` on it verbatim, applies the real `migrate` command of
  `entrypoint.sh` as `frontrow_owner`, hands the test three URLs (admin, owner, app), and drops the
  database afterwards. The `frontrow` database is never touched.

Database fixtures and helpers for every lane are in `tests/dbkit.py` (`migrated_db`, `app_settings`,
`owner_sql`, `app_sql`, `insert_user`, `insert_showtime`, `insert_booking`). They **fail, never skip**,
when the environment is missing.

## Migrate

```sh
docker compose --profile tools run --rm migrate
```

A separate, explicit step — **never on boot** (`SRC-002 §7.8`). It connects as `frontrow_owner`; the
API connects as `frontrow_app`. See `migrations/README.md`.

## Where things go

| Path | Holds |
|---|---|
| `app/api/<router>.py` | one router per authorisation rule; the rule is the router's dependency (`app/api/deps.py`) |
| `app/api/admin/<feature>.py` | admin routes: `router = APIRouter()` with no prefix and no dependency — included automatically under `/api/admin` with `require_admin` |
| `app/api/errors.py` | the one error envelope; raise `ApiError(status, code, message=None, details=None)` |
| `app/core/audit.py` | `check_action()` before the transaction, `write_audit()` inside it |
| `app/core/security.py` | password rules, bcrypt (sync — call it in a thread), the session JWT and cookie |
| `app/domain/pricing.py` | `seat_price_paise()` — the only seat-price formula |
| `app/domain/money.py` | `Paise` / `PositivePaise` — strict integer-paise request fields |
| `app/models/` | Core `Table` mirror of `docs/06 DataModel/schema.sql` (the schema wins on any difference) |
| `app/db/` | the async engine; a request gets one connection through `Depends(db)` |

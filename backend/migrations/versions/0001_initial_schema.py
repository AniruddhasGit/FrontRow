"""The whole Phase 2 data model, as docs/06 DataModel/schema.sql defines it.

Revision ID: 0001
Revises: (none - the first revision)

WHERE THIS COMES FROM. The SQL below is docs/06 DataModel/schema.sql (generated from datamodel.json,
the spec of record) with three mechanical changes and nothing else:
  1. its `--` comments are removed (they are documentation, not objects; the file of record keeps them);
  2. its BEGIN; / COMMIT; are removed, because Alembic already runs this revision in one transaction;
  3. CREATE TABLE booking_seat is written as op.create_table below instead of as SQL, so the
     seat-occupancy table and its UNIQUE (showtime_id, seat_id) visibly carry the SAME revision id
     (S-XCT-04): no earlier revision can have written a seat row without the guard in place.
backend/tests/xct/test_s_xct_04.py proves the migrated catalog equals
the catalog schema.sql produces - columns, constraints, indexes and grants - so a drift in either
direction fails a test. If datamodel.json changes, a NEW revision is written; this one is never edited.

WHO RUNS IT. The entrypoint's `migrate` command only, as frontrow_owner, before the service is updated.
Never on boot (SRC-002 §7.8). The roles must exist first (docs/06 DataModel/checks/roles_local.sql
locally; the client on RDS) - the GRANTs at the end fail and the whole revision rolls back otherwise.
"""

# LOCK: creates 22 new, EMPTY tables and their indexes, and grants on them. Every lock taken is on an
# object this revision itself creates, held for the milliseconds the transaction takes; no existing
# table is touched, so nothing that serves traffic is blocked. audit_log and booking_seat are among
# the created tables - they are empty at this point, which is the only reason this is cheap.

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

# Every table schema.sql creates up to (not including) booking_seat, in its own order.
_BEFORE_BOOKING_SEAT = """
CREATE TABLE certification (
    id                         bigint GENERATED ALWAYS AS IDENTITY NOT NULL,
    name                       text NOT NULL,
    is_active                  boolean NOT NULL,
    created_at                 timestamptz NOT NULL DEFAULT now(),
    updated_at                 timestamptz DEFAULT now(),
    PRIMARY KEY (id),
    CONSTRAINT ck_certification__1 CHECK (char_length(btrim(name)) BETWEEN 1 AND 60)
);
CREATE UNIQUE INDEX uq_certification__name_ci ON certification ((lower(trim(name))));
CREATE TABLE cinema (
    id                         bigint GENERATED ALWAYS AS IDENTITY NOT NULL,
    name                       text NOT NULL,
    timezone                   text NOT NULL,
    version                    integer NOT NULL,
    created_at                 timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (id)
);
CREATE UNIQUE INDEX uq_cinema__name_ci ON cinema ((lower(trim(name))));
CREATE TABLE format (
    id                         bigint GENERATED ALWAYS AS IDENTITY NOT NULL,
    name                       text NOT NULL,
    is_active                  boolean NOT NULL,
    created_at                 timestamptz NOT NULL DEFAULT now(),
    updated_at                 timestamptz DEFAULT now(),
    PRIMARY KEY (id),
    CONSTRAINT ck_format__1 CHECK (char_length(btrim(name)) BETWEEN 1 AND 60)
);
CREATE UNIQUE INDEX uq_format__name_ci ON format ((lower(trim(name))));
CREATE TABLE genre (
    id                         bigint GENERATED ALWAYS AS IDENTITY NOT NULL,
    name                       text NOT NULL,
    is_active                  boolean NOT NULL,
    created_at                 timestamptz NOT NULL DEFAULT now(),
    updated_at                 timestamptz DEFAULT now(),
    PRIMARY KEY (id),
    CONSTRAINT ck_genre__1 CHECK (char_length(btrim(name)) BETWEEN 1 AND 60)
);
CREATE UNIQUE INDEX uq_genre__name_ci ON genre ((lower(trim(name))));
CREATE TABLE language (
    id                         bigint GENERATED ALWAYS AS IDENTITY NOT NULL,
    name                       text NOT NULL,
    is_active                  boolean NOT NULL,
    created_at                 timestamptz NOT NULL DEFAULT now(),
    updated_at                 timestamptz DEFAULT now(),
    PRIMARY KEY (id),
    CONSTRAINT ck_language__1 CHECK (char_length(btrim(name)) BETWEEN 1 AND 60)
);
CREATE UNIQUE INDEX uq_language__name_ci ON language ((lower(trim(name))));
CREATE TABLE outbox_message (
    id                         bigint GENERATED ALWAYS AS IDENTITY NOT NULL,
    created_at                 timestamptz NOT NULL DEFAULT now(),
    topic                      text NOT NULL,
    payload                    jsonb NOT NULL,
    status                     text NOT NULL,
    sent_at                    timestamptz,
    attempts                   integer NOT NULL,
    last_error                 text,
    PRIMARY KEY (id),
    CONSTRAINT ck_outbox_message__1 CHECK (topic IN ('receipt.send', 'password_reset.send')),
    CONSTRAINT ck_outbox_message__2 CHECK (status IN ('pending', 'sent')),
    CONSTRAINT ck_outbox_message__payload_keys_exact CHECK ((topic <> 'receipt.send' OR (payload ?& ARRAY['booking_id', 'dispatch_seq', 'message_version', 'request_id'] AND payload - 'booking_id' - 'dispatch_seq' - 'message_version' - 'request_id' = '{}'::jsonb)) AND (topic <> 'password_reset.send' OR (payload ?& ARRAY['message_version', 'request_id', 'reset_token_id', 'user_id'] AND payload - 'message_version' - 'request_id' - 'reset_token_id' - 'user_id' = '{}'::jsonb)))
);
CREATE INDEX ix_outbox_message__status_created_at ON outbox_message (status, created_at);
CREATE TABLE payment (
    id                         bigint GENERATED ALWAYS AS IDENTITY NOT NULL,
    state                      text NOT NULL,
    amount_paise               bigint NOT NULL,
    idempotency_key            text NOT NULL,
    pending_at                 timestamptz NOT NULL,
    authorized_at              timestamptz,
    captured_at                timestamptz,
    created_at                 timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (id),
    CONSTRAINT ck_payment__state CHECK (state IN ('pending', 'authorized', 'captured', 'failed'))
);
CREATE INDEX ix_payment__state ON payment (state);
CREATE TABLE seat_category (
    id                         bigint GENERATED ALWAYS AS IDENTITY NOT NULL,
    name                       text NOT NULL,
    uplift_basis_points        bigint NOT NULL,
    version                    integer NOT NULL,
    created_at                 timestamptz NOT NULL DEFAULT now(),
    updated_at                 timestamptz DEFAULT now(),
    PRIMARY KEY (id),
    CONSTRAINT ck_seat_category__1 CHECK (uplift_basis_points >= 0),
    CONSTRAINT ck_seat_category__2 CHECK (char_length(btrim(name)) BETWEEN 1 AND 40)
);
CREATE UNIQUE INDEX uq_seat_category__name_ci ON seat_category ((lower(trim(name))));
CREATE TABLE users (
    id                         bigint GENERATED ALWAYS AS IDENTITY NOT NULL,
    email                      text NOT NULL,
    password_hash              text NOT NULL,
    role                       text NOT NULL,
    password_version           integer NOT NULL,
    created_at                 timestamptz NOT NULL DEFAULT now(),
    last_signed_in_at          timestamptz,
    PRIMARY KEY (id),
    CONSTRAINT ck_users__role CHECK (role IN ('customer', 'manager', 'admin'))
);
CREATE UNIQUE INDEX uq_users__email_ci ON users ((lower(email)));
CREATE TABLE audit_log (
    id                         bigint GENERATED ALWAYS AS IDENTITY NOT NULL,
    occurred_at                timestamptz NOT NULL,
    actor_user_id              bigint NOT NULL,
    actor_role                 text NOT NULL,
    action                     text NOT NULL,
    entity_type                text NOT NULL,
    entity_id                  bigint NOT NULL,
    before                     jsonb,
    after                      jsonb,
    request_id                 text NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT fk_audit_log__actor_user_id FOREIGN KEY (actor_user_id) REFERENCES users (id) ON DELETE RESTRICT ON UPDATE RESTRICT
);
CREATE INDEX ix_audit_log__occurred_at ON audit_log (occurred_at);
CREATE TABLE movie (
    id                         bigint GENERATED ALWAYS AS IDENTITY NOT NULL,
    title                      text NOT NULL,
    synopsis                   text NOT NULL,
    runtime_minutes            integer NOT NULL,
    certification_id           bigint NOT NULL,
    language_id                bigint NOT NULL,
    poster_object_key          text,
    published_at               timestamptz,
    display_from               timestamptz,
    display_until              timestamptz,
    version                    integer NOT NULL,
    created_at                 timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (id),
    CONSTRAINT fk_movie__certification_id FOREIGN KEY (certification_id) REFERENCES certification (id) ON DELETE RESTRICT ON UPDATE RESTRICT,
    CONSTRAINT fk_movie__language_id FOREIGN KEY (language_id) REFERENCES language (id) ON DELETE RESTRICT ON UPDATE RESTRICT
);
CREATE TABLE password_reset_token (
    id                         bigint GENERATED ALWAYS AS IDENTITY NOT NULL,
    user_id                    bigint NOT NULL,
    token_sha256               text NOT NULL,
    expires_at                 timestamptz NOT NULL,
    used_at                    timestamptz,
    email_claimed_at           timestamptz,
    email_sent_at              timestamptz,
    created_at                 timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (id),
    CONSTRAINT fk_password_reset_token__user_id FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE RESTRICT ON UPDATE RESTRICT
);
CREATE INDEX ix_password_reset_token__token_sha256 ON password_reset_token (token_sha256);
CREATE INDEX ix_password_reset_token__user_id ON password_reset_token (user_id);
CREATE TABLE screen (
    id                         bigint GENERATED ALWAYS AS IDENTITY NOT NULL,
    cinema_id                  bigint NOT NULL,
    name                       text NOT NULL,
    is_active                  boolean NOT NULL DEFAULT true,
    version                    integer NOT NULL,
    created_at                 timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (id),
    CONSTRAINT fk_screen__cinema_id FOREIGN KEY (cinema_id) REFERENCES cinema (id) ON DELETE RESTRICT ON UPDATE RESTRICT
);
CREATE UNIQUE INDEX uq_screen__name_ci ON screen (cinema_id, (lower(trim(name))));
CREATE TABLE manager_screen_assignment (
    id                         bigint GENERATED ALWAYS AS IDENTITY NOT NULL,
    user_id                    bigint NOT NULL,
    screen_id                  bigint NOT NULL,
    created_at                 timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (id),
    CONSTRAINT uq_manager_screen_assignment__user_id_screen_id UNIQUE (user_id, screen_id),
    CONSTRAINT fk_manager_screen_assignment__user_id FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE RESTRICT ON UPDATE RESTRICT,
    CONSTRAINT fk_manager_screen_assignment__screen_id FOREIGN KEY (screen_id) REFERENCES screen (id) ON DELETE RESTRICT ON UPDATE RESTRICT
);
CREATE INDEX ix_manager_screen_assignment__user_id ON manager_screen_assignment (user_id);
CREATE TABLE movie_genre (
    movie_id                   bigint NOT NULL,
    genre_id                   bigint NOT NULL,
    PRIMARY KEY (movie_id, genre_id),
    CONSTRAINT fk_movie_genre__movie_id FOREIGN KEY (movie_id) REFERENCES movie (id) ON DELETE RESTRICT ON UPDATE RESTRICT,
    CONSTRAINT fk_movie_genre__genre_id FOREIGN KEY (genre_id) REFERENCES genre (id) ON DELETE RESTRICT ON UPDATE RESTRICT
);
CREATE TABLE seat (
    id                         bigint GENERATED ALWAYS AS IDENTITY NOT NULL,
    screen_id                  bigint NOT NULL,
    row_label                  text NOT NULL,
    seat_number                integer NOT NULL,
    grid_row                   integer NOT NULL,
    grid_col                   integer NOT NULL,
    seat_category_id           bigint NOT NULL,
    is_active                  boolean NOT NULL DEFAULT true,
    created_at                 timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (id),
    CONSTRAINT uq_seat__screen_id_row_label_seat_number UNIQUE (screen_id, row_label, seat_number),
    CONSTRAINT uq_seat__screen_id_grid_row_grid_col UNIQUE (screen_id, grid_row, grid_col),
    CONSTRAINT ck_seat__row_label_upper CHECK (row_label = upper(btrim(row_label))),
    CONSTRAINT fk_seat__screen_id FOREIGN KEY (screen_id) REFERENCES screen (id) ON DELETE RESTRICT ON UPDATE RESTRICT,
    CONSTRAINT fk_seat__seat_category_id FOREIGN KEY (seat_category_id) REFERENCES seat_category (id) ON DELETE RESTRICT ON UPDATE RESTRICT
);
CREATE TABLE showtime (
    id                         bigint GENERATED ALWAYS AS IDENTITY NOT NULL,
    movie_id                   bigint NOT NULL,
    screen_id                  bigint NOT NULL,
    starts_at                  timestamptz NOT NULL,
    ends_at                    timestamptz NOT NULL,
    base_price_paise           bigint NOT NULL,
    format_id                  bigint,
    seat_count_at_creation     integer NOT NULL,
    version                    integer NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT fk_showtime__movie_id FOREIGN KEY (movie_id) REFERENCES movie (id) ON DELETE RESTRICT ON UPDATE RESTRICT,
    CONSTRAINT fk_showtime__screen_id FOREIGN KEY (screen_id) REFERENCES screen (id) ON DELETE RESTRICT ON UPDATE RESTRICT,
    CONSTRAINT fk_showtime__format_id FOREIGN KEY (format_id) REFERENCES format (id) ON DELETE RESTRICT ON UPDATE RESTRICT
);
CREATE INDEX ix_showtime__starts_at ON showtime (starts_at);
CREATE INDEX ix_showtime__screen_id_starts_at ON showtime (screen_id, starts_at);
CREATE TABLE booking (
    id                         bigint GENERATED ALWAYS AS IDENTITY NOT NULL,
    reference                  text NOT NULL,
    user_id                    bigint NOT NULL,
    showtime_id                bigint NOT NULL,
    payment_id                 bigint NOT NULL,
    total_paise                bigint NOT NULL,
    status                     text NOT NULL,
    cancelled_at               timestamptz,
    created_at                 timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (id),
    CONSTRAINT uq_booking__reference UNIQUE (reference),
    CONSTRAINT ck_booking__reference_charset CHECK (reference ~ '^[23456789ACDEFHJKMNPQRTVWXY]{8}$'),
    CONSTRAINT fk_booking__user_id FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE RESTRICT ON UPDATE RESTRICT,
    CONSTRAINT fk_booking__showtime_id FOREIGN KEY (showtime_id) REFERENCES showtime (id) ON DELETE RESTRICT ON UPDATE RESTRICT,
    CONSTRAINT fk_booking__payment_id FOREIGN KEY (payment_id) REFERENCES payment (id) ON DELETE RESTRICT ON UPDATE RESTRICT
);
CREATE INDEX ix_booking__showtime_id ON booking (showtime_id);
CREATE INDEX ix_booking__payment_id ON booking (payment_id);
CREATE TABLE showtime_seat (
    showtime_id                bigint NOT NULL,
    seat_id                    bigint NOT NULL,
    PRIMARY KEY (showtime_id, seat_id),
    CONSTRAINT uq_showtime_seat__showtime_id_seat_id UNIQUE (showtime_id, seat_id),
    CONSTRAINT fk_showtime_seat__showtime_id FOREIGN KEY (showtime_id) REFERENCES showtime (id) ON DELETE RESTRICT ON UPDATE RESTRICT,
    CONSTRAINT fk_showtime_seat__seat_id FOREIGN KEY (seat_id) REFERENCES seat (id) ON DELETE RESTRICT ON UPDATE RESTRICT
);
"""

# booking_seat's index, the remaining tables, and the least-privilege grants to frontrow_app.
_AFTER_BOOKING_SEAT = """
CREATE INDEX ix_booking_seat__booking_id ON booking_seat (booking_id);
CREATE TABLE idempotency_record (
    id                         bigint GENERATED ALWAYS AS IDENTITY NOT NULL,
    user_id                    bigint NOT NULL,
    idempotency_key            text NOT NULL,
    request_fingerprint        text NOT NULL,
    status                     text NOT NULL,
    booking_id                 bigint,
    response_body              jsonb,
    created_at                 timestamptz NOT NULL DEFAULT now(),
    completed_at               timestamptz,
    PRIMARY KEY (id),
    CONSTRAINT uq_idempotency_record__user_id_idempotency_key UNIQUE (user_id, idempotency_key),
    CONSTRAINT ck_idempotency_record__status CHECK (status IN ('in_progress', 'completed')),
    CONSTRAINT fk_idempotency_record__user_id FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE RESTRICT ON UPDATE RESTRICT,
    CONSTRAINT fk_idempotency_record__booking_id FOREIGN KEY (booking_id) REFERENCES booking (id) ON DELETE RESTRICT ON UPDATE RESTRICT
);
CREATE TABLE receipt_dispatch (
    id                         bigint GENERATED ALWAYS AS IDENTITY NOT NULL,
    booking_id                 bigint NOT NULL,
    status                     text NOT NULL,
    dispatch_seq               integer NOT NULL,
    claimed_at                 timestamptz,
    sent_at                    timestamptz,
    ses_message_id             text,
    attempts                   integer NOT NULL,
    last_error                 text,
    PRIMARY KEY (id),
    CONSTRAINT uq_receipt_dispatch__booking_id UNIQUE (booking_id),
    CONSTRAINT ck_receipt_dispatch__1 CHECK (status IN ('pending', 'sending', 'sent', 'failed', 'suppressed')),
    CONSTRAINT ck_receipt_dispatch__2 CHECK (dispatch_seq >= 1),
    CONSTRAINT fk_receipt_dispatch__booking_id FOREIGN KEY (booking_id) REFERENCES booking (id) ON DELETE RESTRICT ON UPDATE RESTRICT
);
GRANT USAGE ON SCHEMA public TO frontrow_app;
GRANT SELECT, INSERT ON audit_log TO frontrow_app;
GRANT SELECT, INSERT ON booking TO frontrow_app;
GRANT SELECT, INSERT ON booking_seat TO frontrow_app;
GRANT SELECT, INSERT, UPDATE ON certification TO frontrow_app;
GRANT SELECT, INSERT, UPDATE ON cinema TO frontrow_app;
GRANT SELECT, INSERT, UPDATE ON format TO frontrow_app;
GRANT SELECT, INSERT, UPDATE ON genre TO frontrow_app;
GRANT SELECT, INSERT, UPDATE ON idempotency_record TO frontrow_app;
GRANT SELECT, INSERT, UPDATE ON language TO frontrow_app;
GRANT SELECT, INSERT, DELETE ON manager_screen_assignment TO frontrow_app;
GRANT SELECT, INSERT, UPDATE ON movie TO frontrow_app;
GRANT SELECT, INSERT, DELETE ON movie_genre TO frontrow_app;
GRANT SELECT, INSERT, UPDATE ON outbox_message TO frontrow_app;
GRANT SELECT, INSERT, UPDATE ON password_reset_token TO frontrow_app;
GRANT SELECT, INSERT, UPDATE ON payment TO frontrow_app;
GRANT SELECT, INSERT, UPDATE ON receipt_dispatch TO frontrow_app;
GRANT SELECT, INSERT, UPDATE ON screen TO frontrow_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON seat TO frontrow_app;
GRANT SELECT, INSERT, UPDATE ON seat_category TO frontrow_app;
GRANT SELECT, INSERT, UPDATE ON showtime TO frontrow_app;
GRANT SELECT, INSERT ON showtime_seat TO frontrow_app;
GRANT SELECT, INSERT, UPDATE ON users TO frontrow_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO frontrow_app;
"""


def _run(sql: str) -> None:
    # Straight to the psycopg connection, inside Alembic's transaction: the simple-query protocol runs
    # many statements in one call, and nothing parses `:name` or `%` in the text as a bind parameter.
    op.get_bind().connection.driver_connection.execute(sql)


def upgrade() -> None:
    _run(_BEFORE_BOOKING_SEAT)
    # The seat-occupancy table and THE oversell guard, in one statement (S-XCT-04, P-XCT-01).
    # The UNIQUE is TOTAL: never add a WHERE (AGENT_CONTRACT rule 2 - a partial guard frees the pair
    # for every excluded row and is an oversell by design).
    op.create_table('booking_seat',
        sa.Column("id", sa.BigInteger, sa.Identity(always=True), nullable=False),
        sa.Column("booking_id", sa.BigInteger, nullable=False),
        sa.Column("showtime_id", sa.BigInteger, nullable=False),
        sa.Column("seat_id", sa.BigInteger, nullable=False),
        sa.Column("price_paise", sa.BigInteger, nullable=False),
        sa.Column("base_price_paise_applied", sa.BigInteger, nullable=False),
        sa.Column("uplift_basis_points_applied", sa.BigInteger, nullable=False),
        sa.Column("seat_category_id", sa.BigInteger, nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="booking_seat_pkey"),
        sa.UniqueConstraint('showtime_id', 'seat_id', name="uq_booking_seat__showtime_id_seat_id"),
        sa.ForeignKeyConstraint(["booking_id"], ["booking.id"], name="fk_booking_seat__booking_id", ondelete="RESTRICT", onupdate="RESTRICT"),
        sa.ForeignKeyConstraint(["seat_id"], ["seat.id"], name="fk_booking_seat__seat_id", ondelete="RESTRICT", onupdate="RESTRICT"),
        sa.ForeignKeyConstraint(["showtime_id"], ["showtime.id"], name="fk_booking_seat__showtime_id", ondelete="RESTRICT", onupdate="RESTRICT"),
        sa.ForeignKeyConstraint(["seat_category_id"], ["seat_category.id"], name="fk_booking_seat__seat_category_id", ondelete="RESTRICT", onupdate="RESTRICT"),
    )
    _run(_AFTER_BOOKING_SEAT)


def downgrade() -> None:
    raise NotImplementedError("no down-migrations: a bad migration is corrected by a new forward one (P-XCT-19 exception 5)")

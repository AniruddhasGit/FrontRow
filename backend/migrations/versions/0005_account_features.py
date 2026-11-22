"""CR-008 T3-T8: the customer account - points, bookmarks, notifications, support messages, profile columns.

Revision ID: 0005
Revises: 0004

WHERE THIS COMES FROM. docs/06 DataModel/datamodel.json gained four tables (bookmark, reward_entry, notification,
support_message) and five users columns (display_name, phone, preferred_language_id, preferred_format_id,
points_balance); schema.sql was regenerated from it. The SQL below is those objects as schema.sql writes them, with
the comments removed. backend/tests/xct/test_s_xct_04.py proves the migrated catalog equals the catalog schema.sql
produces.

ADD and CREATE only. Nothing is dropped or narrowed, so the code running before this revision keeps working during
the deploy (it never names a new column, and points_balance defaults to 0 for every existing account).
frontrow_app gets no DELETE on any new table: an un-bookmark sets saved = false (CR-008 T4).
"""

# LOCK: ALTER TABLE users takes an ACCESS EXCLUSIVE lock on users for the milliseconds the statement takes: the five
# columns are nullable or carry a constant default (PostgreSQL 11+ rewrites no row), and the CHECKs and foreign keys
# validate against the existing rows (all NULL or 0) in one scan. Sign-ins and bookings wait that long. The four
# CREATE TABLEs make new, empty tables; their foreign keys take SHARE ROW EXCLUSIVE on users, movie and booking briefly.

from __future__ import annotations

from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
ALTER TABLE users
    ADD COLUMN display_name text,
    ADD COLUMN phone text,
    ADD COLUMN preferred_language_id bigint,
    ADD COLUMN preferred_format_id bigint,
    ADD COLUMN points_balance bigint NOT NULL DEFAULT 0,
    ADD CONSTRAINT ck_users__display_name CHECK (display_name IS NULL OR char_length(btrim(display_name)) BETWEEN 1 AND 60),
    ADD CONSTRAINT ck_users__phone CHECK (phone IS NULL OR phone ~ '^[+]?[0-9]{7,15}$'),
    ADD CONSTRAINT ck_users__points_balance CHECK (points_balance >= 0),
    ADD CONSTRAINT fk_users__preferred_language_id FOREIGN KEY (preferred_language_id) REFERENCES language (id) ON DELETE RESTRICT ON UPDATE RESTRICT,
    ADD CONSTRAINT fk_users__preferred_format_id FOREIGN KEY (preferred_format_id) REFERENCES format (id) ON DELETE RESTRICT ON UPDATE RESTRICT;
CREATE TABLE bookmark (
    id                         bigint GENERATED ALWAYS AS IDENTITY NOT NULL,
    user_id                    bigint NOT NULL,
    movie_id                   bigint NOT NULL,
    saved                      boolean NOT NULL,
    created_at                 timestamptz NOT NULL DEFAULT now(),
    updated_at                 timestamptz DEFAULT now(),
    PRIMARY KEY (id),
    CONSTRAINT uq_bookmark__user_id_movie_id UNIQUE (user_id, movie_id),
    CONSTRAINT fk_bookmark__user_id FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE RESTRICT ON UPDATE RESTRICT,
    CONSTRAINT fk_bookmark__movie_id FOREIGN KEY (movie_id) REFERENCES movie (id) ON DELETE RESTRICT ON UPDATE RESTRICT
);
CREATE TABLE reward_entry (
    id                         bigint GENERATED ALWAYS AS IDENTITY NOT NULL,
    user_id                    bigint NOT NULL,
    booking_id                 bigint NOT NULL,
    kind                       text NOT NULL,
    points                     bigint NOT NULL,
    discount_paise             bigint,
    created_at                 timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (id),
    CONSTRAINT uq_reward_entry__booking_id_kind UNIQUE (booking_id, kind),
    CONSTRAINT ck_reward_entry__kind CHECK (kind IN ('earned', 'redeemed')),
    CONSTRAINT ck_reward_entry__points CHECK (points > 0),
    CONSTRAINT ck_reward_entry__discount CHECK ((kind = 'redeemed') = (discount_paise IS NOT NULL AND discount_paise > 0)),
    CONSTRAINT fk_reward_entry__user_id FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE RESTRICT ON UPDATE RESTRICT,
    CONSTRAINT fk_reward_entry__booking_id FOREIGN KEY (booking_id) REFERENCES booking (id) ON DELETE RESTRICT ON UPDATE RESTRICT
);
CREATE INDEX ix_reward_entry__user_id_id ON reward_entry (user_id, id);
CREATE TABLE notification (
    id                         bigint GENERATED ALWAYS AS IDENTITY NOT NULL,
    user_id                    bigint NOT NULL,
    booking_id                 bigint NOT NULL,
    kind                       text NOT NULL,
    title                      text NOT NULL,
    body                       text NOT NULL,
    read_at                    timestamptz,
    created_at                 timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (id),
    CONSTRAINT uq_notification__booking_id_kind UNIQUE (booking_id, kind),
    CONSTRAINT ck_notification__kind CHECK (kind IN ('booking_confirmed', 'points_earned', 'points_redeemed')),
    CONSTRAINT fk_notification__user_id FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE RESTRICT ON UPDATE RESTRICT,
    CONSTRAINT fk_notification__booking_id FOREIGN KEY (booking_id) REFERENCES booking (id) ON DELETE RESTRICT ON UPDATE RESTRICT
);
CREATE INDEX ix_notification__user_id_id ON notification (user_id, id);
CREATE TABLE support_message (
    id                         bigint GENERATED ALWAYS AS IDENTITY NOT NULL,
    user_id                    bigint,
    email                      text NOT NULL,
    topic                      text NOT NULL,
    message                    text NOT NULL,
    created_at                 timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (id),
    CONSTRAINT ck_support_message__topic CHECK (topic IN ('booking', 'payment', 'rewards', 'account', 'other')),
    CONSTRAINT ck_support_message__message CHECK (char_length(btrim(message)) BETWEEN 1 AND 2000),
    CONSTRAINT ck_support_message__email CHECK (char_length(btrim(email)) BETWEEN 3 AND 254),
    CONSTRAINT fk_support_message__user_id FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE RESTRICT ON UPDATE RESTRICT
);
GRANT SELECT, INSERT, UPDATE ON bookmark TO frontrow_app;
GRANT SELECT, INSERT, UPDATE ON notification TO frontrow_app;
GRANT SELECT, INSERT ON reward_entry TO frontrow_app;
GRANT SELECT, INSERT ON support_message TO frontrow_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO frontrow_app;
""")


def downgrade() -> None:
    raise NotImplementedError("no down-migrations: a bad migration is corrected by a new forward one (P-XCT-19 exception 5)")

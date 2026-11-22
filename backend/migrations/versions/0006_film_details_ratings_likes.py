"""CR-008 T12: full film details (release date, cast, crew) and the customers' ratings and likes.

Revision ID: 0006
Revises: 0005

WHERE THIS COMES FROM. docs/06 DataModel/datamodel.json gained three movie columns (release_date, cast_members,
crew_members) and two tables (movie_rating, movie_like); schema.sql was regenerated from it. The SQL below is those
objects as schema.sql writes them, with the comments removed. backend/tests/xct/test_s_xct_04.py proves the migrated
catalog equals the catalog schema.sql produces.

ADD and CREATE only. The three columns are nullable, so the code running before this revision keeps working during the
deploy (it never names them). frontrow_app gets no DELETE on either table: re-rating updates the row, un-liking sets
liked = false (CR-008 T12).
"""

# LOCK: ALTER TABLE movie takes an ACCESS EXCLUSIVE lock on movie for the milliseconds the statement takes: the three
# columns are nullable with no default (no row is rewritten) and the two CHECKs validate against all-NULL values in one
# scan. Listing reads wait that long. The two CREATE TABLEs make new, empty tables; their foreign keys take SHARE ROW
# EXCLUSIVE on users and movie briefly.

from __future__ import annotations

from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
ALTER TABLE movie
    ADD COLUMN release_date date,
    ADD COLUMN cast_members text,
    ADD COLUMN crew_members text,
    ADD CONSTRAINT ck_movie__cast_members CHECK (cast_members IS NULL OR char_length(cast_members) <= 4000),
    ADD CONSTRAINT ck_movie__crew_members CHECK (crew_members IS NULL OR char_length(crew_members) <= 4000);
CREATE TABLE movie_like (
    id                         bigint GENERATED ALWAYS AS IDENTITY NOT NULL,
    user_id                    bigint NOT NULL,
    movie_id                   bigint NOT NULL,
    liked                      boolean NOT NULL,
    created_at                 timestamptz NOT NULL DEFAULT now(),
    updated_at                 timestamptz DEFAULT now(),
    PRIMARY KEY (id),
    CONSTRAINT uq_movie_like__user_id_movie_id UNIQUE (user_id, movie_id),
    CONSTRAINT fk_movie_like__user_id FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE RESTRICT ON UPDATE RESTRICT,
    CONSTRAINT fk_movie_like__movie_id FOREIGN KEY (movie_id) REFERENCES movie (id) ON DELETE RESTRICT ON UPDATE RESTRICT
);
CREATE INDEX ix_movie_like__movie_id ON movie_like (movie_id);
CREATE TABLE movie_rating (
    id                         bigint GENERATED ALWAYS AS IDENTITY NOT NULL,
    user_id                    bigint NOT NULL,
    movie_id                   bigint NOT NULL,
    score                      integer NOT NULL,
    created_at                 timestamptz NOT NULL DEFAULT now(),
    updated_at                 timestamptz DEFAULT now(),
    PRIMARY KEY (id),
    CONSTRAINT uq_movie_rating__user_id_movie_id UNIQUE (user_id, movie_id),
    CONSTRAINT ck_movie_rating__score CHECK (score BETWEEN 1 AND 10),
    CONSTRAINT fk_movie_rating__user_id FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE RESTRICT ON UPDATE RESTRICT,
    CONSTRAINT fk_movie_rating__movie_id FOREIGN KEY (movie_id) REFERENCES movie (id) ON DELETE RESTRICT ON UPDATE RESTRICT
);
CREATE INDEX ix_movie_rating__movie_id ON movie_rating (movie_id);
GRANT SELECT, INSERT, UPDATE ON movie_like TO frontrow_app;
GRANT SELECT, INSERT, UPDATE ON movie_rating TO frontrow_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO frontrow_app;
""")


def downgrade() -> None:
    raise NotImplementedError("no down-migrations: a bad migration is corrected by a new forward one (P-XCT-19 exception 5)")

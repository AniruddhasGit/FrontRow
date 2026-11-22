"""CR-011 F4: reviews (a written review on the customer's rating) and one "Helpful" vote per customer per review.

Revision ID: 0007
Revises: 0006

WHERE THIS COMES FROM. docs/06 DataModel/datamodel.json gained movie_rating.review_text (with its CHECK) and the table
review_vote; schema.sql was regenerated from it. The SQL below is those objects as schema.sql writes them, with the
comments removed. backend/tests/xct/test_s_xct_04.py proves the migrated catalog equals the catalog schema.sql produces.

ADD and CREATE only. The column is nullable, so the code running before this revision keeps working during the deploy
(it never names it). frontrow_app gets SELECT and INSERT on review_vote only: a vote is cast once and never changed.
"""

# LOCK: ALTER TABLE movie_rating takes an ACCESS EXCLUSIVE lock on movie_rating for the milliseconds the statement
# takes: the column is nullable with no default (no row is rewritten) and the CHECK validates against all-NULL values in
# one scan. Rating writes wait that long. CREATE TABLE review_vote makes a new, empty table; its foreign keys take SHARE
# ROW EXCLUSIVE on movie_rating and users briefly.

from __future__ import annotations

from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
ALTER TABLE movie_rating
    ADD COLUMN review_text text,
    ADD CONSTRAINT ck_movie_rating__review_text CHECK (review_text IS NULL OR char_length(review_text) BETWEEN 1 AND 2000);
CREATE TABLE review_vote (
    id                         bigint GENERATED ALWAYS AS IDENTITY NOT NULL,
    rating_id                  bigint NOT NULL,
    user_id                    bigint NOT NULL,
    created_at                 timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (id),
    CONSTRAINT uq_review_vote__rating_id_user_id UNIQUE (rating_id, user_id),
    CONSTRAINT fk_review_vote__rating_id FOREIGN KEY (rating_id) REFERENCES movie_rating (id) ON DELETE RESTRICT ON UPDATE RESTRICT,
    CONSTRAINT fk_review_vote__user_id FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE RESTRICT ON UPDATE RESTRICT
);
CREATE INDEX ix_review_vote__user_id ON review_vote (user_id);
GRANT SELECT, INSERT ON review_vote TO frontrow_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO frontrow_app;
""")


def downgrade() -> None:
    raise NotImplementedError("no down-migrations: a bad migration is corrected by a new forward one (P-XCT-19 exception 5)")

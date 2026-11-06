"""SQLAlchemy Core mirror of the 23 tables in docs/06 DataModel/schema.sql. NOT the schema.

The ORM mirrors the schema; it never defines it (AGENT_CONTRACT rule 8). The database - built by the
migration from schema.sql - owns every constraint, default, index and grant; this module only names
columns and their types so queries can be written without string SQL. Nothing here is ever used to
CREATE anything (there is no metadata.create_all anywhere, and there must never be).

Drift is a test failure, not a code review: backend/tests/xct/test_s_xct_04.py compares every
table and column here (name, type, nullability) against the migrated database's catalog. If they
disagree, schema.sql wins and this file is the defect.

Server defaults (created_at = now(), ...) are deliberately not declared: a Core insert that omits a
column lets the database default apply, which is the only default allowed (FR-ADR-018).
"""

from __future__ import annotations

from sqlalchemy import TIMESTAMP, BigInteger, Boolean, Column, Identity, Integer, MetaData, Table, Text
from sqlalchemy.dialects.postgresql import JSONB

metadata = MetaData()


certification = Table(
    'certification',
    metadata,
    Column('id', BigInteger, Identity(always=True), primary_key=True, nullable=False),
    Column('name', Text, nullable=False),
    Column('is_active', Boolean, nullable=False),
    Column('created_at', TIMESTAMP(timezone=True), nullable=False),
    Column('updated_at', TIMESTAMP(timezone=True), nullable=True),
)


cinema = Table(
    'cinema',
    metadata,
    Column('id', BigInteger, Identity(always=True), primary_key=True, nullable=False),
    Column('name', Text, nullable=False),
    Column('timezone', Text, nullable=False),
    Column('version', Integer, nullable=False),
    Column('created_at', TIMESTAMP(timezone=True), nullable=False),
)


format = Table(
    'format',
    metadata,
    Column('id', BigInteger, Identity(always=True), primary_key=True, nullable=False),
    Column('name', Text, nullable=False),
    Column('is_active', Boolean, nullable=False),
    Column('created_at', TIMESTAMP(timezone=True), nullable=False),
    Column('updated_at', TIMESTAMP(timezone=True), nullable=True),
)


genre = Table(
    'genre',
    metadata,
    Column('id', BigInteger, Identity(always=True), primary_key=True, nullable=False),
    Column('name', Text, nullable=False),
    Column('is_active', Boolean, nullable=False),
    Column('created_at', TIMESTAMP(timezone=True), nullable=False),
    Column('updated_at', TIMESTAMP(timezone=True), nullable=True),
)


language = Table(
    'language',
    metadata,
    Column('id', BigInteger, Identity(always=True), primary_key=True, nullable=False),
    Column('name', Text, nullable=False),
    Column('is_active', Boolean, nullable=False),
    Column('created_at', TIMESTAMP(timezone=True), nullable=False),
    Column('updated_at', TIMESTAMP(timezone=True), nullable=True),
)


outbox_message = Table(
    'outbox_message',
    metadata,
    Column('id', BigInteger, Identity(always=True), primary_key=True, nullable=False),
    Column('created_at', TIMESTAMP(timezone=True), nullable=False),
    Column('topic', Text, nullable=False),
    Column('payload', JSONB, nullable=False),
    Column('status', Text, nullable=False),
    Column('sent_at', TIMESTAMP(timezone=True), nullable=True),
    Column('attempts', Integer, nullable=False),
    Column('last_error', Text, nullable=True),
)


payment = Table(
    'payment',
    metadata,
    Column('id', BigInteger, Identity(always=True), primary_key=True, nullable=False),
    Column('state', Text, nullable=False),
    Column('amount_paise', BigInteger, nullable=False),
    Column('idempotency_key', Text, nullable=False),
    Column('pending_at', TIMESTAMP(timezone=True), nullable=False),
    Column('authorized_at', TIMESTAMP(timezone=True), nullable=True),
    Column('captured_at', TIMESTAMP(timezone=True), nullable=True),
    Column('created_at', TIMESTAMP(timezone=True), nullable=False),
)


seat_category = Table(
    'seat_category',
    metadata,
    Column('id', BigInteger, Identity(always=True), primary_key=True, nullable=False),
    Column('name', Text, nullable=False),
    Column('uplift_basis_points', BigInteger, nullable=False),
    Column('version', Integer, nullable=False),
    Column('created_at', TIMESTAMP(timezone=True), nullable=False),
    Column('updated_at', TIMESTAMP(timezone=True), nullable=True),
)


users = Table(
    'users',
    metadata,
    Column('id', BigInteger, Identity(always=True), primary_key=True, nullable=False),
    Column('email', Text, nullable=False),
    Column('password_hash', Text, nullable=False),
    Column('role', Text, nullable=False),
    Column('password_version', Integer, nullable=False),
    Column('created_at', TIMESTAMP(timezone=True), nullable=False),
    Column('last_signed_in_at', TIMESTAMP(timezone=True), nullable=True),
)


admin_grant = Table(
    'admin_grant',
    metadata,
    Column('id', BigInteger, Identity(always=True), primary_key=True, nullable=False),
    Column('email', Text, nullable=False),
    Column('granted_by', BigInteger, nullable=False),
    Column('created_at', TIMESTAMP(timezone=True), nullable=False),
)


audit_log = Table(
    'audit_log',
    metadata,
    Column('id', BigInteger, Identity(always=True), primary_key=True, nullable=False),
    Column('occurred_at', TIMESTAMP(timezone=True), nullable=False),
    Column('actor_user_id', BigInteger, nullable=False),
    Column('actor_role', Text, nullable=False),
    Column('action', Text, nullable=False),
    Column('entity_type', Text, nullable=False),
    Column('entity_id', BigInteger, nullable=False),
    Column('before', JSONB, nullable=True),
    Column('after', JSONB, nullable=True),
    Column('request_id', Text, nullable=False),
)


movie = Table(
    'movie',
    metadata,
    Column('id', BigInteger, Identity(always=True), primary_key=True, nullable=False),
    Column('title', Text, nullable=False),
    Column('synopsis', Text, nullable=False),
    Column('runtime_minutes', Integer, nullable=False),
    Column('certification_id', BigInteger, nullable=False),
    Column('language_id', BigInteger, nullable=False),
    Column('poster_object_key', Text, nullable=True),
    Column('published_at', TIMESTAMP(timezone=True), nullable=True),
    Column('display_from', TIMESTAMP(timezone=True), nullable=True),
    Column('display_until', TIMESTAMP(timezone=True), nullable=True),
    Column('version', Integer, nullable=False),
    Column('created_at', TIMESTAMP(timezone=True), nullable=False),
)


password_reset_token = Table(
    'password_reset_token',
    metadata,
    Column('id', BigInteger, Identity(always=True), primary_key=True, nullable=False),
    Column('user_id', BigInteger, nullable=False),
    Column('token_sha256', Text, nullable=False),
    Column('expires_at', TIMESTAMP(timezone=True), nullable=False),
    Column('used_at', TIMESTAMP(timezone=True), nullable=True),
    Column('email_claimed_at', TIMESTAMP(timezone=True), nullable=True),
    Column('email_sent_at', TIMESTAMP(timezone=True), nullable=True),
    Column('created_at', TIMESTAMP(timezone=True), nullable=False),
)


screen = Table(
    'screen',
    metadata,
    Column('id', BigInteger, Identity(always=True), primary_key=True, nullable=False),
    Column('cinema_id', BigInteger, nullable=False),
    Column('name', Text, nullable=False),
    Column('is_active', Boolean, nullable=False),
    Column('version', Integer, nullable=False),
    Column('created_at', TIMESTAMP(timezone=True), nullable=False),
)


manager_screen_assignment = Table(
    'manager_screen_assignment',
    metadata,
    Column('id', BigInteger, Identity(always=True), primary_key=True, nullable=False),
    Column('user_id', BigInteger, nullable=False),
    Column('screen_id', BigInteger, nullable=False),
    Column('created_at', TIMESTAMP(timezone=True), nullable=False),
)


movie_genre = Table(
    'movie_genre',
    metadata,
    Column('movie_id', BigInteger, primary_key=True, nullable=False),
    Column('genre_id', BigInteger, primary_key=True, nullable=False),
    Column('created_at', TIMESTAMP(timezone=True), nullable=False),
)


seat = Table(
    'seat',
    metadata,
    Column('id', BigInteger, Identity(always=True), primary_key=True, nullable=False),
    Column('screen_id', BigInteger, nullable=False),
    Column('row_label', Text, nullable=False),
    Column('seat_number', Integer, nullable=False),
    Column('grid_row', Integer, nullable=False),
    Column('grid_col', Integer, nullable=False),
    Column('seat_category_id', BigInteger, nullable=False),
    Column('is_active', Boolean, nullable=False),
    Column('created_at', TIMESTAMP(timezone=True), nullable=False),
)


showtime = Table(
    'showtime',
    metadata,
    Column('id', BigInteger, Identity(always=True), primary_key=True, nullable=False),
    Column('movie_id', BigInteger, nullable=False),
    Column('screen_id', BigInteger, nullable=False),
    Column('starts_at', TIMESTAMP(timezone=True), nullable=False),
    Column('ends_at', TIMESTAMP(timezone=True), nullable=False),
    Column('base_price_paise', BigInteger, nullable=False),
    Column('format_id', BigInteger, nullable=True),
    Column('seat_count_at_creation', Integer, nullable=False),
    Column('version', Integer, nullable=False),
    Column('created_at', TIMESTAMP(timezone=True), nullable=False),
)


booking = Table(
    'booking',
    metadata,
    Column('id', BigInteger, Identity(always=True), primary_key=True, nullable=False),
    Column('reference', Text, nullable=False),
    Column('user_id', BigInteger, nullable=False),
    Column('showtime_id', BigInteger, nullable=False),
    Column('payment_id', BigInteger, nullable=False),
    Column('total_paise', BigInteger, nullable=False),
    Column('status', Text, nullable=False),
    Column('cancelled_at', TIMESTAMP(timezone=True), nullable=True),
    Column('created_at', TIMESTAMP(timezone=True), nullable=False),
)


showtime_seat = Table(
    'showtime_seat',
    metadata,
    Column('showtime_id', BigInteger, primary_key=True, nullable=False),
    Column('seat_id', BigInteger, primary_key=True, nullable=False),
    Column('created_at', TIMESTAMP(timezone=True), nullable=False),
)


booking_seat = Table(
    'booking_seat',
    metadata,
    Column('id', BigInteger, Identity(always=True), primary_key=True, nullable=False),
    Column('booking_id', BigInteger, nullable=False),
    Column('showtime_id', BigInteger, nullable=False),
    Column('seat_id', BigInteger, nullable=False),
    Column('price_paise', BigInteger, nullable=False),
    Column('base_price_paise_applied', BigInteger, nullable=False),
    Column('uplift_basis_points_applied', BigInteger, nullable=False),
    Column('seat_category_id', BigInteger, nullable=False),
    Column('created_at', TIMESTAMP(timezone=True), nullable=False),
)


idempotency_record = Table(
    'idempotency_record',
    metadata,
    Column('id', BigInteger, Identity(always=True), primary_key=True, nullable=False),
    Column('user_id', BigInteger, nullable=False),
    Column('idempotency_key', Text, nullable=False),
    Column('request_fingerprint', Text, nullable=False),
    Column('status', Text, nullable=False),
    Column('booking_id', BigInteger, nullable=True),
    Column('response_body', JSONB, nullable=True),
    Column('created_at', TIMESTAMP(timezone=True), nullable=False),
    Column('completed_at', TIMESTAMP(timezone=True), nullable=True),
)


receipt_dispatch = Table(
    'receipt_dispatch',
    metadata,
    Column('id', BigInteger, Identity(always=True), primary_key=True, nullable=False),
    Column('booking_id', BigInteger, nullable=False),
    Column('status', Text, nullable=False),
    Column('dispatch_seq', Integer, nullable=False),
    Column('claimed_at', TIMESTAMP(timezone=True), nullable=True),
    Column('sent_at', TIMESTAMP(timezone=True), nullable=True),
    Column('ses_message_id', Text, nullable=True),
    Column('attempts', Integer, nullable=False),
    Column('last_error', Text, nullable=True),
    Column('created_at', TIMESTAMP(timezone=True), nullable=False),
)

"""THE customer-visibility predicate (P-ADM-05, FR-ADR-021, P-BRW-01) - the one copy in the product: published, AND
now >= display_from, AND now < display_until. The functions below ARE the formula; it is not restated in prose.

Two gates, and they stay two: `published` and `in_window` are each one gate alone, so the admin editor reports them
separately (SCR-ADM-02's gate block, S-ADM-27 `published` / `window_open`). `t` is always the injected clock's
instant; a null on either window side fails the comparison, so there is no COALESCE and no special case.
Every caller imports from here: a second copy that misses one clause shows an unpublished film to customers.
A booking, a receipt and the account surface read the movie row directly and never through this (P-ADM-06).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import and_

from app.models import movie


def in_window(t: datetime):
    """display_from inclusive, display_until exclusive (P-ADM-04)."""
    return and_(movie.c.display_from <= t, movie.c.display_until > t)


def published():
    """The publication gate alone. `.isnot` is SQLAlchemy's own spelling of IS NOT NULL (the operator `.is_not` names)."""
    return movie.c.published_at.isnot(None)


def visible(t: datetime):
    return and_(published(), in_window(t))

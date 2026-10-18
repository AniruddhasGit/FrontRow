"""The closed audit `action` vocabulary (P-ADM-19, FR-ADR-019).

Transcribed from P-ADM-19's table, the single source of these strings for the whole product. No
handler, test or screen may coin another: a value outside this tuple is refused with 500 before the
transaction opens (app/core/audit.py), because a free-text action makes every change-log filter
silently match nothing. Adding a member is a specification change to P-ADM-19 first, then here.
A base-price change is `showtime.base_price_changed`: the full name, never a shortened "price changed"
action and never the bare `base_price_changed` without its entity prefix.
"""

from __future__ import annotations

AUDIT_ACTIONS: tuple[str, ...] = (
    "movie.created",
    "movie.updated",
    "movie.poster_uploaded",
    "movie.poster_replaced",
    "movie.display_window_changed",
    "movie.published",
    "movie.unpublished",
    "showtime.created",
    "showtime.updated",
    "showtime.base_price_changed",
    "seat_category.created",
    "seat_category.updated",
    "seat_category.uplift_changed",
    "cinema.updated",
    "cinema.timezone_changed",
    "screen.created",
    "screen.updated",
    "screen.deactivated",
    "screen.reactivated",
    "seat.created",
    "seat.updated",
    "seat.deleted",
    "seat.deactivated",
    "seat.reactivated",
    "manager.created",
    "manager.screen_assigned",
    "manager.screen_unassigned",
    "language.created",
    "certification.created",
    "genre.created",
    "format.created",
    "language.withdrawn",
    "language.restored",
    "certification.withdrawn",
    "certification.restored",
    "genre.withdrawn",
    "genre.restored",
    "format.withdrawn",
    "format.restored",
)

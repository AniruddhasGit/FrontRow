"""The seat map (P-BRW-08, P-BRW-09, P-BRW-10, P-BRW-16, EP-BRW-06).

What it is: THIS SHOWTIME'S seat set (P-ADM-14 - fixed at creation, never the screen's current seats), ordered
gr ASC, gc ASC, each seat stamped with its category's already-rounded integer price, and three objective states:
sold if a booking_seat row exists for (showtime, seat), else held if a live lock:seat key exists, else available.
held_by_me is the client's - the response never varies by who reads it, which is what lets one cached entry
serve every viewer (FR-ADR-030, FR-ADR-045).

The response models are strict: a fourth state, a seat without is_active, or a price that is not a
non-negative integer fails HERE, at construction, before anything is serialised.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncConnection

from app.domain.browse.catalogue import local_iso
from app.domain.pricing import UPLIFT_COLUMN, seat_price_paise
from app.models import booking_seat, cinema, screen, seat, seat_category, showtime, showtime_seat

Paise = Annotated[int, Field(ge=0)]


class _Strict(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")


class Seat(_Strict):
    id: int
    row: str
    num: int
    gr: int
    gc: int
    cat: int
    price_paise: Paise
    state: Literal["available", "held", "sold"]
    # Required, never defaulted: an absent field a client reads as true makes a retired seat selectable.
    is_active: bool


class MapShowtime(_Strict):
    id: int
    starts_at: str
    sales_close_at: str
    sales_closed: bool


class MapScreen(_Strict):
    id: int
    name: str
    rows: int
    cols: int


class Category(_Strict):
    id: int
    name: str
    price_paise: Paise


class SeatMap(_Strict):
    showtime: MapShowtime
    screen: MapScreen
    categories: list[Category]
    seats: list[Seat]
    generated_at: str
    poll_interval_seconds: int


class SeatMapFault(Exception):
    """A seat map that cannot be drawn truthfully: an empty seat set, or one grid row with two labels. A fault,
    never an empty state (P-BRW-08 exception 2, P-BRW-16 exception 1)."""


async def load_seatmap(conn: AsyncConnection, showtime_id: int) -> tuple[dict, list] | None:
    """The showtime and its seat set from PostgreSQL, or None when no such showtime exists."""
    head = (await conn.execute(
        select(showtime.c.id, showtime.c.starts_at, showtime.c.base_price_paise, screen.c.id.label("screen_id"),
               screen.c.name.label("screen_name"), cinema.c.timezone)
        .select_from(showtime.join(screen, showtime.c.screen_id == screen.c.id).join(cinema, screen.c.cinema_id == cinema.c.id))
        .where(showtime.c.id == showtime_id))).mappings().first()
    if head is None:
        return None
    seats = (await conn.execute(
        select(seat.c.id, seat.c.row_label, seat.c.seat_number, seat.c.grid_row, seat.c.grid_col, seat.c.is_active,
               seat_category.c.id.label("category_id"), seat_category.c.name.label("category_name"),
               seat_category.c[UPLIFT_COLUMN].label("uplift"), booking_seat.c.id.label("booked"))
        .select_from(showtime_seat.join(seat, showtime_seat.c.seat_id == seat.c.id)
                     .join(seat_category, seat.c.seat_category_id == seat_category.c.id)
                     .outerjoin(booking_seat, and_(booking_seat.c.showtime_id == showtime_seat.c.showtime_id,
                                                   booking_seat.c.seat_id == showtime_seat.c.seat_id)))
        .where(showtime_seat.c.showtime_id == showtime_id)
        .order_by(seat.c.grid_row, seat.c.grid_col))).all()
    return dict(head), seats


def seat_state(booked: bool, held: bool) -> str:
    """THE precedence, written once (P-SEA-05): sold wins over any lock. A booking leaves its lock behind for up to
    the hold's TTL and a lock can be taken on a sold seat, so a seat with both is sold, never held."""
    return "sold" if booked else "held" if held else "available"


def assemble(head: dict, seats: list, held: set[int], now: datetime, cutoff: timedelta, poll_interval_seconds: int) -> SeatMap:
    if not seats:
        raise SeatMapFault(f"showtime {head['id']} has an empty seat set")
    label: dict[int, str] = {}
    prices: dict[int, int] = {}
    categories: list[Category] = []
    for s in seats:  # already gr ASC, gc ASC
        if label.setdefault(s.grid_row, s.row_label) != s.row_label:
            raise SeatMapFault(f"showtime {head['id']} grid row {s.grid_row} carries two row labels")
        if s.category_id not in prices:
            prices[s.category_id] = seat_price_paise(head["base_price_paise"], s.uplift)
            categories.append(Category(id=s.category_id, name=s.category_name, price_paise=prices[s.category_id]))
    # First appearance by gr, id ascending on a tie (P-BRW-16): a stable sort of the first-seen order on that key.
    first_gr = {}
    for s in seats:
        first_gr.setdefault(s.category_id, s.grid_row)
    categories.sort(key=lambda c: (first_gr[c.id], c.id))
    zone = head["timezone"]
    close = head["starts_at"] + cutoff
    return SeatMap(
        showtime=MapShowtime(id=head["id"], starts_at=local_iso(head["starts_at"], zone), sales_close_at=local_iso(close, zone),
                             sales_closed=not (now < close)),
        screen=MapScreen(id=head["screen_id"], name=head["screen_name"], rows=max(s.grid_row for s in seats),
                         cols=max(s.grid_col for s in seats)),
        categories=categories,
        seats=[Seat(id=s.id, row=s.row_label, num=s.seat_number, gr=s.grid_row, gc=s.grid_col, cat=s.category_id,
                    price_paise=prices[s.category_id],
                    state=seat_state(s.booked is not None, s.id in held),
                    is_active=s.is_active) for s in seats],
        generated_at=local_iso(now, zone),
        poll_interval_seconds=poll_interval_seconds,
    )

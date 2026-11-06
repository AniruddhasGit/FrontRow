"""The two messages this product sends, rendered by the worker at send time (P-TKT-06, SCR-TKT-02, P-TKT-12, the E5 reset
email). Everything printed is read from PostgreSQL in the same job (app/workers/__init__.py); nothing comes from the queue
payload except the reset token, which exists nowhere else (SRC-004 R-3)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from email.message import EmailMessage
from html import escape
from zoneinfo import ZoneInfo

from app.core.config import Settings
from app.domain.booking import presentation

SENDER_NAME = "FrontRow"  # SCR-TKT-02 / the reset email: the display name both messages send under
# The ruled position, written once and rendered into both parts (SRC-003 OPEN-CANCEL-01/02).
FINAL = "This booking is final. There is no cancellation and no refund."
RUPEE = "₹"  # the HTML part's symbol; the plain-text part says "Rs " (SCR-TKT-02)


@dataclass(frozen=True)
class ReceiptFacts:
    """Everything SCR-TKT-02 prints, read from PostgreSQL at send time (P-TKT-06): never from the queue payload."""

    reference: str  # the stored 8 characters
    film: str
    hall: str
    starts_at: datetime  # the stored UTC instant
    timezone: str  # the cinema row's zone
    seats: list[str]  # already ordered by row letter, then seat number as an integer
    total_paise: int


def _when(instant: datetime, zone: str) -> str:
    """S7.19's date-with-time form plus the zone (SCR-TKT-02): `21 Aug 2026, 7:15 pm (Asia/Kolkata)`. Built from parts,
    not strftime's %-d/%-I, which do not exist on every platform."""
    local = instant.astimezone(ZoneInfo(zone))
    hour = local.hour % 12 or 12
    return f"{local.day} {local:%b %Y}, {hour}:{local:%M} {'am' if local.hour < 12 else 'pm'} ({zone})"


def _amount(paise: int, ratio: int, symbol: str) -> str:
    """Integer paise to text at the last moment (FR-ADR-036), Indian grouping: 1,23,456.78. Never a float."""
    whole, minor = divmod(paise, ratio)
    digits = str(whole)
    head, tail = digits[:-3], digits[-3:]
    groups = []
    while len(head) > 2:
        groups.insert(0, head[-2:])
        head = head[:-2]
    grouped = ",".join(([head] if head else []) + groups + [tail])
    # The minor part carries as many digits as the ratio has zeros (2 at 100): the ratio is configuration, not 100.
    return f"{symbol}{grouped}.{minor:0{len(str(ratio)) - 1}d}"


def _message(sender: str, to: str, subject: str, text: str, html: str) -> EmailMessage:
    """One plain-text part (the authoritative one) and one minimal HTML alternative. No attachment, no image."""
    msg = EmailMessage()
    msg["From"] = f"{SENDER_NAME} <{sender}>"
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(text)
    msg.add_alternative(html, subtype="html")
    return msg


def receipt(facts: ReceiptFacts, to: str, settings: Settings) -> EmailMessage:
    """SCR-TKT-02, verbatim. A resend renders byte-identical content: nothing here depends on how many sends came before."""
    ref = presentation(facts.reference)
    url = f"{settings.PUBLIC_BASE_URL.rstrip('/')}/bookings/{ref}"
    when = _when(facts.starts_at, facts.timezone)
    seats = ", ".join(facts.seats)
    ratio = settings.CURRENCY_MINOR_UNIT_RATIO
    # Labels padded so every value starts at column 11: `Film` + 6 spaces, `Showtime` + 2, `Seats` + 5 (S-TKT-09).
    rows = [("Film", facts.film), ("Hall", facts.hall), ("Showtime", when), ("Seats", seats), ("Paid", _amount(facts.total_paise, ratio, "Rs "))]
    text = "\n".join([
        "Your booking is confirmed.", "",
        f"Booking reference: {ref}", "",
        *[f"{label:<10}{value}" for label, value in rows], "",
        "Show this reference at the entrance. A person will check it.", "",
        f"You can see this booking again at {url}", "",
        FINAL,
    ]) + "\n"
    facts_html = [("Film", facts.film), ("Hall", facts.hall), ("Showtime", when), ("Seats", seats),
                  ("Paid", _amount(facts.total_paise, ratio, RUPEE))]
    html = "\n".join([
        "<!doctype html>", '<html><body>',
        "<h1>Your booking is confirmed.</h1>",
        f'<p>Booking reference: <span style="font-family:monospace">{escape(ref)}</span></p>',
        "<ul>", *[f"<li>{label}: {escape(value)}</li>" for label, value in facts_html], "</ul>",
        "<p>Show this reference at the entrance. A person will check it.</p>",
        f'<p><a href="{escape(url)}">See this booking again</a></p>',
        f"<p>{FINAL}</p>",
        "</body></html>",
    ]) + "\n"
    return _message(settings.SES_SENDER_ADDRESS, to, f"Your FrontRow booking {ref}", text, html)


def password_reset(to: str, token: str, settings: Settings) -> EmailMessage:
    """The reset email (E5 reset-email copy). The token comes from the queue message (SRC-004 R-3), never a column.
    The minutes are interpolated from PASSWORD_RESET_TTL_SECONDS / 60, never typed (P-ACC-07)."""
    # The token rides in the URL FRAGMENT, not the query string: a browser never sends a fragment to a server, so no ALB
    # access log, no proxy and no request log can record it (prep-queue row 27; S-XCT-43 forbids a token in a query
    # string). [JUDGMENT CALL] P-ACC-07 publishes the token as a query parameter; the reset-confirm page reads location.hash instead.
    url = f"{settings.PUBLIC_BASE_URL.rstrip('/')}/account/reset/confirm#token={token}"
    minutes = settings.PASSWORD_RESET_TTL_SECONDS // 60
    lines = [f"A password reset was requested for {to}.", "Set a new password here:", url,
             f"The link works once and expires in {minutes} minutes.",
             "If you did not ask for this, nothing has happened to your account and you do not need to do anything."]
    text = f"{lines[0]}\n\n{lines[1]}\n{lines[2]}\n\n{lines[3]}\n\n{lines[4]}\n"
    html = "\n".join(["<!doctype html>", "<html><body>", f"<p>{escape(lines[0])}</p>",
                      f'<p>{lines[1]}<br><a href="{escape(url)}">{escape(url)}</a></p>', f"<p>{lines[3]}</p>",
                      f"<p>{lines[4]}</p>", "</body></html>"]) + "\n"
    return _message(settings.SES_SENDER_ADDRESS, to, "Reset your FrontRow password", text, html)

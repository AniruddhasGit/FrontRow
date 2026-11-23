// SCR-TKT-01 · /bookings/{reference}: durable and reachable again. Read through the caller's own lookup (EP-ACC-08)
// until lane E4's EP-TKT-01 exists; both are scoped to the signed-in owner on the server.
import { useEffect, useRef, useState } from "react";
import { Link, navigate } from "../../router";
import { formatPaise } from "../admin/money";
import { get } from "../browse/api";
import { dayLabel, timeLabel } from "../browse/logic";
import { reveal } from "../browse/reveal";
import "../booking/booking.css";
import { ShareButton } from "../discover/Bits";
import { bookingIcs } from "../discover/discover";
import { takeHandOver } from "./arrival";
import { ConfirmationPage, NOT_FOUND, UNAVAILABLE, failed, type Booking, hallViewSrc } from "./page";

export function ConfirmationScreen({ reference }: { reference: string }) {
  const [first] = useState(() => takeHandOver(reference));
  const [booking, setBooking] = useState<Booking | null>(null);
  const [email, setEmail] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const heading = useRef<HTMLDivElement>(null);

  useEffect(() => {
    get<Booking>(`/api/me/bookings/${encodeURIComponent(reference)}`).then((r) => {
      if (r.ok) return setBooking(r.body);
      if (r.status === 401) return navigate(`/sign-in?next=${encodeURIComponent(`/bookings/${reference}`)}`);
      setError(r.status === 404 ? NOT_FOUND : r.status === 503 ? UNAVAILABLE : r.status === 429 ? r.message : failed(r.requestId));
    });
    if (first) get<{ email: string }>("/api/auth/me").then((r) => r.ok && setEmail(r.body.email));
  }, [reference, first]);

  useEffect(() => {
    heading.current?.querySelector("h1")?.focus(); // focus moves to the page's only h1 on arrival
  }, [booking]);

  const copy = () => {
    if (!booking) return;
    navigator.clipboard?.writeText(booking.reference).then(() => setCopied(true), () => setCopied(false));
  };

  return (
    <div ref={heading}>
      <div className="fr-banner-region" aria-live="assertive">{error ? <p className="fr-banner">{error}</p> : null}</div>
      {booking || !error ? (
        <ConfirmationPage booking={booking} money={formatPaise} copied={copied} onCopy={copy}
          startsLabel={booking ? `${dayLabel(booking.showtime_starts_at.slice(0, 10))} · ${timeLabel(booking.showtime_starts_at)}` : ""}
          receiptTo={first ? email : null} />
      ) : null}
      {booking ? <Extras booking={booking as Booking & { showtime_ends_at?: string }} /> : null}
      {booking && hallViewSrc(booking.hall_name) ? (
        <figure className="fr-hall-view">
          <img ref={reveal} className="fr-reveal" src={hallViewSrc(booking.hall_name)!} alt={`The screen as seen from the middle of ${booking.hall_name}`}
               loading="lazy" width={1600} height={900} onError={(e) => ((e.currentTarget.parentElement as HTMLElement).hidden = true)} />
          <figcaption>Your view on the night: {booking.hall_name}, from the middle of the hall.</figcaption>
        </figure>
      ) : null}
    </div>
  );
}

/** CR-008 T13b/c: "Add to calendar" (an .ics file whose times are UTC instants, so any calendar shows them in its own
 *  zone at the right moment) and Share (the film and the time - never the reference, which is the ticket itself). */
function Extras({ booking }: { booking: Booking & { showtime_ends_at?: string } }) {
  const ends = booking.showtime_ends_at ?? booking.showtime_starts_at;
  const ics = bookingIcs({ ...booking, showtime_ends_at: ends }, new Date().toISOString());
  const when = `${dayLabel(booking.showtime_starts_at.slice(0, 10))}, ${timeLabel(booking.showtime_starts_at)}`;
  return (
    <div className="fr-ticket-extras">
      <a className="fr-action-secondary fr-calendar" href={`data:text/calendar;charset=utf-8,${encodeURIComponent(ics)}`}
         download={`frontrow-${booking.reference}.ics`}>
        <span aria-hidden="true">📅</span> Add to calendar
      </a>
      <ShareButton label="Share" title={booking.movie_title} path="/"
                   text={`I'm seeing ${booking.movie_title} at FrontRow, ${booking.hall_name}, ${when}.`} />
      {/* CR-011 F7: after paying - see every ticket, or go back to browsing */}
      <Link to="/bookings" className="fr-action-secondary">My bookings</Link>
      <Link to="/films" className="fr-action-secondary">Browse all films</Link>
    </div>
  );
}

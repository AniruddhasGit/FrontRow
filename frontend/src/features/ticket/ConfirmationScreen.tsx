// SCR-TKT-01 · /bookings/{reference}: durable and reachable again. Read through the caller's own lookup (EP-ACC-08)
// until lane E4's EP-TKT-01 exists; both are scoped to the signed-in owner on the server.
import { useEffect, useRef, useState } from "react";
import { navigate } from "../../router";
import { formatPaise } from "../admin/money";
import { get } from "../browse/api";
import { dayLabel, timeLabel } from "../browse/logic";
import "../booking/booking.css";
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
    if (booking) heading.current?.querySelector("h1")?.focus(); // focus moves to the page's only h1 on arrival
  }, [booking]);

  const copy = () => {
    if (!booking) return;
    navigator.clipboard?.writeText(booking.reference).then(() => setCopied(true), () => setCopied(false));
  };

  return (
    <div ref={heading}>
      <div className="fr-banner-region" aria-live="assertive">{error ? <p className="fr-banner">{error}</p> : null}</div>
      {booking ? (
        <ConfirmationPage booking={booking} money={formatPaise} copied={copied} onCopy={copy}
          startsLabel={`${dayLabel(booking.showtime_starts_at.slice(0, 10))} · ${timeLabel(booking.showtime_starts_at)}`}
          receiptTo={first ? email : null} />
      ) : null}
      {booking && hallViewSrc(booking.hall_name) ? (
        <figure className="fr-hall-view">
          <img src={hallViewSrc(booking.hall_name)!} alt={`The screen as seen from the middle of ${booking.hall_name}`}
               loading="lazy" width={1600} height={900} onError={(e) => ((e.currentTarget.parentElement as HTMLElement).hidden = true)} />
          <figcaption>Your view on the night: {booking.hall_name}, from the middle of the hall.</figcaption>
        </figure>
      ) : null}
    </div>
  );
}

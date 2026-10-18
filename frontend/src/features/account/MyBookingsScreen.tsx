// SCR-ACC-04 · My bookings at /bookings: a list. Each row links to the one booking page (SCR-TKT-01) and restates nothing.
import { useEffect, useState } from "react";
import { Link, navigate } from "../../router";
import { formatPaise } from "../admin/money";
import { get, query } from "../browse/api";
import { dayLabel, timeLabel } from "../browse/logic";
import { signOutSweep } from "../booking/checkout";
import "../booking/booking.css";

type Row = { reference: string; movie_title: string; hall_name: string; seat_count: number; showtime_starts_at: string; seats: string[];
             total_paise: number };
type Page = { upcoming: Row[]; past: Row[]; page: number; page_size: number; total_upcoming: number; total_past: number };

export async function signOut(): Promise<void> {
  await fetch("/api/auth/logout", { method: "POST", credentials: "same-origin" }).catch(() => null);
  try {
    signOutSweep(window.sessionStorage); // the whole fr.* namespace, never a named list
  } catch {
    // no storage to sweep
  }
  navigate("/");
}

function Rows({ rows }: { rows: Row[] }) {
  return (
    <ul className="fr-bookings">
      {rows.map((r) => (
        <li key={r.reference}>
          <Link to={`/bookings/${encodeURIComponent(r.reference)}`} className="fr-booking-row">
            <span className="fr-mono">{r.reference}</span>
            <span>{r.movie_title}</span>
            <span className="fr-mono">{dayLabel(r.showtime_starts_at.slice(0, 10))} · {timeLabel(r.showtime_starts_at)}</span>
            <span>{r.hall_name} · {r.seats.join(", ")}</span>
            <span className="fr-mono">{formatPaise(r.total_paise)}</span>
          </Link>
        </li>
      ))}
    </ul>
  );
}

export function MyBookingsScreen() {
  const [page, setPage] = useState(1);
  const [data, setData] = useState<Page | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    get<Page>(`/api/me/bookings${query({ page })}`).then((r) => {
      if (r.ok) return setData(r.body);
      if (r.status === 401) return navigate(`/sign-in?next=${encodeURIComponent("/bookings")}`);
      setError(r.message || "Your bookings cannot be loaded right now. Try again shortly.");
    });
  }, [page]);
  const nothing = data && data.total_upcoming === 0 && data.total_past === 0;
  return (
    <section>
      <h1>My bookings</h1>
      <div className="fr-banner-region" aria-live="assertive">{error ? <p className="fr-banner">{error}</p> : null}</div>
      {nothing ? <p>You have not booked anything yet. <Link to="/">See what is showing</Link></p> : null}
      {data && !nothing ? (
        <>
          <h2>Upcoming</h2>
          {data.total_upcoming === 0 ? <p>You have nothing coming up.</p> : <Rows rows={data.upcoming} />}
          <h2>Past</h2>
          <Rows rows={data.past} />
          <p className="fr-pager">
            {page > 1 ? <button type="button" className="fr-action-secondary" onClick={() => setPage(page - 1)}>Previous page</button> : null}
            {page * data.page_size < Math.max(data.total_upcoming, data.total_past)
              ? <button type="button" className="fr-action-secondary" onClick={() => setPage(page + 1)}>Next page</button> : null}
          </p>
        </>
      ) : null}
      <button type="button" className="fr-action-secondary" onClick={() => void signOut()}>Sign out</button>
    </section>
  );
}

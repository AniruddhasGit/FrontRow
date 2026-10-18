// SCR-BRW-02 · one film and its showtimes at `/movies/{movie_id}`, optionally `?date=YYYY-MM-DD`. Anyone.
// With no date the server answers for TODAY IN THE CINEMA'S ZONE and says which date it used; the strip is today
// through the last day of the film's window (P-BRW-06). A closed showtime is listed, marked, not focusable, and
// goes nowhere (P-BRW-07).
import { useEffect, useRef, useState } from "react";
import { formatPaise } from "../admin/money";
import { Link, navigate } from "../../router";
import { get, query, type Film, type Showtime } from "./api";
import { DayStrip } from "./DayStrip";
import { countLine, dayLabel, movieStrip, showtimeName, timeLabel } from "./logic";
import { Poster } from "./Poster";
import "./browse.css";

// The one place these screens read the clock; tests and a harness pass their own `now`. Module-level, so it is
// the same function on every render and never re-triggers the effects that depend on it.
const wallClock = () => Date.now();

type Listed = { date: string; next_date_with_showtimes: string | null; showtimes: Showtime[] };

// The first state, for the render harness (react-dom/server runs no effect). Production passes no seed.
type Seed = { film?: Film | "missing"; date?: string | null; listed?: Listed; failed?: boolean };

export function MovieScreen({ movieId, now = wallClock, seed }: { movieId: string; now?: () => number; seed?: Seed }) {
  const [film, setFilm] = useState<Film | null | "missing">(seed?.film ?? null);
  const [date, setDate] = useState<string | null>(() => (seed ? seed.date ?? null : new URLSearchParams(window.location.search).get("date")));
  const [listed, setListed] = useState<Listed | null>(seed?.listed ?? null);
  const [failed, setFailed] = useState(seed?.failed ?? false);
  const [attempt, setAttempt] = useState(0);
  const [announce, setAnnounce] = useState("");
  const first = useRef(true);

  useEffect(() => {
    get<Film>(`/api/movies/${encodeURIComponent(movieId)}`).then((r) => setFilm(r.ok ? r.body : "missing"));
  }, [movieId]);

  useEffect(() => {
    const controller = new AbortController();
    setListed(null);
    get<Listed>(`/api/showtimes${query({ movie_id: movieId, date })}`, controller.signal).then((r) => {
      if (controller.signal.aborted) return;
      if (!r.ok) {
        if (r.status === 404) setFilm("missing");
        setFailed(r.status !== 404);
        return;
      }
      setFailed(false);
      setListed(r.body);
      if (!first.current) setAnnounce(countLine(r.body.showtimes.length, "showtime", "on this date"));
      first.current = false;
    });
    return () => controller.abort();
  }, [movieId, date, attempt]);

  const choose = (day: string | null) => {
    setDate(day);
    window.history.replaceState(null, "", `/movies/${movieId}${query({ date: day })}`);
  };

  if (film === "missing") {
    return (
      <section className="fr-state">
        <p>That movie is not showing.</p>
        <Link to="/">Back to what is showing</Link>
      </section>
    );
  }
  const selected = date ?? listed?.date ?? null;
  const days = film ? movieStrip(now(), film.display_until) : [];

  return (
    <section className="fr-movie">
      {film ? (
        <header className="fr-movie-head">
          <Poster src={film.poster_url} title={film.title} />
          <div>
            <h1>{film.title}</h1>
            <p className="fr-meta">
              <span className="fr-mono">{film.runtime_minutes} min</span>
              <span className="fr-chip">{film.certification.name}</span>
              <span>{film.language.name}</span>
              {film.genres.length > 0 ? <span>{film.genres.map((g) => g.name).join(", ")}</span> : null}
            </p>
            <p className="fr-movie-synopsis">{film.synopsis}</p>
          </div>
        </header>
      ) : null}
      {days.length > 0 ? <DayStrip label="Choose a date" days={days} selected={selected} onSelect={choose} /> : null}
      <p className="fr-visually-hidden" aria-live="polite">{announce}</p>
      {failed ? (
        <div className="fr-state">
          <p>Showtimes could not be loaded.</p>
          <button type="button" className="fr-clear" onClick={() => setAttempt((n) => n + 1)}>Try again</button>
        </div>
      ) : listed === null ? (
        <ul className="fr-times" aria-hidden="true">{[0, 1, 2, 3].map((i) => <li key={i} className="fr-time fr-time-loading" />)}</ul>
      ) : listed.showtimes.length === 0 ? (
        <div className="fr-state">
          {listed.next_date_with_showtimes ? (
            <>
              <p>No showtimes on this date.</p>
              <button type="button" className="fr-clear" onClick={() => choose(listed.next_date_with_showtimes)}>
                Next: {dayLabel(listed.next_date_with_showtimes)}
              </button>
            </>
          ) : (
            <p>No showtimes for this movie.</p>
          )}
        </div>
      ) : (
        <>
          <ul className="fr-times">
            {listed.showtimes.map((st) => (
              <li key={st.id}>
                <ShowtimeButton st={st} />
              </li>
            ))}
          </ul>
          {listed.next_date_with_showtimes && listed.showtimes.every((s) => s.sales_closed) ? (
            // Every showtime here is closed: the list stays, and the next buyable date is offered (P-BRW-06 1a).
            <button type="button" className="fr-clear" onClick={() => choose(listed.next_date_with_showtimes)}>
              Next: {dayLabel(listed.next_date_with_showtimes)}
            </button>
          ) : null}
        </>
      )}
    </section>
  );
}

function ShowtimeButton({ st }: { st: Showtime }) {
  const name = showtimeName(st, formatPaise);
  const body = (
    <>
      <span className="fr-mono fr-time-at">{timeLabel(st.starts_at)}</span>
      <span className="fr-time-hall">{st.screen.name}</span>
      {st.sales_closed ? <span className="fr-time-closed">Closed</span> : <span className="fr-mono fr-time-price">{formatPaise(st.base_price_paise)}</span>}
    </>
  );
  if (st.sales_closed) {
    // Removed from the tab order and inert: its state is in its name, so nobody is told to activate it.
    return <a className="fr-time" data-closed="" aria-disabled="true" tabIndex={-1} aria-label={name} onClick={(e) => e.preventDefault()}>{body}</a>;
  }
  const to = `/showtimes/${st.id}`;
  return (
    <a className="fr-time" href={to} aria-label={name} onClick={(e) => {
      if (e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
      e.preventDefault();
      navigate(to);
    }}>
      {body}
    </a>
  );
}

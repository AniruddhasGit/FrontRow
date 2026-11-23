// SCR-BRW-02 · one film and its showtimes at `/movies/{movie_id}`, optionally `?date=YYYY-MM-DD`. Anyone.
// With no date the server answers for TODAY IN THE CINEMA'S ZONE and says which date it used; the strip is today
// through the last day of the film's window (P-BRW-06). A closed showtime is listed, marked, not focusable, and
// goes nowhere (P-BRW-07).
// CR-011 F3 (the owner's reference: a big film page): a hero over the film's own poster light - poster, the rating box
// with Rate now, runtime / genres / certificate / release date, the formats and language, Book tickets and Share; then
// the showtimes for the chosen date grouped by screen; About, cast and crew, ratings and reviews; You might also like.
// The hero (owner, 2026-11-23): the description where Book tickets was, and on the right a dim corridor ending in the
// show's door (Door.tsx) - the chosen time's, else the first open one. Choosing a time points the door at it and brings
// it into view; pressing the door flies through it into that show's hall (the page's other parts slide away first).
import { useEffect, useRef, useState, type MouseEvent } from "react";
import { formatPaise } from "../admin/money";
import { Link, navigate } from "../../router";
import { get, query, type Film, type FilmDetail, type Showtime } from "./api";
import { DayStrip } from "./DayStrip";
import { countLine, dayLabel, movieStrip, showtimeName, timeLabel } from "./logic";
import { Poster } from "./Poster";
import { BookmarkToggle, useSaved } from "../account/Bookmark";
import { FilmTile, releaseLabel, ShareButton } from "../discover/Bits";
import { adultsOnly, doorShow, pushRecent, ratingName, ratingText, recentStore, recommended } from "../discover/discover";
import { TheatreDoor } from "../discover/Door";
import { FilmDetails } from "../discover/FilmDetails";
import "./browse.css";

// The one place these screens read the clock; tests and a harness pass their own `now`. Module-level, so it is
// the same function on every render and never re-triggers the effects that depend on it.
const wallClock = () => Date.now();

type Listed = { date: string; next_date_with_showtimes: string | null; showtimes: Showtime[] };

// The first state, for the render harness (react-dom/server runs no effect). Production passes no seed.
type Seed = { film?: FilmDetail | "missing"; date?: string | null; listed?: Listed; failed?: boolean; chosen?: number | null };

/** `2h 13m` / `55m` */
function hours(minutes: number): string {
  return minutes >= 60 ? `${Math.floor(minutes / 60)}h ${minutes % 60}m` : `${minutes}m`;
}

export function MovieScreen({ movieId, now = wallClock, seed }: { movieId: string; now?: () => number; seed?: Seed }) {
  const [film, setFilm] = useState<FilmDetail | null | "missing">(seed?.film ?? null);
  const [date, setDate] = useState<string | null>(() => (seed ? seed.date ?? null : new URLSearchParams(window.location.search).get("date")));
  const [listed, setListed] = useState<Listed | null>(seed?.listed ?? null);
  const [failed, setFailed] = useState(seed?.failed ?? false);
  const [attempt, setAttempt] = useState(0);
  const [announce, setAnnounce] = useState("");
  const [saved, toggle] = useSaved(); // CR-008 T4
  const first = useRef(true);
  // CR-011 F5: the show whose door is open, kept in the URL (?show=) so Back from the seat page returns to it
  const [chosen, setChosen] = useState<number | null>(() => (seed ? seed.chosen ?? null
    : Number(new URLSearchParams(window.location.search).get("show")) || null));
  const [all, setAll] = useState<Film[]>([]); // CR-011 F3: the listing, for You might also like
  const door = useRef<HTMLDivElement>(null);
  const toDoor = useRef(false);
  const [flying, setFlying] = useState(false); // the door was pressed: everything but the corridor slides away
  useEffect(() => {
    if (!flying) return;
    document.documentElement.dataset.flying = "";
    return () => void delete document.documentElement.dataset.flying;
  }, [flying]);

  useEffect(() => {
    get<{ movies: Film[] }>("/api/movies").then((r) => r.ok && setAll(r.body.movies));
  }, []);
  useEffect(() => {
    if (!toDoor.current || chosen === null) return;
    toDoor.current = false;
    door.current?.scrollIntoView({ block: "center", behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" });
    door.current?.querySelector<HTMLButtonElement>(".fr-corridor-door")?.focus({ preventScroll: true });
  }, [chosen]);

  useEffect(() => {
    get<FilmDetail>(`/api/movies/${encodeURIComponent(movieId)}`).then((r) => {
      setFilm(r.ok ? r.body : "missing");
      if (r.ok) pushRecent(recentStore(), r.body.id); // CR-008 T13d: this browser's Recently viewed
    });
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
    setChosen(null);
    window.history.replaceState(window.history.state, "", `/movies/${movieId}${query({ date: day })}`);
  };
  const pick = (id: number) => {
    toDoor.current = true;
    setChosen(id);
    window.history.replaceState(window.history.state, "", `/movies/${movieId}${query({ date, show: id })}`);
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
  const show = doorShow(listed?.showtimes ?? [], chosen);
  const started = !!show && Date.parse(show.starts_at) <= now();
  const also = film ? recommended(film, all) : [];
  const days = film ? movieStrip(now(), film.display_until) : [];

  return (
    <section className="fr-movie" data-flying={flying || undefined}>
      {film ? (
        <header className="fr-movie-hero">
          <div className="fr-movie-backdrop" aria-hidden="true" style={{ backgroundImage: `url(${film.poster_url})` }} />
          <div className="fr-movie-hero-inner">
            <div className="fr-movie-poster">
              <Poster src={film.poster_url} title={film.title} />
              <p className="fr-movie-in">{film.coming_soon ? "Coming soon" : "In cinemas"}</p>
            </div>
            <div className="fr-movie-info">
              {film.coming_soon && film.release_date ? <p className="fr-opens">Opens {releaseLabel(film.release_date)}</p> : null}
              <h1>{film.title}</h1>
              <div className="fr-rate-box">
                {film.coming_soon ? (
                  <span className="fr-rate-figure">♥ {film.likes} {film.likes === 1 ? "person wants" : "people want"} to see it</span>
                ) : (
                  <span className="fr-rate-figure" role="img" aria-label={ratingName(film.rating)}>
                    <span aria-hidden="true">★ {ratingText(film.rating) ?? "New"}{film.rating.count ? "/10" : ""}</span>
                    <span className="fr-rate-votes" aria-hidden="true">
                      {film.rating.count ? ` (${film.rating.count} ${film.rating.count === 1 ? "vote" : "votes"})` : " No votes yet"}
                    </span>
                  </span>
                )}
                <a className="fr-action-secondary fr-rate-now" href="#film-rate" onClick={(e) => jump(e, "film-rate")}>
                  {film.coming_soon ? "Like it" : "Rate now"}
                </a>
              </div>
              <p className="fr-movie-meta">
                {[hours(film.runtime_minutes), film.genres.map((g) => g.name).join(", "), film.certification.name,
                  film.release_date ? releaseLabel(film.release_date) : ""].filter(Boolean).join(" • ")}
              </p>
              <p className="fr-movie-chips">
                {formats(listed?.showtimes ?? []).map((f) => <span key={f} className="fr-chip">{f}</span>)}
                <span className="fr-chip">{film.language.name}</span>
              </p>
              <p className="fr-movie-about">{film.synopsis || "No description yet."}</p>
              {started ? <p className="fr-door-note">This show started at {timeLabel(show!.starts_at)}. Seats stay on sale until sales close.</p> : null}
              {adultsOnly(film.certification.name)
                ? <p className="fr-door-note">Rated {film.certification.name}: adults only. Carry a photo ID to the show.</p> : null}
            </div>
            {film.coming_soon ? null : (
              <div ref={door} className="fr-movie-door"><TheatreDoor show={show} film={film} onFly={setFlying} /></div>
            )}
            <div className="fr-movie-actions">
              <BookmarkToggle movieId={film.id} title={film.title} state={saved} toggle={toggle} />
              <ShareButton title={film.title} text={`${film.title} at FrontRow`} path={`/movies/${film.id}`} />
            </div>
          </div>
        </header>
      ) : (
        // the hero's frame while the film loads, the same grid and the same 2:3 poster box, so the showtimes below do
        // not jump down by the hero's height when it arrives (CLS 0.47, 2026-11-23)
        <header className="fr-movie-hero" aria-hidden="true">
          <div className="fr-movie-hero-inner">
            <div className="fr-movie-poster fr-card-loading"><div className="fr-poster" /></div>
            <div className="fr-movie-info" />
            <div className="fr-movie-door" />
          </div>
        </header>
      )}
      {/* with the film: its date strip (drawn from the film's window) would otherwise land above the times and push them */}
      {film ? <section id="showtimes" className="fr-showtimes" aria-labelledby="showtimes-title">
      <h2 id="showtimes-title">Showtimes</h2>
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
          {/* owner, 2026-11-23: one row of small boxes - format on top, the time, the screen - not a card per screen */}
          <ul className="fr-times fr-times-flat">
            {[...listed.showtimes].sort((x, y) => Date.parse(x.starts_at) - Date.parse(y.starts_at)).map((st) => (
              <li key={st.id}>
                <ShowtimeButton st={st} chosen={st.id === show?.id} onChoose={pick} />
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
      </section> : null}
      {film && film.rating.breakdown ? <FilmDetails film={film} onChanged={setFilm} /> : null}
      {film && also.length ? (
        <section aria-labelledby="also-like" className="fr-also">
          <div className="fr-row-head">
            <h2 id="also-like">You might also like</h2>
            <p>Films that share its genres.</p>
            <a className="fr-see-all" href="/films" onClick={(e) => { e.preventDefault(); navigate("/films"); }}>View all films →</a>
          </div>
          <ul className="fr-tiles">{also.map((f) => <FilmTile key={f.id} film={f} />)}</ul>
        </section>
      ) : null}
    </section>
  );
}

/** The formats a set of showtimes is shown in (2D, IMAX...), once each. */
function formats(shows: Showtime[]): string[] {
  return [...new Set(shows.map((t) => t.format?.name).filter((f): f is string => Boolean(f)))];
}

/** An in-page jump (Rate now, Book tickets) that scrolls without adding a history step. */
function jump(e: MouseEvent<HTMLAnchorElement>, id: string) {
  e.preventDefault();
  const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;
  document.getElementById(id)?.scrollIntoView({ block: "start", behavior: reduced ? "auto" : "smooth" });
}

function ShowtimeButton({ st, chosen, onChoose }: { st: Showtime; chosen: boolean; onChoose: (id: number) => void }) {
  const name = showtimeName(st, formatPaise);
  const body = (
    <>
      {st.format?.name ? <span className="fr-time-format">{st.format.name}</span> : null}
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
    // CR-011 F5: a plain click chooses the show and opens its door; a modified click still opens the seats in a new tab
    <a className="fr-time" href={to} aria-label={name} aria-current={chosen || undefined} onClick={(e) => {
      if (e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
      e.preventDefault();
      onChoose(st.id);
    }}>
      {body}
    </a>
  );
}

// CR-005: the landing at `/` (and `/browse`). You sit locked in the hall's default seat (the back row's seat 1). The
// films run down a rail on the left; the one clicked plays on the screen (scrolling only scrolls - owner, 2026-11-23). The landing is a showcase (owner, 2026-11-23:
// "load all the movies in the theatre hall 6 ... when they are actually going to book the seats then only show them
// their real halls"): every film plays in Hall 6, so changing film never loads another hall - the projector flickers
// and the screen lights up with the new film (hall3d/flicker.ts). "Book tickets" goes to the seat page of the chosen
// show, which arrives in that show's real hall (signed out: through sign-in first).
// "All films" (owner, 2026-11-22; the curtain is gone): the rail expands across the page, then the films already in it
// glide to their places in the /films grid (a View Transition, matched by name) and the films that were not in the
// rail fade in a moment after (immersive.css).
// CR-011 F1 (owner: "browse a few films like 10 max in the left side bar which are top 10 rated one, then to explore more
// movies they'll have to hit on all films"): the rail holds the 10 best-rated films that are out (discover.ts sidebarTop),
// then "All films".
// Reads only the public read path, once per choice; nothing polls.
import { useEffect, useState } from "react";
import { formatPaise } from "../admin/money";
import { leaveForSignIn, signInHref, takeNotice } from "../auth/session";
import { get, query, type Film, type Showtime } from "../browse/api";
import { runtimeName, showtimeName, timeLabel } from "../browse/logic";
import { Poster } from "../browse/Poster";
import { BookmarkToggle, useSaved } from "../account/Bookmark";
import { sidebarTop } from "../discover/discover";
import { Discover } from "../discover/Rows";
import { HallStage } from "../hall3d/HallStage";
import { navigate } from "../../router";
import "../browse/browse.css";

type Listed = { date: string; next_date_with_showtimes: string | null; showtimes: Showtime[] };
type Leaving = null | "films";
const SHOWCASE_HALL = 6; // the biggest room; the landing never switches halls
const EXPAND_MS = 600; // the rail's ground wiping across the page (immersive.css .fr-landing::after), before /films takes over

export function Landing() {
  const [films, setFilms] = useState<Film[] | null>(null); // the rail: what is showing
  const [all, setAll] = useState<Film[]>([]); // CR-008 T10: every listed film, coming soon included, for the rows below
  const [failed, setFailed] = useState(false);
  const [filmId, setFilmId] = useState<number | null>(null);
  const [listed, setListed] = useState<Listed | null>(null);
  const [st, setSt] = useState<Showtime | null>(null);
  const [leaving, setLeaving] = useState<Leaving>(null);
  const [saved, toggle] = useSaved(); // CR-008 T4: Save for the film on the screen
  const [notice] = useState(() => {
    try {
      return takeNotice(window.sessionStorage);
    } catch {
      return null;
    }
  });

  useEffect(() => {
    get<{ movies: Film[] }>("/api/movies").then((r) => {
      if (!r.ok) return setFailed(true);
      const showing = sidebarTop(r.body.movies);
      setAll(r.body.movies);
      setFilms(showing);
      setFilmId((id) => id ?? showing[0]?.id ?? null);
    });
  }, []);
  useEffect(() => {
    if (filmId === null) return;
    const ctl = new AbortController();
    setListed(null);
    setSt(null);
    get<Listed>(`/api/showtimes${query({ movie_id: filmId })}`, ctl.signal).then((r) => {
      if (ctl.signal.aborted || !r.ok) return;
      setListed(r.body);
      const first = r.body.showtimes.find((s) => !s.sales_closed) ?? r.body.showtimes[0] ?? null;
      setSt(first);
    });
    return () => ctl.abort();
  }, [filmId]);

  const book = async () => {
    if (!st || leaving) return;
    const to = `/showtimes/${st.id}`;
    const me = await fetch("/api/auth/me", { credentials: "same-origin" }).catch(() => null);
    if (!me?.ok) {
      try {
        leaveForSignIn(to, window.sessionStorage, Date.now());
      } catch {
        // no storage: sign-in still returns by its ?next
      }
      return navigate(signInHref(to));
    }
    navigate(to); // the seat page arrives in the show's own hall
  };
  useEffect(() => {
    if (leaving !== "films") return;
    const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;
    const t = setTimeout(() => navigate("/films"), reduced ? 0 : EXPAND_MS);
    return () => clearTimeout(t);
  }, [leaving]);

  const film = films?.find((f) => f.id === filmId) ?? null;
  return (
    <>
    <section className="fr-immersive fr-landing" data-leaving={leaving ?? undefined}>
      <aside className="fr-rail" aria-label="Films">
        <h1>Top 10</h1>
        <p className="fr-rail-note">The best-rated films showing now.</p>
        {notice ? <div className="fr-banner" role="alert"><p>{notice}</p></div> : null}
        {failed ? <p className="fr-state">The listing could not be loaded.</p>
          : films?.length === 0 ? <p className="fr-state">Nothing is showing right now.</p> : null}
        <ul className="fr-rail-films">
          {films?.map((f, i) => (
            // the same view-transition name as its /films card: the browser glides each film to its place in the grid
            <li key={f.id} data-film={f.id} style={{ viewTransitionName: `film-${f.id}`, ["--i" as string]: i }}>
              <button type="button" className="fr-rail-film" aria-pressed={f.id === filmId} onClick={() => setFilmId(f.id)}>
                <Poster src={f.poster_url} title={f.title} />
                <span className="fr-rail-title">{f.title}</span>
                <span className="fr-meta">
                  <span className="fr-mono">{runtimeName(f.runtime_minutes)}</span>
                  <span className="fr-chip">{f.certification.name}</span>
                  <span>{f.language.name}</span>
                </span>
              </button>
            </li>
          ))}
        </ul>
        <button type="button" className="fr-action-secondary fr-rail-all" disabled={!!leaving} onClick={() => setLeaving("films")}>
          All films
        </button>
      </aside>
      <div className="fr-landing-stage">
        <HallStage hallNo={SHOWCASE_HALL} film={film} />
        {film ? (
          <div className="fr-landing-bar">
            <p className="fr-landing-now">{film.title}</p>
            <BookmarkToggle movieId={film.id} title={film.title} state={saved} toggle={toggle} />
            {listed === null ? <p className="fr-browse-note">Finding the times…</p> : listed.showtimes.length === 0 ? (
              <p className="fr-browse-note">No showtimes today.</p>
            ) : (
              <div role="group" aria-label="Showtimes" className="fr-landing-times">
                {listed.showtimes.map((s) => (
                  <button key={s.id} type="button" className="fr-choice" aria-pressed={s.id === st?.id} disabled={s.sales_closed}
                          aria-label={showtimeName(s, formatPaise)} onClick={() => setSt(s)}>
                    <span className="fr-mono">{timeLabel(s.starts_at)}</span>
                  </button>
                ))}
              </div>
            )}
            <button type="button" className="fr-action" disabled={!st || st.sales_closed || !!leaving} onClick={() => void book()}>
              Book tickets
            </button>
          </div>
        ) : null}
      </div>
    </section>
    {/* CR-008 T10/T13: under the hall - the featured films, the rows, Recently viewed */}
    {all.length ? <Discover films={all} /> : null}
    </>
  );
}

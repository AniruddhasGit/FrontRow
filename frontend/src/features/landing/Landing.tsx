// CR-005: the landing at `/` (and `/browse`). You sit locked in the hall's default seat (the back row's seat 1). The
// films run down a rail on the left; the one centred in the rail plays on the screen - in the hall of its next show,
// so booking happens in the room you are already in. "Book tickets":
//   signed out - to sign-in, which returns to the seat page (its own arrival: the screen, then the seats);
//   signed in  - one flow: the rail folds away, the camera turns from your seat onto the seats, and the seat page takes
//                over on that same picture (fr.flown; the router holds the frame until its hall has drawn).
// "All films": the curtain drops on the hall, then opens from left to right, pulling the rail's edge across with it until
// the rail is the whole page; the films already in the rail glide to their places in the /films grid (a View Transition,
// matched by name) and everything else fades in.
// Reads only the public read path, once per choice; nothing polls.
import { useCallback, useEffect, useRef, useState } from "react";
import { formatPaise } from "../admin/money";
import { leaveForSignIn, signInHref, takeNotice } from "../auth/session";
import { get, query, type Film, type Showtime } from "../browse/api";
import { runtimeName, showtimeName, timeLabel } from "../browse/logic";
import { Poster } from "../browse/Poster";
import { Curtain, type CurtainPhase } from "../curtain/Curtain";
import { FLOWN } from "../hall3d/Hall3D";
import { screenNumber } from "../hall3d/hall";
import { nextHallDrawn } from "../hall3d/hallReady";
import { HallStage } from "../hall3d/HallStage";
import { parseSeatMap, type SeatMap } from "../seatmap/model";
import { navigate } from "../../router";
import "../browse/browse.css";

type Listed = { date: string; next_date_with_showtimes: string | null; showtimes: Showtime[] };
type Leaving = null | "book" | "curtain" | "drawn";

export function Landing() {
  const [films, setFilms] = useState<Film[] | null>(null);
  const [failed, setFailed] = useState(false);
  const [filmId, setFilmId] = useState<number | null>(null);
  const [listed, setListed] = useState<Listed | null>(null);
  const [st, setSt] = useState<Showtime | null>(null);
  const [hall, setHall] = useState(1);
  const [map, setMap] = useState<SeatMap | null>(null);
  const [leaving, setLeaving] = useState<Leaving>(null);
  const rail = useRef<HTMLUListElement>(null);
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
      setFilms(r.body.movies);
      setFilmId((id) => id ?? r.body.movies[0]?.id ?? null);
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
      const n = first ? screenNumber(first.screen.name) : null;
      if (n) setHall(n); // the film plays in the hall it is booked in; no show, the room stays as it is
    });
    return () => ctl.abort();
  }, [filmId]);
  useEffect(() => {
    setMap(null);
    if (!st) return;
    const ctl = new AbortController();
    get<unknown>(`/api/showtimes/${st.id}/seatmap`, ctl.signal).then((r) => !ctl.signal.aborted && r.ok && setMap(parseSeatMap(r.body)));
    return () => ctl.abort();
  }, [st]);

  // The film centred in the rail is the one on the screen. Read once the scrolling settles, so a fast flick through
  // the list does not load every hall on the way.
  useEffect(() => {
    const ul = rail.current;
    if (!ul || !films?.length) return;
    let t = 0;
    const settle = () => {
      clearTimeout(t);
      t = window.setTimeout(() => {
        const box = ul.getBoundingClientRect();
        const across = ul.scrollWidth > ul.clientWidth + 1; // phones: the rail scrolls sideways
        const mid = across ? box.left + box.width / 2 : box.top + box.height / 2;
        let best: HTMLElement | null = null, gap = Infinity;
        for (const li of ul.children as HTMLCollectionOf<HTMLElement>) {
          const r = li.getBoundingClientRect();
          const d = Math.abs((across ? r.left + r.width / 2 : r.top + r.height / 2) - mid);
          if (d < gap) [best, gap] = [li, d];
        }
        const id = Number(best?.dataset.film);
        if (id) setFilmId(id);
      }, 180);
    };
    ul.addEventListener("scroll", settle, { passive: true });
    return () => {
      ul.removeEventListener("scroll", settle);
      clearTimeout(t);
    };
  }, [films]);
  const centre = (id: number) => {
    setFilmId(id);
    rail.current?.querySelector<HTMLElement>(`[data-film="${id}"]`)?.scrollIntoView({ behavior: "smooth", block: "center", inline: "center" });
  };

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
    setLeaving("book");
  };
  const panned = useCallback(() => {
    if (!st) return;
    try {
      window.sessionStorage.setItem(FLOWN, String(st.id));
    } catch {
      // no storage: the seat page plays its own arrival instead
    }
    navigate(`/showtimes/${st.id}`, nextHallDrawn());
  }, [st]);
  const curtainDone = () => {
    if (leaving === "curtain") setLeaving("drawn");
    else if (leaving === "drawn") navigate("/films");
  };

  const film = films?.find((f) => f.id === filmId) ?? null;
  const phase: CurtainPhase = leaving === "curtain" ? "down" : leaving === "drawn" ? "drawn" : "up";
  return (
    <section className="fr-immersive fr-landing" data-leaving={leaving ?? undefined}>
      <aside className="fr-rail" aria-label="Films">
        <h1>Now showing</h1>
        {notice ? <div className="fr-banner" role="alert"><p>{notice}</p></div> : null}
        {failed ? <p className="fr-state">The listing could not be loaded.</p>
          : films?.length === 0 ? <p className="fr-state">Nothing is showing right now.</p> : null}
        <ul ref={rail} className="fr-rail-films">
          {films?.map((f) => (
            // the same view-transition name as its /films card: the browser glides each film to its place in the grid
            <li key={f.id} data-film={f.id} style={{ viewTransitionName: `film-${f.id}` }}>
              <button type="button" className="fr-rail-film" aria-pressed={f.id === filmId} onClick={() => centre(f.id)}>
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
        <button type="button" className="fr-action-secondary fr-rail-all" disabled={!!leaving} onClick={() => setLeaving("curtain")}>
          All films
        </button>
      </aside>
      <div className="fr-landing-stage">
        <HallStage hallNo={hall} film={film} map={map} pan={leaving === "book"} onPanned={panned} />
        <Curtain phase={phase} onDone={curtainDone} />
        <div className="fr-landing-fill" aria-hidden="true" />
        {film ? (
          <div className="fr-landing-bar">
            <p className="fr-landing-now">{film.title}</p>
            {listed === null ? <p className="fr-browse-note">Finding the times…</p> : listed.showtimes.length === 0 ? (
              <p className="fr-browse-note">No showtimes today.</p>
            ) : (
              <div role="group" aria-label="Showtimes" className="fr-landing-times">
                {listed.showtimes.map((s) => (
                  <button key={s.id} type="button" className="fr-choice" aria-pressed={s.id === st?.id} disabled={s.sales_closed}
                          aria-label={showtimeName(s, formatPaise)} onClick={() => {
                            setSt(s);
                            const n = screenNumber(s.screen.name);
                            if (n) setHall(n);
                          }}>
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
  );
}

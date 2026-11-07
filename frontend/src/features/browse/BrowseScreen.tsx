// CR-004: /browse. The films down a rail on the left; the chosen show's hall fills the rest of the screen with its
// film on the screen. Changing the film or the time changes the hall. "Choose your seats" opens the seat page.
// Reads only the public read path (the same calls as SCR-BRW-01/02), one fetch per choice, no polling.
import { useEffect, useState } from "react";
import { formatPaise } from "../admin/money";
import { takeNotice } from "../auth/session";
import { screenNumber } from "../hall3d/hall";
import { HallStage } from "../hall3d/HallStage";
import { parseSeatMap, type SeatMap } from "../seatmap/model";
import { Link, navigate } from "../../router";
import { get, query, type Film, type Showtime } from "./api";
import { dayLabel, runtimeName, showtimeName, timeLabel } from "./logic";
import { Poster } from "./Poster";
import "./browse.css";

type Listed = { date: string; next_date_with_showtimes: string | null; showtimes: Showtime[] };

export function BrowseScreen() {
  const [films, setFilms] = useState<Film[] | null>(null);
  const [failed, setFailed] = useState(false);
  const [filmId, setFilmId] = useState<number | null>(null);
  const [date, setDate] = useState<string | null>(null);
  const [listed, setListed] = useState<Listed | null>(null);
  const [st, setSt] = useState<Showtime | null>(null);
  const [map, setMap] = useState<SeatMap | null>(null);
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
    get<Listed>(`/api/showtimes${query({ movie_id: filmId, date })}`, ctl.signal).then((r) => {
      if (ctl.signal.aborted || !r.ok) return;
      setListed(r.body);
      // straight into the hall of the first show still on sale
      setSt(r.body.showtimes.find((s) => !s.sales_closed) ?? r.body.showtimes[0] ?? null);
    });
    return () => ctl.abort();
  }, [filmId, date]);
  useEffect(() => {
    setMap(null);
    if (!st) return;
    const ctl = new AbortController();
    get<unknown>(`/api/showtimes/${st.id}/seatmap`, ctl.signal).then((r) => !ctl.signal.aborted && r.ok && setMap(parseSeatMap(r.body)));
    return () => ctl.abort();
  }, [st]);

  const film = films?.find((f) => f.id === filmId) ?? null;
  const hall = st ? screenNumber(st.screen.name) : null;
  const pick = (id: number) => {
    if (id === filmId) return;
    setFilmId(id);
    setDate(null);
    setSt(null);
  };

  return (
    <section className="fr-immersive fr-browse">
      <aside className="fr-browse-rail" aria-label="Shows">
        <h1>Now showing</h1>
        {notice ? <div className="fr-banner" role="alert"><p>{notice}</p></div> : null}
        {failed ? <p className="fr-state">The listing could not be loaded.</p> : films === null ? null : films.length === 0 ? (
          <p className="fr-state">Nothing is showing right now.</p>
        ) : (
          <ul className="fr-browse-films">
            {films.map((f) => (
              <li key={f.id} className="fr-browse-film" data-open={f.id === filmId || undefined}>
                <button type="button" className="fr-browse-pick" aria-expanded={f.id === filmId} onClick={() => pick(f.id)}>
                  <Poster src={f.poster_url} title={f.title} />
                  <span>
                    <span className="fr-browse-title">{f.title}</span>
                    <span className="fr-meta">
                      <span className="fr-mono">{runtimeName(f.runtime_minutes)}</span>
                      <span className="fr-chip">{f.certification.name}</span>
                      <span>{f.language.name}</span>
                    </span>
                  </span>
                </button>
                {f.id === filmId ? <Times listed={listed} st={st} onPick={setSt} onDate={setDate} /> : null}
              </li>
            ))}
          </ul>
        )}
        <Link className="fr-browse-all" to="/films">All films, with filters</Link>
      </aside>
      <div className="fr-browse-stage">
        {hall ? <HallStage hallNo={hall} film={film} map={map} /> : <div className="fr-stage" />}
        {st && film ? (
          <div className="fr-browse-bar">
            <p>
              <span className="fr-browse-now">{film.title}</span>
              <span><span className="fr-mono">{timeLabel(st.starts_at)}</span> · {st.screen.name}</span>
            </p>
            {st.sales_closed ? <span className="fr-time-closed">Sales closed</span> : (
              <a className="fr-action" href={`/showtimes/${st.id}`} onClick={(e) => {
                if (e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
                e.preventDefault();
                navigate(`/showtimes/${st.id}`);
              }}>Choose your seats</a>
            )}
          </div>
        ) : null}
      </div>
    </section>
  );
}

function Times({ listed, st, onPick, onDate }: {
  listed: Listed | null; st: Showtime | null; onPick: (s: Showtime) => void; onDate: (d: string) => void;
}) {
  if (!listed) return <p className="fr-browse-note">Finding the times…</p>;
  const next = listed.next_date_with_showtimes;
  return (
    <div className="fr-browse-times">
      <p className="fr-browse-note">{dayLabel(listed.date)}</p>
      {listed.showtimes.length === 0 ? <p className="fr-browse-note">No showtimes on this date.</p> : (
        <div role="group" aria-label="Showtimes" className="fr-browse-slots">
          {listed.showtimes.map((s) => (
            <button key={s.id} type="button" className="fr-choice" aria-pressed={s.id === st?.id}
                    aria-label={showtimeName(s, formatPaise)} onClick={() => onPick(s)}>
              <span className="fr-mono">{timeLabel(s.starts_at)}</span> <span>{s.screen.name}</span>
            </button>
          ))}
        </div>
      )}
      {next && (listed.showtimes.length === 0 || listed.showtimes.every((s) => s.sales_closed)) ? (
        <button type="button" className="fr-clear" onClick={() => onDate(next)}>Next: {dayLabel(next)}</button>
      ) : null}
    </div>
  );
}

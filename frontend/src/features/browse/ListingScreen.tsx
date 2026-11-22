// SCR-BRW-01 · the movie listing, at `/films` since CR-004 (was `/`). Anyone, no account (P-BRW-05).
// The filters live in the URL query string, so a back navigation returns the same listing. The date strip is
// derived on the client from the injected clock and the display_until values of the films THIS response returned
// (P-BRW-04); each reference-backed control renders only when /api/reference holds two or more values for it.
// CR-011 F2: plus title, genre and minimum rating, applied here to the films the server returned (no extra request per
// keystroke), also kept in the URL. The filters sit in a left column; on phones they fold behind a "Filters" button.
import { useEffect, useMemo, useRef, useState } from "react";
import { navigate } from "../../router";
import { takeNotice } from "../auth/session";
import { get, query, type Film } from "./api";
import { ChoiceGroup, DayStrip } from "./DayStrip";
import { controlsFor, countLine, listingStrip, runtimeName, settleListing, type Reference } from "./logic";
import { Poster } from "./Poster";
import { BookmarkToggle, useSaved } from "../account/Bookmark";
import type { Saved } from "../account/account";
import { Genres, RatingBadge, releaseLabel } from "../discover/Bits";
import { genresOf, narrowFilms, ratingName, type Narrow } from "../discover/discover";
import "./browse.css";

// The one place these screens read the clock; tests and a harness pass their own `now`. Module-level, so it is
// the same function on every render and never re-triggers the effects that depend on it.
const wallClock = () => Date.now();

type Filters = { date: string | null; language_id: string | null; format_id: string | null; cinema_id: string | null };
const KEYS = ["date", "language_id", "format_id", "cinema_id"] as const;

function fromUrl(): Filters {
  const q = new URLSearchParams(window.location.search);
  return { date: q.get("date"), language_id: q.get("language_id"), format_id: q.get("format_id"), cinema_id: q.get("cinema_id") };
}
const NO_NARROW: Narrow = { q: null, genre_id: null, min_rating: null };
function narrowFromUrl(): Narrow {
  const q = new URLSearchParams(window.location.search);
  return { q: q.get("q"), genre_id: q.get("genre_id"), min_rating: q.get("min_rating") };
}
const MIN_RATINGS = ["6", "7", "8", "9"];

// The first state, for the render harness (react-dom/server runs no effect, so nothing is fetched there). A seeded
// `movies` is settled exactly as a response is. Production passes no seed.
type Seed = { filters?: Filters; narrow?: Narrow; movies?: Film[]; reference?: Reference | null; failed?: boolean };

export function ListingScreen({ now = wallClock, seed }: { now?: () => number; seed?: Seed }) {
  const [boot] = useState(() => {
    const f = seed?.filters ?? fromUrl();
    return seed?.movies ? settleListing(f, seed.movies.map((m) => m.display_until), now()) : { filters: f, announce: null };
  });
  const [filters, setFilters] = useState<Filters>(boot.filters);
  const [narrow, setNarrow] = useState<Narrow>(() => seed ? seed.narrow ?? NO_NARROW : narrowFromUrl());
  const [panel, setPanel] = useState(false); // phones: the filters column folded behind a button
  const [films, setFilms] = useState<Film[] | null>(seed?.movies ?? null);
  const [failed, setFailed] = useState(seed?.failed ?? false);
  const [reference, setReference] = useState<Reference | null | undefined>(seed?.reference);
  const [announce, setAnnounce] = useState(boot.announce ?? "");
  const [attempt, setAttempt] = useState(0);
  const [saved, toggle] = useSaved(); // CR-008 T4: one read of the saved set for every card
  const first = useRef(true);
  // One sentence another screen left for this one, read once (P-ACC-13 row 6: the showtime has gone).
  const [notice] = useState(() => {
    try {
      return takeNotice(window.sessionStorage);
    } catch {
      return null;
    }
  });

  useEffect(() => {
    get<Reference>("/api/reference").then((r) => setReference(r.ok ? r.body : null));
  }, []);

  useEffect(() => {
    window.history.replaceState(window.history.state, "", `/films${query({ ...filters, ...narrow })}${window.location.hash}`);
  }, [filters, narrow]);

  useEffect(() => {
    const controller = new AbortController();
    get<{ count: number; movies: Film[] }>(`/api/movies${query(filters)}`, controller.signal).then((r) => {
      if (controller.signal.aborted) return;
      if (!r.ok) {
        setFailed(true);
        return;
      }
      setFailed(false);
      setFilms(r.body.movies);
      // A filter that leaves the selected day outside the new strip drops it back to Any date (P-BRW-04).
      const settled = settleListing(filters, r.body.movies.map((m) => m.display_until), now());
      if (settled.announce) {
        setAnnounce(settled.announce);
        setFilters((f) => ({ ...f, date: null }));
        return;
      }
      if (!first.current) setAnnounce(countLine(r.body.count, "film", "showing"));
      first.current = false;
    });
    return () => controller.abort();
  }, [filters, attempt, now]);

  const shown = films ? narrowFilms(films, narrow) : null;
  const showing = shown?.filter((f) => !f.coming_soon) ?? [];
  const soon = shown?.filter((f) => f.coming_soon) ?? [];
  const genres = films ? genresOf(films) : [];
  // A #coming-soon link (the landing's See all) scrolls there once the films are on the page.
  useEffect(() => {
    if (films && window.location.hash) document.getElementById(window.location.hash.slice(1))?.scrollIntoView();
  }, [films]);
  const days = useMemo(() => (films ? listingStrip(now(), films.map((m) => m.display_until)) : []), [films, now]);
  const controls = reference === undefined ? controlsFor({ cinemas: [], languages: [], formats: [], certifications: [] }) : controlsFor(reference);
  const narrowed = Object.values(narrow).filter((v) => v).length;
  const anyFilter = KEYS.some((k) => filters[k] !== null) || narrowed > 0;
  const set = (key: keyof Filters, value: string | null) => setFilters((f) => ({ ...f, [key]: value || null }));
  const narrowBy = (key: keyof Narrow, value: string | null) => setNarrow((n) => ({ ...n, [key]: value || null }));
  const active = KEYS.filter((k) => filters[k] !== null).length + narrowed;

  return (
    <section className="fr-listing">
      {notice ? <div className="fr-banner" role="alert"><p>{notice}</p></div> : null}
      <h1 id="now-showing">Now showing</h1>
      <div className="fr-listing-layout">
      <div className="fr-listing-side">
      <button type="button" className="fr-action-secondary fr-filters-toggle" aria-expanded={panel} aria-controls="film-filters"
              onClick={() => setPanel((o) => !o)}>
        Filters{active ? ` (${active})` : ""}
      </button>
      <div role="group" aria-label="Filter what is showing" className="fr-filters" id="film-filters" data-open={panel ? "" : undefined}>
        <label className="fr-filter-search">
          <span>Title</span>
          <input type="search" value={narrow.q ?? ""} placeholder="Search titles" onChange={(e) => narrowBy("q", e.target.value)} />
        </label>
        {genres.length >= 2 ? (
          <ChoiceGroup label="Genre" className="fr-pick" selected={narrow.genre_id} onSelect={(v) => narrowBy("genre_id", v)}
                       choices={[{ value: null, label: "Any genre" }, ...genres.map((g) => ({ value: String(g.id), label: g.name }))]} />
        ) : null}
        <ChoiceGroup label="Rating" className="fr-pick" selected={narrow.min_rating} onSelect={(v) => narrowBy("min_rating", v)}
                     choices={[{ value: null, label: "Any rating" }, ...MIN_RATINGS.map((n) => ({ value: n, label: `★ ${n}+` }))]} />
        {days.length > 0 ? <DayStrip label="Date" days={days} selected={filters.date} anyDate onSelect={(d) => set("date", d)} /> : null}
        {controls.language && reference ? (
          <Pick label="Language" first="Any language" options={reference.languages} value={filters.language_id} onChange={(v) => set("language_id", v)} />
        ) : null}
        {controls.format && reference ? (
          <Pick label="Format" first="Any format" options={reference.formats} value={filters.format_id} onChange={(v) => set("format_id", v)} />
        ) : null}
        {controls.cinema && reference ? (
          <Pick label="Cinema" first="Any cinema" options={reference.cinemas} value={filters.cinema_id} onChange={(v) => set("cinema_id", v)} />
        ) : null}
        {anyFilter ? (
          <button type="button" className="fr-clear" onClick={() => {
            setFilters({ date: null, language_id: null, format_id: null, cinema_id: null });
            setNarrow(NO_NARROW);
          }}>
            Clear filters
          </button>
        ) : null}
      </div>
      {controls.unavailable ? <p className="fr-filters-down">Filters are unavailable right now.</p> : null}
      </div>
      <div className="fr-listing-main">
      <p className="fr-visually-hidden" aria-live="polite">{announce}</p>
      {failed ? (
        <div className="fr-state">
          <p>The listing could not be loaded.</p>
          <button type="button" className="fr-clear" onClick={() => setAttempt((n) => n + 1)}>Try again</button>
        </div>
      ) : films === null ? (
        <ul className="fr-cards" aria-hidden="true">
          {[0, 1, 2].map((i) => <li key={i} className="fr-card fr-card-loading"><div className="fr-poster" /></li>)}
        </ul>
      ) : shown!.length === 0 ? (
        <p className="fr-state">{anyFilter ? "Nothing is showing for the chosen filters." : "Nothing is showing right now."}</p>
      ) : (
        <>
          <ul className="fr-cards">
            {showing.map((m, i) => <Card key={m.id} film={m} index={i} saved={saved} toggle={toggle} />)}
          </ul>
          {/* CR-008 T10: films not out yet get their own section (the landing's Coming soon "See all" lands here) */}
          {soon.length ? (
            <section aria-labelledby="coming-soon" className="fr-listing-soon">
              <h2 id="coming-soon">Coming soon</h2>
              <ul className="fr-cards">
                {soon.map((m, i) => <Card key={m.id} film={m} index={showing.length + i} saved={saved} toggle={toggle} />)}
              </ul>
            </section>
          ) : null}
        </>
      )}
      </div>
      </div>
    </section>
  );
}

function Card({ film, index, saved, toggle }: { film: Film; index: number; saved: Saved; toggle: (id: number, s: boolean) => void }) {
  const name = `${film.title}, ${film.coming_soon ? "coming soon" : ratingName(film.rating)}, ${runtimeName(film.runtime_minutes)}, `
    + `${film.certification.name}, ${film.language.name}`;
  return (
    <li className="fr-card" style={{ ["--i" as string]: index, viewTransitionName: `film-${film.id}` }}>
      <a href={`/movies/${film.id}`} className="fr-card-link" aria-label={name} onClick={(e) => {
        if (e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
        e.preventDefault();
        navigate(`/movies/${film.id}`);
      }}>
        <Poster src={film.poster_url} title={film.title} />
        {/* CR-008 T12: the stars beside the title; T11: the genres under it */}
        <span className="fr-title-row">
          <h2 className="fr-card-title">{film.title}</h2>
          {film.coming_soon ? null : <RatingBadge rating={film.rating} />}
        </span>
        <Genres film={film} />
        <p className="fr-card-synopsis">{film.synopsis}</p>
        <p className="fr-meta">
          {film.coming_soon && film.release_date ? <span className="fr-tile-note">Opens {releaseLabel(film.release_date)}</span> : null}
          <span className="fr-mono">{film.runtime_minutes} min</span>
          <span className="fr-chip">{film.certification.name}</span>
          <span>{film.language.name}</span>
        </p>
      </a>
      {/* a sibling of the card's link, never inside it: one control per tab stop */}
      <BookmarkToggle movieId={film.id} title={film.title} state={saved} toggle={toggle} />
    </li>
  );
}

function Pick({ label, first, options, value, onChange }: {
  label: string; first: string; options: { id: number; name: string }[]; value: string | null; onChange: (v: string | null) => void;
}) {
  // A single-choice button group, not a <select>: the listing renders no select, listbox or combobox (S-BRW-03).
  return <ChoiceGroup label={label} className="fr-pick" selected={value} onSelect={onChange}
                      choices={[{ value: null, label: first }, ...options.map((o) => ({ value: String(o.id), label: o.name }))]} />;
}

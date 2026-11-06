// SCR-ADM-01 - every film, draft and published, with BOTH gates shown separately and never one "live" flag
// (FR-ADR-021). Paged by EP-ADM-01 (50 a page) with a readout that always renders. The poster box's words are decided
// by poster_present, never by whether the image arrived (no poster -> upload; could not load -> reload).
import { useEffect, useState } from "react";
import { Link, navigate } from "../../router";
import { api, errorText } from "./api";
import { readout, windowMark, type Film } from "./films";

type Status = "all" | "draft" | "published";
const PAGE = 50;
const FILTERS: { value: Status; label: string }[] = [
  { value: "all", label: "All films" },
  { value: "draft", label: "Drafts" },
  { value: "published", label: "Published" },
];

// The first state, for the render harness (react-dom/server runs no effect). Production passes no seed.
type Seed = { items: Film[]; total: number; offset?: number; status?: Status; failed?: number[] };

export function FilmsScreen({ seed }: { seed?: Seed }) {
  const [status, setStatus] = useState<Status>(seed?.status ?? "all");
  const [offset, setOffset] = useState(seed?.offset ?? 0);
  const [page, setPage] = useState<{ items: Film[]; total: number } | null>(seed ?? null);
  const [failed, setFailed] = useState<number[]>(seed?.failed ?? []);
  const [message, setMessage] = useState("");
  useEffect(() => {
    if (seed) return;
    setPage(null);
    const query = new URLSearchParams({ status, limit: String(PAGE), offset: String(offset) });
    api<{ items: Film[]; total: number }>("GET", `/api/admin/movies?${query}`).then(setPage, (e) => setMessage(errorText(e)));
  }, [status, offset]);
  const choose = (next: Status) => {
    setStatus(next);
    setOffset(0); // a filter change returns to the first page
  };

  return (
    <section className="admin">
      <h1>Films</h1>
      <p>
        <Link to="/admin/movies/new" className="admin-primary">New film</Link>
      </p>
      <fieldset className="admin-filter">
        <legend>Show</legend>
        {FILTERS.map((f) => (
          <label key={f.value}>
            <input type="radio" name="film-status" checked={status === f.value} onChange={() => choose(f.value)} /> {f.label}
          </label>
        ))}
      </fieldset>
      <p className="admin-help">A film appears to customers only when it is published and today is inside its display window. Both are needed.</p>
      {message ? <p role="alert">{message}</p> : null}
      {page === null && !message ? <ul className="admin-list" aria-busy="true">{[0, 1, 2, 3, 4, 5].map((i) => <li key={i} className="admin-row-loading" />)}</ul> : null}
      {page !== null && page.items.length === 0 && offset === 0 ? <p>No films yet. Create the first one.</p> : null}
      {page !== null && page.items.length > 0 ? (
        <ul className="admin-list">
          {page.items.map((film) => {
            const poster = !film.poster_present ? "No poster" : failed.includes(film.id) ? "Poster could not be loaded. Reload the page." : null;
            const label = [film.title, film.published ? "Published" : "Draft", windowMark(film).toLowerCase(),
              poster === null ? null : film.poster_present ? "poster could not be loaded" : "no poster"].filter(Boolean).join(", ");
            return (
              <li key={film.id}>
                <a href={`/admin/movies/${film.id}`} aria-label={label} className="admin-film"
                   onClick={(e) => {
                     if (e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return; // new tab keeps the browser's way
                     e.preventDefault();
                     navigate(`/admin/movies/${film.id}`);
                   }}>
                  <span className="admin-film-row">
                    <span className="admin-poster">
                      {poster === null ? (
                        <img src={`/api/admin/movies/${film.id}/poster`} alt="" onError={() => setFailed((f) => [...f, film.id])} />
                      ) : (
                        <span className={film.poster_present ? "admin-poster-failed" : "admin-help"}>{poster}</span>
                      )}
                    </span>
                    <span className="admin-film-title">{film.title}</span>
                    <span className={film.published ? "admin-help" : "admin-gate-fail"}>{film.published ? "Published" : "Draft"}</span>
                    <span className={film.window_open ? "admin-help" : "admin-gate-fail"}>{windowMark(film)}</span>
                    <span className="admin-help"><span className="admin-mono">{film.runtime_minutes} min</span> · {film.certification.name} · {film.language.name}</span>
                  </span>
                </a>
              </li>
            );
          })}
        </ul>
      ) : null}
      {page !== null ? (
        <nav className="admin-pager" aria-label="Pages">
          {offset > 0 ? <button type="button" onClick={() => setOffset(Math.max(0, offset - PAGE))}>Newer films</button> : null}
          <span className="admin-mono" aria-live="polite">{readout(offset, page.items.length, page.total)}</span>
          {offset + page.items.length < page.total ? <button type="button" onClick={() => setOffset(offset + PAGE)}>Older films</button> : null}
        </nav>
      ) : null}
    </section>
  );
}

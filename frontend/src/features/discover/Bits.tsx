// CR-008 T10-T13: small pieces the discovery screens share - the star badge beside every title, the poster tile of the
// landing rows, and the Share button (Web Share, else copy, else the link shown to copy by hand).
import { useState, type MouseEvent } from "react";
import { navigate } from "../../router";
import type { Film } from "../browse/api";
import { Poster } from "../browse/Poster";
import { ratingName, ratingText, SHARE_COPIED, SHARE_MANUAL, shareLink, type Rating, type Shared } from "./discover";
import "./discover.css";

/** T12: the star average beside a title, or "New" when nobody has rated it yet. */
export function RatingBadge({ rating }: { rating: Rating }) {
  const text = ratingText(rating);
  return (
    <span className="fr-stars" data-new={text === null ? "" : undefined} role="img" aria-label={ratingName(rating)}>
      {text === null ? "New" : <><span aria-hidden="true">★</span> {text}</>}
    </span>
  );
}

/** T11: the genres line under a title. Nothing at all for a film with no genre (S-BRW-02). */
export function Genres({ film }: { film: Pick<Film, "genres"> }) {
  return film.genres.length ? <p className="fr-genres">{film.genres.map((g) => g.name).join(" · ")}</p> : null;
}

function go(e: MouseEvent<HTMLAnchorElement>, to: string) {
  if (e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
  e.preventDefault();
  navigate(to);
}

/** A poster in a landing row: the poster, the title with its stars, the genres; Coming soon shows the date instead. */
export function FilmTile({ film }: { film: Film }) {
  const to = `/movies/${film.id}`;
  return (
    <li className="fr-tile">
      <a href={to} className="fr-tile-link" onClick={(e) => go(e, to)}>
        <Poster src={film.poster_url} title={film.title} />
        <span className="fr-tile-head">
          <span className="fr-tile-title">{film.title}</span>
          {film.coming_soon ? null : <RatingBadge rating={film.rating} />}
        </span>
        {film.coming_soon && film.release_date ? <span className="fr-tile-note">Opens {releaseLabel(film.release_date)}</span> : null}
        <Genres film={film} />
      </a>
    </li>
  );
}

const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];

/** `4 December 2026` from 2026-12-04 - a calendar date, no zone arithmetic. */
export function releaseLabel(isoDate: string): string {
  return `${Number(isoDate.slice(8, 10))} ${MONTHS[Number(isoDate.slice(5, 7)) - 1]} ${isoDate.slice(0, 4)}`;
}

/** T13c: one status for the share flow; the outcome is announced politely. */
export function ShareButton({ title, text, path, label = "Share" }: { title: string; text: string; path: string; label?: string }) {
  const [state, setState] = useState<Shared>({ kind: "idle" });
  // No guard while "sharing": a share sheet that never settles (some browsers) must not trap the button
  // (web-app-pitfalls rule 2). A second press while one is open makes share() refuse, and the link is copied instead.
  const press = async () => {
    const url = new URL(path, window.location.href).href; // read at the press, never during render
    setState({ kind: "sharing" });
    setState(await shareLink(navigator, { title, text, url }));
  };
  return (
    <span className="fr-share">
      <button type="button" className="fr-action-secondary fr-share-button" aria-busy={state.kind === "sharing" || undefined}
              onClick={() => void press()}>
        <span aria-hidden="true">↗</span> {label}
      </button>
      <span role="status" className="fr-share-note">
        {state.kind === "copied" ? SHARE_COPIED : state.kind === "manual" ? SHARE_MANUAL : ""}
      </span>
      {state.kind === "manual" ? (
        <input className="fr-share-url" readOnly value={state.url} aria-label="Link to share" onFocus={(e) => e.currentTarget.select()} />
      ) : null}
    </span>
  );
}

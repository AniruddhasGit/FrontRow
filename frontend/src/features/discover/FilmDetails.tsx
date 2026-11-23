// CR-008 T12: the film page's full details (description, genres, runtime, certificate, language, release date, cast,
// crew) and its ratings (average, count, the 1-10 breakdown) with the viewer's own control: rate 1-10 a released film
// (CR-013: any signed-in customer; the server decides, EP-ACC-20), or like a film that is coming soon (EP-ACC-21).
// One status for the viewer's half (Mine) and one for a write (Write); no timer, no poll.
// CR-011 F3/F4: cast and crew as wrapping portrait tiles (initials, no photos), the review form beside the score, and the
// film's reviews under the ratings (Reviews.tsx). CR-013: "Your rating" sits at the top of the reviews (#film-rate); for a
// coming-soon film (no reviews) the Like stays in the ratings box under the same id.
import { useEffect, useState } from "react";
import { get, send, type FilmDetail } from "../browse/api";
import { runtimeName } from "../browse/logic";
import { signInHref } from "../auth/session";
import { Link } from "../../router";
import { releaseLabel } from "./Bits";
import { initials, ratingName, ratingText, reviewText } from "./discover";
import { Reviews } from "./Reviews";

type Me = { score: number | null; can_rate: boolean; liked: boolean; coming_soon: boolean;
            review: string | null; review_id: number | null; voted: number[] };
type Mine = { kind: "loading" } | { kind: "guest" } | { kind: "error" } | { kind: "ready"; me: Me };
type Write = { kind: "idle" } | { kind: "saving" } | { kind: "failed"; message: string };

export function FilmDetails({ film, onChanged }: { film: FilmDetail; onChanged: (f: FilmDetail) => void }) {
  const [mine, setMine] = useState<Mine>({ kind: "loading" });
  const [write, setWrite] = useState<Write>({ kind: "idle" });
  const [draft, setDraft] = useState<string | null>(null); // the review form's text while it is open
  const [posted, setPosted] = useState(0); // bumped after a review is saved, so the list re-reads once
  useEffect(() => {
    const ctl = new AbortController();
    void get<Me>(`/api/me/movies/${film.id}`, AbortSignal.any([ctl.signal, AbortSignal.timeout(15000)])).then((r) => {
      if (ctl.signal.aborted) return;
      setMine(r.ok ? { kind: "ready", me: r.body } : r.status === 401 ? { kind: "guest" } : { kind: "error" });
    });
    return () => ctl.abort();
  }, [film.id]);

  const rate = async (score: number) => {
    if (mine.kind !== "ready" || write.kind === "saving") return;
    setWrite({ kind: "saving" });
    const r = await send<{ score: number; rating: FilmDetail["rating"] }>("PUT", `/api/me/ratings/${film.id}`, { score });
    if (!r.ok) return setWrite({ kind: "failed", message: r.message || "Your rating was not saved. Try again." });
    setWrite({ kind: "idle" });
    setMine({ kind: "ready", me: { ...mine.me, score: r.body.score } });
    onChanged({ ...film, rating: r.body.rating });
  };
  const review = async () => {
    if (mine.kind !== "ready" || !mine.me.score || draft === null || write.kind === "saving") return;
    const t = reviewText(draft);
    if (!t.ok) return setWrite({ kind: "failed", message: t.message });
    setWrite({ kind: "saving" });
    const r = await send<{ review_id: number; score: number; text: string; rating: FilmDetail["rating"] }>(
      "PUT", `/api/me/reviews/${film.id}`, { score: mine.me.score, text: t.text });
    if (!r.ok) return setWrite({ kind: "failed", message: r.message || "Your review was not saved. Try again." });
    setWrite({ kind: "idle" });
    setDraft(null);
    setMine({ kind: "ready", me: { ...mine.me, review: r.body.text, review_id: r.body.review_id } });
    setPosted((n) => n + 1);
    onChanged({ ...film, rating: r.body.rating });
  };
  const like = async () => {
    if (mine.kind !== "ready" || write.kind === "saving") return;
    setWrite({ kind: "saving" });
    const r = await send<{ liked: boolean; likes: number }>("PUT", `/api/me/likes/${film.id}`, { liked: !mine.me.liked });
    if (!r.ok) return setWrite({ kind: "failed", message: r.message || "That did not save. Try again." });
    setWrite({ kind: "idle" });
    setMine({ kind: "ready", me: { ...mine.me, liked: r.body.liked } });
    onChanged({ ...film, likes: r.body.likes });
  };

  const facts: [string, string][] = [
    ["Runtime", runtimeName(film.runtime_minutes)], ["Certificate", film.certification.name], ["Language", film.language.name],
    ["Release date", film.release_date ? releaseLabel(film.release_date) : "Not announced"],
    ["Genres", film.genres.length ? film.genres.map((g) => g.name).join(", ") : "None listed"],
  ];
  const mineBlock = (
    <div className="fr-my" id="film-rate">
      <h3>{film.coming_soon ? "Want to see it?" : "Your rating"}</h3>
      {mine.kind === "loading" ? <p>Checking your account…</p>
        : mine.kind === "error" ? <p>Your rating cannot be loaded right now.</p>
        : mine.kind === "guest" ? (
          <p><Link to={signInHref(`/movies/${film.id}`)}>Sign in</Link> {film.coming_soon ? "to like this film." : "to rate and review it."}</p>
        ) : film.coming_soon ? (
          <button type="button" className="fr-action-secondary fr-like" aria-pressed={mine.me.liked}
                  disabled={write.kind === "saving"} onClick={() => void like()}>
            <span aria-hidden="true">{mine.me.liked ? "♥" : "♡"}</span> {mine.me.liked ? "Liked" : "Like"}
          </button>
        ) : mine.me.can_rate ? (
          <>
            <p>{mine.me.score ? `You gave it ${mine.me.score}. Choose again to change it.` : "How was it? Choose a score."}</p>
            <div role="group" aria-label="Rate this film from 1 to 10" className="fr-scores">
              {Array.from({ length: 10 }, (_, i) => i + 1).map((n) => (
                <button key={n} type="button" className="fr-choice" aria-pressed={mine.me.score === n} aria-label={`${n} out of 10`}
                        disabled={write.kind === "saving"} onClick={() => void rate(n)}>{n}</button>
              ))}
            </div>
            {/* CR-011 F4: the review goes with the score; editing reopens the same form */}
            {!mine.me.score ? null : draft === null ? (
              <button type="button" className="fr-action-secondary fr-review-open" onClick={() => setDraft(mine.me.review ?? "")}>
                {mine.me.review ? "Edit your review" : "Write a review"}
              </button>
            ) : (
              <form className="fr-review-form" onSubmit={(e) => { e.preventDefault(); void review(); }}>
                <label htmlFor="review-text">Your review ({mine.me.score} out of 10)</label>
                <textarea id="review-text" rows={4} maxLength={2000} value={draft} onChange={(e) => setDraft(e.target.value)} />
                <div className="fr-review-actions">
                  <button type="submit" className="fr-action" disabled={write.kind === "saving"}>Post review</button>
                  <button type="button" className="fr-action-secondary" onClick={() => setDraft(null)}>Cancel</button>
                </div>
              </form>
            )}
          </>
        ) : <p>Ratings open once the film is out.</p>}
      <p role="status" className="fr-share-note">{write.kind === "failed" ? write.message : write.kind === "saving" ? "Saving…" : ""}</p>
    </div>
  );
  const most = Math.max(1, ...film.rating.breakdown);
  const avg = ratingText(film.rating);
  return (
    <div className="fr-film-details">
      <section aria-labelledby="about-film">
        <h2 id="about-film">About the film</h2>
        <p className="fr-movie-synopsis">{film.synopsis || "No description yet."}</p>
        <dl className="fr-facts">{facts.map(([k, v]) => <div key={k}><dt>{k}</dt><dd>{v}</dd></div>)}</dl>
        <People id="film-cast" title="Cast" people={film.cast} />
        <People id="film-crew" title="Crew" people={film.crew} />
      </section>
      <section className="fr-ratings" aria-labelledby="film-ratings">
        <h2 id="film-ratings">{film.coming_soon ? "Before it opens" : "Ratings"}</h2>
        {film.coming_soon ? (
          <p className="fr-ratings-score"><span className="fr-ratings-big">{film.likes}</span>
            <span className="fr-ratings-count">{film.likes === 1 ? "person wants" : "people want"} to see it</span></p>
        ) : (
          <>
            <p className="fr-ratings-score" aria-label={ratingName(film.rating)}>
              <span className="fr-ratings-big" aria-hidden="true">{avg ? `★ ${avg}` : "New"}</span>
              <span className="fr-ratings-count" aria-hidden="true">
                {film.rating.count ? `out of 10 · ${film.rating.count} ${film.rating.count === 1 ? "rating" : "ratings"}` : "No ratings yet"}
              </span>
            </p>
            <ol className="fr-bars" aria-label="How people scored it" reversed>
              {[...film.rating.breakdown].map((n, i) => ({ n, score: i + 1 })).reverse().map(({ n, score }) => (
                <li key={score} aria-label={`${score} out of 10: ${n} ${n === 1 ? "rating" : "ratings"}`}>
                  <span className="fr-mono" aria-hidden="true">{score}</span>
                  <span className="fr-bar" aria-hidden="true"><span style={{ width: `${(100 * n) / most}%` }} /></span>
                  <span className="fr-mono" aria-hidden="true">{n}</span>
                </li>
              ))}
            </ol>
          </>
        )}
        {film.coming_soon ? mineBlock : null}
      </section>
      {film.coming_soon ? null : (
        <Reviews filmId={film.id} version={posted} me={mine.kind === "ready" ? mine.me : null} signedIn={mine.kind === "ready"}>
          {mineBlock}
        </Reviews>
      )}
    </div>
  );
}

function People({ id, title, people }: { id: string; title: string; people: FilmDetail["cast"] }) {
  if (!people.length) return null;
  return (
    <>
      <h2 id={id}>{title}</h2>
      <ul className="fr-people" aria-labelledby={id}>
        {people.map((p, i) => (
          <li key={`${p.name}-${i}`}>
            <span className="fr-avatar" aria-hidden="true">{initials(p.name)}</span>
            <strong>{p.name}</strong>{p.role ? <span>{p.role}</span> : null}
          </li>
        ))}
      </ul>
    </>
  );
}

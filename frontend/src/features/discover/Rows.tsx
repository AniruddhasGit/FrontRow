// CR-008 T10 + T13a/d: what sits under the landing's hall - the featured hero, Top rated, Now showing, Coming soon and
// Recently viewed. Every row is a wrapping poster grid (T16: nothing scrolls sideways) built from the one /api/movies
// read the landing already made; Recently viewed is this browser's own list (discover.ts recentStore, try/catch).
// "Top rated" is the owner's first row ("... (top rated)"): the same order for everyone, by the stars customers gave.
import { useEffect, useReducer, useRef, useState, type MouseEvent } from "react";
import { navigate } from "../../router";
import type { Film } from "../browse/api";
import { Poster } from "../browse/Poster";
import { runtimeName } from "../browse/logic";
import { FilmTile, Genres, RatingBadge, releaseLabel } from "./Bits";
import { carousel, featured, readRecent, recentFilms, recentStore, ROW_SIZE, rows, turning } from "./discover";

const TURN_MS = 7000;

function go(e: MouseEvent<HTMLAnchorElement>, to: string) {
  if (e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
  e.preventDefault();
  navigate(to);
}

export function Discover({ films }: { films: Film[] }) {
  const { top, now, soon } = rows(films);
  const [recent] = useState(() => readRecent(recentStore()));
  const viewed = recentFilms(recent, films);
  return (
    <section className="fr-discover" aria-label="Discover films">
      <Hero films={featured(films)} />
      {top.length ? <Row id="top-rated" title="Top rated" note="Highest scores from people who saw them here." films={top} all="/films" /> : null}
      <Row id="now-showing-row" title="Now showing" note={`${now.length} ${now.length === 1 ? "film" : "films"} with shows this week.`}
           films={now} all="/films" />
      {soon.length ? <Row id="coming-soon-row" title="Coming soon" note="Like one to show it is wanted." films={soon} all="/films#coming-soon" /> : null}
      {viewed.length ? <Row id="recently-viewed" title="Recently viewed" note="On this device." films={viewed} /> : null}
    </section>
  );
}

function Row({ id, title, note, films, all }: { id: string; title: string; note: string; films: Film[]; all?: string }) {
  return (
    <section aria-labelledby={id}>
      <div className="fr-row-head">
        <h2 id={id}>{title}</h2>
        <p>{note}</p>
        {all && films.length > ROW_SIZE ? (
          <a className="fr-see-all" href={all} aria-label={`See all: ${title}`} onClick={(e) => go(e, all)}>See all →</a>
        ) : null}
      </div>
      <ul className="fr-tiles">{films.slice(0, ROW_SIZE).map((f) => <FilmTile key={f.id} film={f} />)}</ul>
    </section>
  );
}

/** T13a: one slide at a time, cross-faded inside a clipped box. Turns every 7 s only while nothing holds it: it waits
 *  while the pointer is over it, focus is inside it, the tab is hidden or it is off-screen, and it never turns under
 *  reduced motion or after Pause (WCAG 2.2.2). Prev / next and the dots always work. */
function Hero({ films }: { films: Film[] }) {
  const reduced = typeof matchMedia === "function" && matchMedia("(prefers-reduced-motion: reduce)").matches;
  const [s, dispatch] = useReducer(carousel, { index: 0, count: films.length, stopped: reduced, holds: [] });
  const box = useRef<HTMLElement>(null);
  useEffect(() => dispatch({ type: "count", count: films.length }), [films.length]);
  useEffect(() => {
    const vis = () => dispatch({ type: document.hidden ? "hold" : "release", why: "hidden" });
    document.addEventListener("visibilitychange", vis);
    const seen = new IntersectionObserver(([e]) => dispatch({ type: e.isIntersecting ? "release" : "hold", why: "offscreen" }));
    if (box.current) seen.observe(box.current);
    return () => {
      document.removeEventListener("visibilitychange", vis);
      seen.disconnect();
    };
  }, []);
  const playing = turning(s);
  useEffect(() => {
    if (!playing) return;
    const t = window.setTimeout(() => dispatch({ type: "tick" }), TURN_MS); // client-side only; re-armed per slide
    return () => window.clearTimeout(t);
  }, [playing, s.index]);
  if (!films.length) return null;
  return (
    <section ref={box} className="fr-hero" aria-roledescription="carousel" aria-label="Featured films"
             onPointerEnter={() => dispatch({ type: "hold", why: "hover" })} onPointerLeave={() => dispatch({ type: "release", why: "hover" })}
             onFocus={() => dispatch({ type: "hold", why: "focus" })}
             onBlur={(e) => !e.currentTarget.contains(e.relatedTarget as Node | null) && dispatch({ type: "release", why: "focus" })}>
      <div className="fr-hero-slides" aria-live={playing ? "off" : "polite"}>
        {films.map((f, i) => (
          <article key={f.id} className="fr-hero-slide" data-current={i === s.index ? "" : undefined} aria-hidden={i !== s.index}
                   aria-roledescription="slide" aria-label={`${i + 1} of ${films.length}: ${f.title}`}
                   inert={i !== s.index}>
            <div className="fr-hero-glow" style={{ backgroundImage: `url(${f.poster_url})` }} aria-hidden="true" />
            <Poster src={f.poster_url} title={f.title} />
            <div>
              <p className="fr-hero-kicker">Featured · {f.rating.count ? "Top rated" : "Now showing"}</p>
              <h2 className="fr-hero-title">{f.title}</h2>
              <p className="fr-hero-meta">
                <RatingBadge rating={f.rating} />
                <span className="fr-mono">{runtimeName(f.runtime_minutes)}</span>
                <span className="fr-chip">{f.certification.name}</span>
                {f.release_date ? <span>Out {releaseLabel(f.release_date)}</span> : null}
              </p>
              <Genres film={f} />
              <p className="fr-hero-synopsis">{f.synopsis}</p>
              <a className="fr-hero-cta" href={`/movies/${f.id}`} onClick={(e) => go(e, `/movies/${f.id}`)}>Showtimes and details</a>
            </div>
          </article>
        ))}
      </div>
      {films.length > 1 ? (
        <div className="fr-hero-controls">
          <button type="button" aria-label="Previous film" onClick={() => dispatch({ type: "prev" })}>←</button>
          <button type="button" aria-label="Next film" onClick={() => dispatch({ type: "next" })}>→</button>
          <div className="fr-hero-dots">
            {films.map((f, i) => (
              <button key={f.id} type="button" className="fr-hero-dot" aria-label={`Show film ${i + 1} of ${films.length}`}
                      aria-current={i === s.index} onClick={() => dispatch({ type: "go", index: i })} />
            ))}
          </div>
          <button type="button" aria-label={s.stopped ? "Play the featured films" : "Pause the featured films"}
                  onClick={() => dispatch({ type: s.stopped ? "play" : "stop" })}>{s.stopped ? "▶" : "❚❚"}</button>
        </div>
      ) : null}
    </section>
  );
}

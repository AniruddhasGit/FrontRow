// The home hero (the Main wireframe): the hall with the house lights down, above the listing. Pure markup and CSS:
// no three.js here, so the home page never loads the 3D bundle (FR-ADR-074 5: 3D only on the seat page).
// The art is /art/hero.jpg when that file is deployed, drawn over a CSS room (screen glow, seat silhouettes) that
// shows through whenever it is not (browse.css .fr-hero-art).
import { Link } from "../../router";
import type { Film } from "./api";

export function Hero({ film }: { film: Film | null }) {
  return (
    <section className="fr-hero" aria-label="Tonight in the hall">
      <div className="fr-hero-art" aria-hidden="true">
        <div className="fr-hero-screen"><span>{film?.title ?? ""}</span></div>
        <div className="fr-hero-seats" />
      </div>
      <div className="fr-hero-copy">
        <div>
          <p className="fr-hero-eyebrow">Tonight in the hall</p>
          <p className="fr-hero-title">See the room.<br />Then choose your seat.</p>
          <p className="fr-hero-lede">Every showtime opens in its hall. Walk the rows, sit down, look at the screen from there, then hold it.</p>
        </div>
        <div className="fr-hero-actions">
          <a className="fr-action" href="#now-showing">Tonight's showtimes</a>
          {film ? <Link className="fr-action-secondary" to={`/movies/${film.id}`}>Tour the hall</Link> : null}
        </div>
      </div>
    </section>
  );
}

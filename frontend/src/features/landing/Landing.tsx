// CR-004: the landing page at `/`. You are already sitting in one of the six halls, facing the screen, with the
// first film showing on it. From here: browse the shows (each opens in its own hall) or look round every hall.
import { useEffect, useState } from "react";
import { Link } from "../../router";
import { get, type Film } from "../browse/api";
import { ChoiceGroup } from "../browse/DayStrip";
import { HallStage } from "../hall3d/HallStage";

const HALLS = [1, 2, 3, 4, 5, 6];

export function Landing() {
  const [hall, setHall] = useState(1);
  const [film, setFilm] = useState<Film | null>(null);
  useEffect(() => {
    get<{ movies: Film[] }>("/api/movies").then((r) => r.ok && setFilm(r.body.movies[0] ?? null));
  }, []);

  return (
    <section className="fr-immersive fr-landing">
      <HallStage hallNo={hall} film={film} fallback={<div className="fr-landing-glow" />} />
      <div className="fr-landing-copy">
        <p className="fr-hero-eyebrow">FrontRow · six halls, one theatre</p>
        <h1>Your seat is already waiting.</h1>
        <p className="fr-landing-lede">Every show opens in its own hall. Look around, sit anywhere, then choose your seat.</p>
        <div className="fr-landing-actions">
          <Link className="fr-action" to="/browse">Browse the shows</Link>
        </div>
        <ChoiceGroup label="See every hall" className="fr-strip fr-landing-halls" selected={String(hall)}
                     onSelect={(v) => v && setHall(Number(v))} choices={HALLS.map((n) => ({ value: String(n), label: `Hall ${n}` }))} />
      </div>
    </section>
  );
}

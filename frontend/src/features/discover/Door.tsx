// CR-011 F5/F6 (owner: "a door which is half open which has enter written on top like a theatre door, and as soon as the
// person hits that door then the animation that we already have kicks in"): the chosen show's door. A real <button>
// named for the show; ENTER lit above it, the screen and time on its plate; hover or focus swings it a little wider.
// Pressing it swings it open and floods the page with the hall's light, then the seat page opens and its hall plays the
// walk-in (WALKIN, read once by Hall3D). One status (discover.ts Door); the exit is a timer, so it can never stick.
// Reduced motion: no swing, no flood - straight to the seat page, whose hall then cuts to the seats.
import { useEffect, useState } from "react";
import { navigate } from "../../router";
import { timeLabel } from "../browse/logic";
import { nextHallDrawn, WALKIN } from "../hall3d/hallReady";
import { adultsOnly, DOOR_OPEN_MS, pressDoor, type Door } from "./discover";
import "./door.css";

type Show = { id: number; starts_at: string; screen: { id: number; name: string }; sales_closed: boolean };

function walkIn(showtimeId: number) {
  try {
    window.sessionStorage.setItem(WALKIN, String(showtimeId));
  } catch {
    // no storage: the seat page plays its own arrival instead
  }
  navigate(`/showtimes/${showtimeId}`, nextHallDrawn());
}

export function TheatreDoor({ show, film, now }: { show: Show; film: { title: string; certification: { name: string } }; now: number }) {
  const [door, setDoor] = useState<Door>({ kind: "closed" });
  useEffect(() => setDoor({ kind: "closed" }), [show.id]);
  useEffect(() => {
    if (door.kind !== "opening") return;
    const t = window.setTimeout(() => walkIn(door.showtimeId), DOOR_OPEN_MS);
    return () => window.clearTimeout(t);
  }, [door]);
  const at = timeLabel(show.starts_at);
  const press = () => {
    if (matchMedia("(prefers-reduced-motion: reduce)").matches) return walkIn(show.id);
    setDoor((d) => pressDoor(d, show.id));
  };
  const started = Date.parse(show.starts_at) <= now;
  return (
    <section className="fr-door-scene" aria-labelledby="door-title" data-door={door.kind}>
      <h2 id="door-title" className="fr-visually-hidden">Your show: {show.screen.name}, {at}</h2>
      <div className="fr-door-wall">
        <p className="fr-door-sign"><span>ENTER</span></p>
        <button type="button" className="fr-door" aria-label={`Enter ${show.screen.name} for ${film.title} at ${at}`}
                onClick={press} disabled={door.kind === "opening"}>
          <span className="fr-door-glow" aria-hidden="true" />
          <span className="fr-door-leaf" aria-hidden="true">
            <span className="fr-door-pane" />
            <span className="fr-door-bar" />
          </span>
          <span className="fr-door-spill" aria-hidden="true" />
        </button>
        <p className="fr-door-plate"><span className="fr-door-screen">{show.screen.name}</span> · <span className="fr-mono">{at}</span></p>
      </div>
      <div className="fr-door-notes">
        <p className="fr-door-hint">{door.kind === "opening" ? "Walking in…" : "Push the door to walk in and choose your seats."}</p>
        {started ? <p className="fr-door-note">This show started at {at}. Seats stay on sale until sales close.</p> : null}
        {adultsOnly(film.certification.name)
          ? <p className="fr-door-note">Rated {film.certification.name}: adults only. Carry a photo ID to the show.</p> : null}
      </div>
      <span className="fr-door-wash" aria-hidden="true" />
    </section>
  );
}

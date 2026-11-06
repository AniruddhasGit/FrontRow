// The 3D hall on the seat page (FR-ADR-074, CR-001 Part B): a presentation layer over the 2D map, which stays
// complete beneath it. This file is small and loads with the seat page; three.js and the scene load only when
// this mounts, through the lazy import below.
// Shown only when it can work: WebGL present, a screen at least 48rem wide. Otherwise, or when the scene fails to
// load or throws, this renders nothing and the 2D map alone carries the page - nothing is lost. It renders nothing on
// the first render too (the decision is an effect), so the server-side render harness sees the 2D page unchanged.
// ponytail: the width is checked once on mount; resizing below it later keeps the scene. Upgrade: a matchMedia listener.
import { Component, Suspense, lazy, useEffect, useState, type ReactNode } from "react";
import { seatName, visualOf, type Seat, type SeatMap, type Visual } from "../seatmap/model";
import type { Mode } from "./hall";
import "./hall3d.css";

const HallScene = lazy(() => import("./HallScene"));

const MODES: [Mode, string][] = [["overview", "Hall overview"], ["seat", "View from my seat"], ["screen", "From the screen"]];

function canDraw(): boolean {
  if (!window.matchMedia("(min-width: 48rem)").matches) return false;
  try {
    const canvas = document.createElement("canvas");
    const gl = canvas.getContext("webgl2") ?? canvas.getContext("webgl");
    gl?.getExtension("WEBGL_lose_context")?.loseContext(); // a probe only: give the context straight back
    return Boolean(gl);
  } catch {
    return false;
  }
}

class Guard extends Component<{ children: ReactNode; onFail: () => void }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  componentDidCatch() {
    this.props.onFail();
  }
  render() {
    return this.state.failed ? null : this.props.children;
  }
}

export function Hall3D({ map, mine, onTap }: {
  map: SeatMap | null; mine: ReadonlySet<number>; onTap: (seat: Seat, visual: Visual) => void;
}) {
  const [able, setAble] = useState(false);
  const [on, setOn] = useState(true);
  const [mode, setMode] = useState<Mode>("overview");
  const [hover, setHover] = useState<Seat | null>(null);
  useEffect(() => setAble(canDraw()), []);
  if (!able || !map) return null;

  if (!on) {
    return (
      <div className="fr-hall3d-off">
        <button type="button" className="fr-action-secondary" onClick={() => setOn(true)}>Show the hall in 3D</button>
      </div>
    );
  }
  const category = new Map(map.categories.map((c) => [c.id, c.name]));
  const first = map.seats.find((s) => s.id === mine.values().next().value);
  const caption = hover
    ? seatName(hover, category.get(hover.cat) ?? "", visualOf(hover, mine))
    : mode === "seat"
      ? (first ? `Your view from row ${first.row}, seat ${first.num}.` : "Choose a seat to see the screen from it.")
      : mode === "screen" ? "Looking back at the hall from the screen." : "Tap a seat here or on the map below. Both stay in step.";

  return (
    <section className="fr-hall3d" aria-label="The hall in 3D">
      <div className="fr-hall3d-bar">
        <div role="group" aria-label="Camera" className="fr-hall3d-modes">
          {MODES.map(([m, label]) => (
            <button key={m} type="button" className="fr-choice" aria-pressed={mode === m} onClick={() => setMode(m)}>{label}</button>
          ))}
        </div>
        <button type="button" className="fr-action-secondary" onClick={() => setOn(false)}>Use the 2D map only</button>
      </div>
      <div className="fr-hall3d-stage" aria-hidden="true">
        <Guard onFail={() => setAble(false)}>
          <Suspense fallback={null}>
            <HallScene map={map} mine={mine} mode={mode} onTap={onTap} onHover={setHover} />
          </Suspense>
        </Guard>
        <p className="fr-hall3d-name">{map.screen.name} <span className="fr-mono">{map.seats.length}</span> seats</p>
        <p className="fr-hall3d-caption">{caption}</p>
      </div>
    </section>
  );
}

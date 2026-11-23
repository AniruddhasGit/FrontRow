// The 3D hall on the seat page (FR-ADR-074, CR-001 Part B): a presentation layer over the 2D map, which stays
// complete beneath it. This file is small and loads with the seat page; three.js and the scene load lazily, in the
// app's one hall (host.tsx, CR-014): this page says what it wants of it and gives it a slot, so a hall already up
// from the film page's corridor carries straight on here.
// Shown only when it can work: WebGL present (phones included, CR-003). Otherwise, or when the scene fails to
// load or throws, this renders nothing and the 2D map alone carries the page - nothing is lost. The WebGL check runs
// in the first render (2026-11-23): deciding it in an effect drew the panel full width for one frame, then pushed it
// into its column (CLS 0.68). The server-side render harness has no document, so it still sees the 2D page.
import { Component, useCallback, useLayoutEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { formatPaise } from "../admin/money";
import { seatLabel, selectable, visualOf, type Seat, type SeatMap, type Visual } from "../seatmap/model";
import { screenFirst, screenNumber, seatTip, stateWord, type BakedMeta, type Mode } from "./hall";
import type { Film } from "./HallScene";
import { WALKIN } from "./hallReady";
import { HallSlot, takeWalked, useHall, useHostView } from "./host";
import { NO_COVER, type Cover } from "./walk";
import "./hall3d.css";

const MODES: [Mode, string][] = [["all", "All seats"], ["seat", "From my seat"]];
/** Set by the landing just before it hands over to this page (CR-005). */
export const FLOWN = "fr.flown";

export function canDraw(): boolean {
  try {
    const canvas = document.createElement("canvas");
    const gl = canvas.getContext("webgl2") ?? canvas.getContext("webgl");
    gl?.getExtension("WEBGL_lose_context")?.loseContext(); // a probe only: give the context straight back
    return Boolean(gl);
  } catch {
    return false;
  }
}

export class Guard extends Component<{ children: ReactNode; onFail: () => void }, { failed: boolean }> {
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

export function Hall3D({ map, film, mine, onTap, showtimeId: page }: {
  /** `film` undefined: the showtime's header has not arrived yet; the hall waits for it (readiness.ts) */
  map: SeatMap | null; film?: Film | null; mine: ReadonlySet<number>; onTap: (seat: Seat, visual: Visual) => void;
  /** this page's showtime (CR-014: did the film page's walk just bring the visitor here?) */
  showtimeId?: number;
}) {
  const [able] = useState(canDraw);
  const [on, setOn] = useState(true);
  const [mode, setMode] = useState<Mode>("all");
  const [picked, setPicked] = useState<number | null>(null); // the seat last clicked in 3D, whose view is shown
  const [preview, setPreview] = useState<string | null>(null);
  const [hover, setHover] = useState<Seat | null>(null);
  const [moving, setMoving] = useState(false);
  const tip = useRef<HTMLDivElement>(null);
  // CR-004: the visitor arrives seated, facing their film on the screen, then the camera turns onto the seats.
  // CR-005: coming from the landing's pan (it leaves fr.flown = this showtime), the camera is already over the seats.
  const [flown] = useState(() => {
    try {
      const v = window.sessionStorage.getItem(FLOWN);
      window.sessionStorage.removeItem(FLOWN);
      return v;
    } catch {
      return null;
    }
  });
  // CR-011 F6: through the film page's door (it leaves fr.walkin = this showtime), the hall plays the walk-in: the baked
  // route from the ENTRY door to the seats (meta.intro), not the seated arrival.
  const [walked] = useState(() => {
    try {
      const v = window.sessionStorage.getItem(WALKIN);
      window.sessionStorage.removeItem(WALKIN);
      return v;
    } catch {
      return null;
    }
  });
  const showtimeId = map?.showtime.id;
  const hallNo = map ? screenNumber(map.screen.name) : null;
  // CR-014: the page under the panel (hall3d.css: the stage runs on under it) - the hall is framed in the part you see
  const box = useRef<HTMLElement>(null);
  const [cover, setCover] = useState<Cover>(NO_COVER);
  useLayoutEffect(() => {
    const el = box.current;
    const stage = el?.querySelector(".fr-hall3d-stage");
    if (!el || !stage) return;
    const measure = () => {
      const a = el.getBoundingClientRect(), b = stage.getBoundingClientRect();
      const next = { right: Math.max(0, Math.round(b.right - a.right)), bottom: Math.max(0, Math.round(b.bottom - a.bottom)) };
      setCover((c) => (c.right === next.right && c.bottom === next.bottom ? c : next));
    };
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    ro.observe(stage);
    return () => ro.disconnect();
  }, [on]);
  const onMoving = useCallback((m: boolean) => {
    setMoving(m);
    if (m) setHover(null); // the seat under the pointer is about to change
  }, []);
  // CR-004/005/011: the arrival when the hall first shows on this page (not when it walked in from the film page)
  const host = useHostView(); // the hall that is up
  const meta = host.hall === hallNo ? host.meta : undefined;
  const intro = useMemo(() => (!meta?.seats?.length ? null : flown !== null && String(showtimeId) === flown ? null
    : walked !== null && String(showtimeId) === walked && meta.intro?.length ? meta.intro : screenFirst(meta)), [meta, flown, walked, showtimeId]);
  const [came] = useState(() => page !== undefined && takeWalked(page));
  const view = useHall(able && on ? {
    hallNo, map, film, mine, mode, seatId: mode === "seat" ? picked ?? mine.values().next().value ?? null : null, intro, cover,
    houseDown: mode === "seat", // owner, 2026-11-23: sitting in a seat, the house lights go down; All seats brings them up
    door: "wide", onTap, onLook: (s) => look(s), onHover: setHover, onMoving,
  } : null);
  if (!able || (view.status === "failed" && view.hall === hallNo && hallNo !== null)) return null; // the 2D map alone carries the page
  if (!on) {
    return (
      <div className="fr-hall3d-off">
        <button type="button" className="fr-action-secondary" onClick={() => setOn(true)}>Show the hall in 3D</button>
      </div>
    );
  }
  const category = new Map((map?.categories ?? []).map((c) => [c.id, c.name]));
  const seatId = mode === "seat" ? picked ?? mine.values().next().value ?? null : null;
  const at = map?.seats.find((s) => s.id === seatId);
  const caption = mode === "seat"
    ? (at ? `The view from row ${at.row}, seat ${at.num}.` : "Choose a seat to see the screen from it.")
    : matchMedia("(hover: none)").matches ? "Tap a seat to see the screen from it; double-tap to choose it. The map below stays in step."
      : "Click a seat to see the screen from it, double-click to choose it, right-click to take it back. The map below stays in step.";
  const show = (m: Mode) => {
    setMode(m);
    setPicked(null);
    setPreview(null);
  };
  // A click on any seat shows its view; a seat that cannot be chosen is only previewed (HallScene did not tap it).
  function look(seat: Seat) {
    if (!map) return;
    const v = visualOf(seat, mine);
    setMode("seat");
    setPicked(seat.id);
    setPreview(selectable(seat, v, map.showtime.sales_closed) ? null
      : `Previewing ${seatLabel(seat)}: this seat is ${(stateWord(seat, v) ?? "not on sale").toLowerCase()}.`);
  }

  return (
    <section ref={box} className="fr-hall3d" aria-label="The hall in 3D" data-walked={came || undefined}>
      <div className="fr-hall3d-bar">
        <div role="group" aria-label="Camera" className="fr-hall3d-modes">
          {MODES.map(([m, label]) => (
            <button key={m} type="button" className="fr-choice" aria-pressed={mode === m} onClick={() => show(m)}>{label}</button>
          ))}
        </div>
        <button type="button" className="fr-action-secondary" onClick={() => setOn(false)}>2D map</button>
      </div>
      <div key="stage" className="fr-hall3d-stage" aria-hidden="true" onPointerMove={(e) => {
        // The label follows the pointer by a style write, not a render: React re-renders only when the seat changes.
        const box = e.currentTarget.getBoundingClientRect();
        tip.current?.style.setProperty("transform", `translate(${e.clientX - box.left + 14}px, ${e.clientY - box.top + 18}px)`);
      }}>
        <HallSlot />
        <div ref={tip} className="fr-hall3d-tip" hidden={!hover || moving}>
          {hover ? seatTip(hover, category.get(hover.cat) ?? "", visualOf(hover, mine), formatPaise(hover.price_paise)) : null}
        </div>
        {map ? <p className="fr-hall3d-name">{map.screen.name} <span className="fr-mono">{map.seats.length}</span> seats</p> : null}
        <p className="fr-hall3d-caption">{caption}</p>
      </div>
      {mode === "seat" ? (
        <div className="fr-hall3d-bar">
          <p className="fr-hall3d-preview">{preview ?? ""}</p>
          <button type="button" className="fr-action-secondary" onClick={() => show("all")}>Back to all seats</button>
        </div>
      ) : null}
    </section>
  );
}

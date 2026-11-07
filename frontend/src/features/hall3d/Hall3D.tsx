// The 3D hall on the seat page (FR-ADR-074, CR-001 Part B): a presentation layer over the 2D map, which stays
// complete beneath it. This file is small and loads with the seat page; three.js and the scene load only when
// this mounts, through the lazy import below.
// Shown only when it can work: WebGL present (phones included, CR-003). Otherwise, or when the scene fails to
// load or throws, this renders nothing and the 2D map alone carries the page - nothing is lost. It renders nothing on
// the first render too (the decision is an effect), so the server-side render harness sees the 2D page unchanged.
import { Component, Suspense, lazy, useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { formatPaise } from "../admin/money";
import { seatLabel, selectable, visualOf, type Seat, type SeatMap, type Visual } from "../seatmap/model";
import { screenNumber, seatTip, stateWord, type BakedMeta, type Mode } from "./hall";
import type { Film } from "./HallScene";
import "./hall3d.css";

const HallScene = lazy(() => import("./HallScene"));

const MODES: [Mode, string][] = [["all", "All seats"], ["seat", "From my seat"]];

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

export function Hall3D({ map, film = null, mine, onTap }: {
  map: SeatMap | null; film?: Film | null; mine: ReadonlySet<number>; onTap: (seat: Seat, visual: Visual) => void;
}) {
  const [able, setAble] = useState(false);
  const [on, setOn] = useState(true);
  const [mode, setMode] = useState<Mode>("all");
  const [picked, setPicked] = useState<number | null>(null); // the seat last clicked in 3D, whose view is shown
  const [preview, setPreview] = useState<string | null>(null);
  const [hover, setHover] = useState<Seat | null>(null);
  const [moving, setMoving] = useState(false);
  const tip = useRef<HTMLDivElement>(null);
  // CR-003: a hall with a baked room ships /halls/hallN.json (+ .glb and an entrance clip). Undefined = still asking,
  // null = none (the procedural hall). The scene waits for the answer so it mounts once, in the right mode.
  const hallNo = map ? screenNumber(map.screen.name) : null;
  const [meta, setMeta] = useState<BakedMeta | null | undefined>(undefined);
  useEffect(() => setAble(canDraw()), []);
  useEffect(() => {
    if (!hallNo) return setMeta(null);
    let live = true;
    fetch(`/halls/hall${hallNo}.json`).then((r) => (r.ok ? r.json() : null)).catch(() => null).then((m) => live && setMeta(m));
    return () => {
      live = false;
    };
  }, [hallNo]);
  const onMoving = useCallback((m: boolean) => {
    setMoving(m);
    if (m) setHover(null); // the seat under the pointer is about to change
  }, []);
  if (!able || !map || meta === undefined) return null;

  if (!on) {
    return (
      <div className="fr-hall3d-off">
        <button type="button" className="fr-action-secondary" onClick={() => setOn(true)}>Show the hall in 3D</button>
      </div>
    );
  }
  const category = new Map(map.categories.map((c) => [c.id, c.name]));
  const seatId = mode === "seat" ? picked ?? mine.values().next().value ?? null : null;
  const at = map.seats.find((s) => s.id === seatId);
  const caption = mode === "seat"
    ? (at ? `The view from row ${at.row}, seat ${at.num}.` : "Choose a seat to see the screen from it.")
    : `${matchMedia("(hover: none)").matches ? "Tap" : "Click"} a seat to choose it and see the screen from it. The map below stays in step.`;
  const show = (m: Mode) => {
    setMode(m);
    setPicked(null);
    setPreview(null);
  };
  // A click on any seat shows its view; a seat that cannot be chosen is only previewed (HallScene did not tap it).
  const look = (seat: Seat) => {
    const v = visualOf(seat, mine);
    setMode("seat");
    setPicked(seat.id);
    setPreview(selectable(seat, v, map.showtime.sales_closed) ? null
      : `Previewing ${seatLabel(seat)}: this seat is ${(stateWord(seat, v) ?? "not on sale").toLowerCase()}.`);
  };

  return (
    <section className="fr-hall3d" aria-label="The hall in 3D">
      <div className="fr-hall3d-bar">
        <div role="group" aria-label="Camera" className="fr-hall3d-modes">
          {MODES.map(([m, label]) => (
            <button key={m} type="button" className="fr-choice" aria-pressed={mode === m} onClick={() => show(m)}>{label}</button>
          ))}
        </div>
        <button type="button" className="fr-action-secondary" onClick={() => setOn(false)}>Use the 2D map only</button>
      </div>
      <div className="fr-hall3d-stage" aria-hidden="true" onPointerMove={(e) => {
        // The label follows the pointer by a style write, not a render: React re-renders only when the seat changes.
        const box = e.currentTarget.getBoundingClientRect();
        tip.current?.style.setProperty("transform", `translate(${e.clientX - box.left + 14}px, ${e.clientY - box.top + 18}px)`);
      }}>
        <Guard onFail={() => setAble(false)}>
          <Suspense fallback={null}>
            <HallScene map={map} film={film} mine={mine} mode={mode} seatId={seatId} onTap={onTap} onLook={look}
                       onHover={setHover} onMoving={onMoving} meta={meta} hallNo={hallNo} />
          </Suspense>
        </Guard>
        <div ref={tip} className="fr-hall3d-tip" hidden={!hover || moving}>
          {hover ? seatTip(hover, category.get(hover.cat) ?? "", visualOf(hover, mine), formatPaise(hover.price_paise)) : null}
        </div>
        <p className="fr-hall3d-name">{map.screen.name} <span className="fr-mono">{map.seats.length}</span> seats</p>
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

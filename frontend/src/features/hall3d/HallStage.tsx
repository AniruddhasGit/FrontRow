// CR-004: a baked hall filling its box, seen from a seat - the landing page and Browse. No hold or booking happens
// here: a seat click only moves the camera to it. With the showtime's real seat map, the hover label carries the
// price and the state (seatTip); without one (the landing) the seats are the bake's, named by category alone.
// Same rules as Hall3D: no WebGL, no bake or a scene error renders the fallback, never a broken box.
import { Suspense, lazy, useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { formatPaise } from "../admin/money";
import { visualOf, type Seat, type SeatMap } from "../seatmap/model";
import { bakedSeatMap } from "../wake/wakeup";
import { Guard, canDraw } from "./Hall3D";
import { seatTip, type BakedMeta, type Mode } from "./hall";
import type { Film } from "./HallScene";
import "./hall3d.css";

const HallScene = lazy(() => import("./HallScene"));
const NONE: ReadonlySet<number> = new Set();

export function HallStage({ hallNo, film, map: real = null, fallback = null }: {
  hallNo: number; film: Film | null; map?: SeatMap | null; fallback?: ReactNode;
}) {
  const [able, setAble] = useState(false);
  const [meta, setMeta] = useState<BakedMeta | null | undefined>(undefined);
  const [mode, setMode] = useState<Mode>("seat"); // seated, facing the screen
  const [picked, setPicked] = useState<number | null>(null);
  const [hover, setHover] = useState<Seat | null>(null);
  const [moving, setMoving] = useState(false);
  const tip = useRef<HTMLDivElement>(null);
  useEffect(() => setAble(canDraw()), []);
  useEffect(() => {
    let live = true;
    setMeta(undefined);
    setPicked(null);
    setMode("seat");
    fetch(`/halls/hall${hallNo}.json`).then((r) => (r.ok ? r.json() : null)).catch(() => null)
      // no arrival route here: the visitor is already sitting down
      .then((m: BakedMeta | null) => live && setMeta(m?.seats?.length ? { ...m, intro: undefined } : null));
    return () => {
      live = false;
    };
  }, [hallNo]);
  // the real map only when it is this hall's; otherwise the bake's own seats
  const map = useMemo(() => (real && meta && real.seats.length === meta.seats.length ? real : meta ? bakedSeatMap(meta) : null), [real, meta]);
  const onMoving = useCallback((m: boolean) => {
    setMoving(m);
    if (m) setHover(null);
  }, []);
  if (!able || meta === null) return <div className="fr-stage">{fallback}</div>;
  if (!meta || !map) return <div className="fr-stage" />;

  const names = new Map(map.categories.map((c) => [c.id, c.name]));
  const priced = map.showtime.id !== 0;
  const label = (s: Seat) => priced ? seatTip(s, names.get(s.cat) ?? "", visualOf(s, NONE), formatPaise(s.price_paise))
    : `Row ${s.row} · Seat ${s.num} · ${names.get(s.cat) ?? ""}`;
  const at = map.seats.find((s) => s.id === picked);
  const tap = matchMedia("(hover: none)").matches ? "Tap" : "Click";
  const caption = mode === "all" ? `Drag to look around. ${tap} a seat to sit there.`
    : at ? `The view from row ${at.row}, seat ${at.num}. Drag to look around.` : `Drag to look around. ${tap} a seat to sit there.`;

  return (
    <div className="fr-stage" onPointerMove={(e) => {
      const box = e.currentTarget.getBoundingClientRect();
      tip.current?.style.setProperty("transform", `translate(${e.clientX - box.left + 14}px, ${e.clientY - box.top + 18}px)`);
    }}>
      <div className="fr-stage-canvas" aria-hidden="true">
        <Guard key={hallNo} onFail={() => setMeta(null)}>
          <Suspense fallback={null}>
            <HallScene map={map} film={film} mine={NONE} mode={mode} seatId={mode === "seat" ? picked : null}
                       onTap={() => undefined /* booking happens on the seat page */}
                       onLook={(s) => { setMode("seat"); setPicked(s.id); }}
                       onHover={setHover} onMoving={onMoving} meta={meta} hallNo={hallNo} />
          </Suspense>
        </Guard>
      </div>
      <div ref={tip} className="fr-hall3d-tip" hidden={!hover || moving}>{hover ? label(hover) : null}</div>
      <div className="fr-stage-foot">
        <p className="fr-hall3d-caption">{caption}</p>
        <button type="button" className="fr-action-secondary" onClick={() => { setMode(mode === "all" ? "seat" : "all"); setPicked(null); }}>
          {mode === "all" ? "Back to my seat" : "See every seat"}
        </button>
      </div>
    </div>
  );
}

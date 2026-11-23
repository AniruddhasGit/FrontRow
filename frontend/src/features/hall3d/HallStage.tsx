// CR-004/005: a baked hall filling its box, seen from the default seat - the landing. `locked` (the landing): no seat
// can be clicked, nothing hovers, nothing drags; the camera moves only when `pan` turns true, from the seat round onto
// the all-seats view, and `onPanned` fires when it lands (at once when there is nothing to fly: no WebGL, no bake,
// reduced motion). No hold or booking happens here.
// Same rules as Hall3D: no WebGL, no bake or a scene error renders the fallback, never a broken box.
import { Suspense, lazy, useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import type { SeatMap } from "../seatmap/model";
import { bakedSeatMap } from "../wake/wakeup";
import { Guard, canDraw } from "./Hall3D";
import type { BakedMeta } from "./hall";
import type { Film } from "./HallScene";
import { HALL_CAP_MS } from "./readiness";
import "./hall3d.css";

const HallScene = lazy(() => import("./HallScene"));
const NONE: ReadonlySet<number> = new Set();
const PAN_CAP_MS = 7000; // the pan takes ~4.2 s; past this the page moves on anyway

export function HallStage({ hallNo, film, map: real = null, fallback = null, pan = false, onPanned }: {
  /** undefined while the page is still finding the film: the hall waits for it before it shows (readiness.ts) */
  hallNo: number; film: Film | null | undefined; map?: SeatMap | null; fallback?: ReactNode; pan?: boolean; onPanned?: () => void;
}) {
  const [able] = useState(canDraw); // in the first render, so the stage does not switch state a frame later
  const [meta, setMeta] = useState<BakedMeta | null | undefined>(undefined);
  const [since] = useState(() => performance.now()); // the hall's load cap counts from here
  const started = useRef(false);
  const told = useRef(false);
  useEffect(() => {
    let live = true;
    setMeta(undefined);
    fetch(`/halls/hall${hallNo}.json`, { signal: AbortSignal.timeout(HALL_CAP_MS) }).then((r) => (r.ok ? r.json() : null)).catch(() => null)
      // no arrival route here: the visitor is already sitting down
      .then((m: BakedMeta | null) => live && setMeta(m?.seats?.length ? { ...m, intro: undefined } : null));
    return () => {
      live = false;
    };
  }, [hallNo]);
  // the real map only when it is this hall's; otherwise the bake's own seats
  const map = useMemo(() => (real && meta && real.seats.length === meta.seats.length ? real : meta ? bakedSeatMap(meta) : null), [real, meta]);
  const done = useCallback(() => {
    if (told.current) return;
    told.current = true;
    onPanned?.();
  }, [onPanned]);
  const flying = able && !!meta && !matchMedia("(prefers-reduced-motion: reduce)").matches;
  useEffect(() => {
    if (!pan) return;
    if (!flying) return done();
    const cap = setTimeout(done, PAN_CAP_MS);
    return () => clearTimeout(cap);
  }, [pan, flying, done]);
  const onMoving = useCallback((m: boolean) => {
    if (!pan) return;
    if (m) started.current = true;
    else if (started.current) done();
  }, [pan, done]);

  if (!able || meta === null) return <div className="fr-stage" data-off="">{fallback}</div>; // no hall coming: no loader
  if (!meta || !map) return <div className="fr-stage" />;
  return (
    <div className="fr-stage">
      <div className="fr-stage-canvas" aria-hidden="true">
        <Guard key={hallNo} onFail={() => setMeta(null)}>
          <Suspense fallback={null}>
            <HallScene map={map} film={film} mine={NONE} mode={pan ? "all" : "seat"} seatId={null} locked
                       houseDown={!pan} /* watching: lights down; Book tickets brings them up for choosing seats */
                       onTap={() => undefined} onLook={() => undefined} onHover={() => undefined}
                       onMoving={onMoving} meta={meta} hallNo={hallNo} since={since} />
          </Suspense>
        </Guard>
      </div>
    </div>
  );
}

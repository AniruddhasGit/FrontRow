// CR-005: the stage curtain - a transition piece, used where the owner says. Real cloth (CurtainScene.tsx: Verlet
// physics, velvet sheen, a woven normal map) wherever WebGL works; elsewhere the flat CSS drape below stands in.
// It fills its positioned parent and never takes a click.
//   up     - flown out, above the box (nothing shows, nothing runs)
//   down   - dropped over the box; the hem swings on and settles
//   drawn  - opened from left to right: gathered to the box's RIGHT edge, folding up as it goes, revealing what is behind
// `onDone` fires when the current move has finished (settle included). With reduced motion every move is instant.
import { Suspense, lazy, useEffect, useRef, useState } from "react";
import { Guard, canDraw } from "../hall3d/Hall3D";
import "./curtain.css";

const load = () => import("./CurtainScene");
const CurtainScene = lazy(load);

export type CurtainPhase = "up" | "down" | "drawn";
const DONE_MS: Record<CurtainPhase, number> = { up: 0, down: 1000, drawn: 950 }; // the flat drape's moves (the cloth reports its own)

export function Curtain({ phase, onDone }: { phase: CurtainPhase; onDone?: () => void }) {
  const done = useRef(onDone);
  done.current = onDone;
  const [cloth, setCloth] = useState(false);
  const [failed, setFailed] = useState(false);
  const reduced = typeof matchMedia === "function" && matchMedia("(prefers-reduced-motion: reduce)").matches;
  useEffect(() => {
    const ok = canDraw() && !reduced;
    setCloth(ok);
    if (ok) void load(); // fetched while the page is idle, so the first drop starts on the click
  }, [reduced]);
  const live = cloth && !failed;
  useEffect(() => {
    if (phase === "up" || live) return; // the cloth calls onDone itself
    const t = setTimeout(() => done.current?.(), reduced ? 0 : DONE_MS[phase]);
    return () => clearTimeout(t);
  }, [phase, reduced, live]);
  // The cloth is mounted while parked too (above the box, drawn once), so its first drop starts without a stall.
  if (phase === "up" && !live) return null;
  return (
    <div className="fr-curtain" data-phase={phase} aria-hidden="true">
      {live ? (
        <Guard onFail={() => setFailed(true)}>
          <Suspense fallback={null}>
            <CurtainScene phase={phase} onDone={() => done.current?.()} />
          </Suspense>
        </Guard>
      ) : (
        <>
          <div className="fr-curtain-drape" />
          <div className="fr-curtain-valance" />
        </>
      )}
    </div>
  );
}

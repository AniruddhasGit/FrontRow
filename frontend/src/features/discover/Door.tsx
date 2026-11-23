// The film page's door (owner, 2026-11-23; CR-014): at the right of the hero, the chosen show's hall seen live from its
// own corridor (hallN.json `corridor`), the door ajar at its end - the SAME 3D hall the seat page shows (hall3d/host.tsx).
// Hover or focus opens the door a little (`peek`). Pressing it, or Book, is the walk: the page's other parts slide away
// (MovieScreen, data-flying), the view grows to fill the window, the door swings wide and the camera follows `enter`
// through it onto the all-seats view; only then does the URL become the seat page, whose panel slides in over the same
// live scene. No fade, no snapshot, no remount.
// Loading: until the hall is ready (readiness.ts) its corridor render stands in at the same view (walk.ts corridorFov),
// then fades out over the live view. Another screen's show: the picture comes back first, then the hall behind it changes.
// One status (discover.ts `door`); every wait has an exit: a hall that cannot show leaves the picture up and the door
// goes straight to the seat page, and a walk that never reports landing leaves after WALK_CAP_MS.
// Reduced motion: no walk - straight to the seat page.
import { useEffect, useReducer, useRef, useState, type CSSProperties } from "react";
import { navigate } from "../../router";
import { timeLabel } from "../browse/logic";
import { canDraw } from "../hall3d/Hall3D";
import { screenNumber } from "../hall3d/hall";
import { WALKIN } from "../hall3d/hallReady";
import { HallSlot, useHall, useHostView, walkedTo } from "../hall3d/host";
import { WALK_MS } from "../hall3d/walk";
import { door as step, type DoorShow } from "./discover";
import "./door.css";

// Cycles renders (claude_leash Graphics/FrontRow): each screen's corridor from `corridor.eye`, a square 32 mm frame
const still = (n: number) => `/art/corridor/screen${n}.webp`;
const DECODE_CAP_MS = 6000; // the picture shows once decoded, or after this anyway
const FADE_MS = 400 + 450; // the canvas fades in under the picture (hall3d.css), then the picture fades out (door.css)
const WALK_CAP_MS = WALK_MS + 2500; // the walk reports landing; if it never does (a hidden window draws no frames), go anyway
const reduced = () => matchMedia("(prefers-reduced-motion: reduce)").matches;

/** The image decoded (or the cap passed): only then does it show, so it never draws in line by line. Never rejects. */
function decoded(src: string): Promise<void> {
  const i = new Image();
  i.src = src;
  return Promise.race([i.decode().catch(() => undefined), new Promise<void>((r) => setTimeout(r, DECODE_CAP_MS))]);
}

export function TheatreDoor({ show, film, onFly }: {
  show: DoorShow | null; film: { id?: number; title: string }; onFly?: (flying: boolean) => void;
}) {
  const n = show ? screenNumber(show.screen.name) || 1 : null; // the hall behind the door; null until the show is known
  const [able] = useState(canDraw);
  const [state, dispatch] = useReducer(step, { kind: "waiting" });
  const host = useHostView();
  // The hall asked of the host. A new screen's hall is asked for only once its picture covers the box again, so the
  // old live view never vanishes into an empty box (null: the hall that is up stays - Back from the seat page).
  const [asked, setAsked] = useState<number | null>(n);
  const showing = able && host.status === "shown" && (asked === null || host.hall === asked);
  const covered = !showing || (n !== null && n !== asked); // the picture is up
  const stateRef = useRef(state);
  stateRef.current = state;
  useEffect(() => {
    if (n === null || n === asked) return;
    const hidden = stateRef.current.kind === "live";
    dispatch({ type: "reset" });
    const t = window.setTimeout(() => setAsked(n), hidden ? 450 : 0);
    return () => clearTimeout(t);
  }, [n, asked]);
  // the picture: this screen's, once decoded (the previous one stays up meanwhile)
  const [pic, setPic] = useState<number | null>(null);
  const want = n ?? host.hall;
  useEffect(() => {
    if (want === null) return;
    let live = true;
    void decoded(still(want)).then(() => live && setPic(want));
    return () => {
      live = false;
    };
  }, [want]);
  // the hall is live once the picture has finished fading off it (at once if the picture never showed: Back)
  const seenCovered = useRef(covered);
  if (covered) seenCovered.current = true;
  useEffect(() => {
    if (!showing || covered) return;
    if (!seenCovered.current) return dispatch({ type: "ready" });
    const t = window.setTimeout(() => dispatch({ type: "ready" }), FADE_MS);
    return () => clearTimeout(t);
  }, [showing, covered]);
  // Back from the seat page: the hall is already up, but its canvas arrives here still showing the seats for a frame
  // or two before the camera's cut to the corridor is drawn; it is held unseen that long, then fades in
  const [settling, setSettling] = useState(() => host.status === "shown");
  useEffect(() => {
    if (!settling) return;
    const t = window.setTimeout(() => setSettling(false), 150);
    return () => clearTimeout(t);
  }, [settling]);
  const failed = !able || (host.status === "failed" && (asked === null || host.hall === asked));
  useEffect(() => void (failed && dispatch({ type: "failed" })), [failed]);

  const walking = state.kind === "walking" || (state.kind === "leaving" && state.how === "walked");
  const [hover, setHover] = useState(false);
  useHall(able ? {
    hallNo: asked, corridor: true, locked: true, film: film.id === undefined ? null : { id: film.id, title: film.title },
    mode: walking ? "all" : "corridor", walk: walking,
    door: walking ? "wide" : hover && state.kind === "live" && !reduced() ? "peek" : "ajar",
    onWalked: () => dispatch({ type: "landed" }),
  } : null);

  // the walk: the box leaves the page's flow where it was, then grows to the window (a CSS transition)
  const [box, setBox] = useState<{ left: number; top: number; width: number; height: number } | null>(null);
  const [full, setFull] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (state.kind !== "walking" || !box) return;
    onFly?.(true);
    // grow once the fixed box has painted at its old place (a timer, not two animation frames: a hidden or occluded
    // window runs no frames, and the walk must still reach the seats)
    const grow = window.setTimeout(() => setFull(true), 40);
    const cap = window.setTimeout(() => dispatch({ type: "landed" }), WALK_CAP_MS);
    return () => {
      clearTimeout(grow);
      clearTimeout(cap);
    };
  }, [state.kind, box, onFly]);
  useEffect(() => () => onFly?.(false), [onFly]);
  useEffect(() => {
    if (state.kind !== "leaving") return;
    const to = `/showtimes/${state.show.id}`;
    if (state.how === "walked") {
      walkedTo(state.show.id); // the seat page slides its panel in over this same hall
      window.scrollTo(0, 0); // the seat page starts at its top; the box is fixed, so nothing on screen moves
      return navigate(to, undefined, { instant: true });
    }
    try {
      window.sessionStorage.setItem(WALKIN, String(state.show.id)); // the old way: the seat page plays the walk-in
    } catch {
      // no storage: the seat page plays its own arrival instead
    }
    navigate(to);
  }, [state]);

  const at = show ? timeLabel(show.starts_at) : "";
  const open = !!show && !show.sales_closed;
  const press = () => {
    if (!show || !open) return;
    lift();
    dispatch({ type: "press", show, reduced: reduced() });
  };
  // where the box is when the walk starts: taken in the press itself when the hall is live (the box is fixed there in
  // the same frame), else when a queued press starts walking
  const lift = () => {
    const r = ref.current?.getBoundingClientRect();
    if (r && state.kind === "live") setBox({ left: r.left, top: r.top, width: r.width, height: r.height });
  };
  useEffect(() => {
    if (state.kind !== "walking" || box) return;
    const r = ref.current?.getBoundingClientRect();
    if (r) setBox({ left: r.left, top: r.top, width: r.width, height: r.height });
  }, [state.kind, box]);
  const flying = walking && !!box;
  const style: CSSProperties | undefined = flying ? (full
    ? { position: "fixed", left: 0, top: 0, width: "100vw", height: "100vh" }
    : { position: "fixed", ...box }) : undefined;
  const busy = !open || state.kind === "queued" || state.kind === "walking" || state.kind === "leaving";
  return (
    <>
      <div className="fr-corridor-box">
        {flying ? <div className="fr-corridor-keep" /> : null}
        <div ref={ref} className="fr-corridor" data-door={flying ? "flying" : state.kind} data-full={full || undefined} style={style}>
          {/* the whole view is the door's button: the door is small in it, and the corridor is the way in */}
          <button type="button" className="fr-corridor-door" disabled={busy} onClick={press} aria-busy={state.kind === "queued" || undefined}
                  onPointerEnter={() => setHover(true)} onPointerLeave={() => setHover(false)} onFocus={() => setHover(true)} onBlur={() => setHover(false)}
                  aria-label={open ? `Enter ${show!.screen.name} for ${film.title} at ${at}` : "No show open to enter"}>
            <span className="fr-corridor-frame" aria-hidden="true">
              {able ? <span className="fr-corridor-live" data-settling={settling || undefined}><HallSlot /></span> : null}
              {/* the span fades the picture in once (decoded first); the img fades out over the live hall and back */}
              {pic !== null ? <span className="fr-corridor-pic"><img className="fr-corridor-shot" src={still(pic)} alt="" decoding="async"
                                                                      data-live={!covered || undefined} /></span> : null}
            </span>
          </button>
        </div>
      </div>
      {/* the same walk, for anyone who does not think of pushing the door */}
      <button type="button" className="fr-action fr-corridor-book" disabled={busy} onClick={press}>
        {open ? <>Book <span className="fr-mono">· {show!.screen.name} · {at}</span></> : "Choose a showtime below"}
      </button>
    </>
  );
}

// The film page's door (owner, 2026-11-23, replacing CR-011 F5's door below the showtimes): at the right of the hero,
// a dim corridor fades into the box, and at its end a door - the screen's name lit yellow above it, a green ENTER below.
// The door is a real <button> named for the show. Pressing it is a fly-through: the page's other parts slide away
// (MovieScreen, data-flying), the corridor grows to fill the window and the camera flies into the door while the hall
// is fetched (prefetchHall); then the seat page opens on that frame and its hall plays the walk-in from the entry
// door (WALKIN, read once by Hall3D; the router holds this frame until the hall has drawn, so nothing flashes).
// One status (discover.ts Door). Every wait has an exit: the flight leaves after FLY_MS plus at most PREFETCH_CAP_MS.
// Reduced motion: no flight - straight to the seat page, whose hall then cuts to the seats.
import { useEffect, useRef, useState, type CSSProperties } from "react";
import { navigate } from "../../router";
import { timeLabel } from "../browse/logic";
import { screenNumber } from "../hall3d/hall";
import { nextHallDrawn, WALKIN } from "../hall3d/hallReady";
import { FLY_MS, PREFETCH_CAP_MS, pressDoor, type Door, type DoorShow } from "./discover";
import "./door.css";

/** Everything the seat page's hall needs, loaded and the room PARSED while the film page is open (hall3d/preload.ts):
 *  the walk-in then starts without waiting for it. The 3D code arrives as its own chunk, so this page stays light.
 *  Never rejects. */
function prefetchHall(show: DoorShow): Promise<unknown> {
  const n = screenNumber(show.screen.name);
  return Promise.all([
    ...(n ? [`/halls/hall${n}.json`, `/halls/hall${n}_env.hdr`].map((f) => fetch(f).then((r) => r.arrayBuffer()).catch(() => null)) : []),
    import("../hall3d/preload").then((m) => (n ? m.loadRoom(n) : null)).catch(() => null),
    import("../hall3d/seatModels").then((m) => Promise.all((["standard", "premium", "recliner"] as const).map(m.seatGeometry))).catch(() => null),
    import("../hall3d/HallScene").catch(() => null),
  ]);
}

/** Run when the page is idle (not while it is still drawing itself). */
function whenIdle(fn: () => void): () => void {
  const w = window as Window & { requestIdleCallback?: (f: () => void, o?: { timeout: number }) => number; cancelIdleCallback?: (id: number) => void };
  if (w.requestIdleCallback) {
    const id = w.requestIdleCallback(fn, { timeout: 1500 });
    return () => w.cancelIdleCallback?.(id);
  }
  const t = window.setTimeout(fn, 300);
  return () => clearTimeout(t);
}

function walkIn(showtimeId: number) {
  try {
    window.sessionStorage.setItem(WALKIN, String(showtimeId));
  } catch {
    // no storage: the seat page plays its own arrival instead
  }
  navigate(`/showtimes/${showtimeId}`, nextHallDrawn());
}

// Cycles renders (claude_leash Graphics/FrontRow, corridor_render.py): the corridor per screen with its door ajar, and
// one strip of 12 frames of that door swinging open, cropped to the doorway - played in place over the still.
const still = (n: number) => `/art/corridor/screen${n}.webp`;
const SWING = "/art/corridor/swing.webp";
const READY_CAP_MS = 6000;
const SWING_FRAMES = 12;
const PEEK = 4; // the swing frame a hovered door opens to // owner, 2026-11-23: nothing shows or moves before it has loaded - and every wait has an exit

/** Both images decoded (or the cap passed): only then does the corridor show, and the door work. Never rejects. */
function decoded(srcs: string[]): Promise<void> {
  const one = (src: string) => { const i = new Image(); i.src = src; return i.decode().catch(() => undefined); };
  return Promise.race([Promise.all(srcs.map(one)).then(() => undefined), new Promise<void>((r) => setTimeout(r, READY_CAP_MS))]);
}

export function TheatreDoor({ show, film, onFly }: {
  show: DoorShow | null; film: { title: string }; onFly?: (flying: boolean) => void;
}) {
  const [door, setDoor] = useState<Door>({ kind: "closed" });
  const [box, setBox] = useState<{ left: number; top: number; width: number; height: number } | null>(null);
  const [full, setFull] = useState(false); // the corridor has grown to the window
  const ref = useRef<HTMLDivElement>(null);
  const n = (show && screenNumber(show.screen.name)) || 1;
  const [loaded, setLoaded] = useState<number | null>(null); // the screen whose corridor has decoded
  useEffect(() => {
    let live = true;
    void decoded([still(n), SWING]).then(() => live && setLoaded(n));
    return () => {
      live = false;
    };
  }, [n]);
  // owner, 2026-11-23: start the hall's loading as soon as this page knows the show, not when the door is pressed
  useEffect(() => (show ? whenIdle(() => void prefetchHall(show)) : undefined), [show?.id]); // eslint-disable-line react-hooks/exhaustive-deps
  // hover or focus opens the door a little: the swing's first frames, one after another, and back when you leave
  const [peek, setPeek] = useState(0); // the swing frame shown at rest (0 = the still's own ajar door)
  const peekTo = useRef(0);
  useEffect(() => {
    if (peek === peekTo.current) return;
    const t = window.setTimeout(() => setPeek((p) => p + Math.sign(peekTo.current - p)), 45);
    return () => clearTimeout(t);
  }, [peek]);
  const lean = (open: boolean) => {
    if (matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    peekTo.current = open ? PEEK : 0;
    setPeek((p) => p + Math.sign(peekTo.current - p));
  };
  useEffect(() => setDoor({ kind: "closed" }), [show?.id]);
  useEffect(() => {
    if (door.kind !== "flying") return;
    let live = true;
    onFly?.(true);
    // grow once the fixed corridor has painted at its old place (a timer, not two animation frames: a hidden or
    // occluded window runs no frames, and the flight must still reach the hall)
    const grow = window.setTimeout(() => live && setFull(true), 40);
    const flown = new Promise((r) => setTimeout(r, FLY_MS));
    const loaded = Promise.race([prefetchHall(door.show), new Promise((r) => setTimeout(r, FLY_MS + PREFETCH_CAP_MS))]);
    void Promise.all([flown, loaded]).then(() => live && walkIn(door.show.id));
    return () => {
      live = false;
      clearTimeout(grow);
    };
  }, [door, onFly]);
  useEffect(() => () => onFly?.(false), [onFly]);

  const at = show ? timeLabel(show.starts_at) : "";
  const open = !!show && !show.sales_closed;
  const press = () => {
    if (!show || !open) return;
    if (matchMedia("(prefers-reduced-motion: reduce)").matches) return walkIn(show.id);
    const r = ref.current?.getBoundingClientRect();
    setBox(r ? { left: r.left, top: r.top, width: r.width, height: r.height } : null);
    setDoor((d) => pressDoor(d, show));
  };
  // flying: the corridor leaves the page's flow exactly where it was, then grows to the window (a CSS transition)
  const flying = door.kind === "flying" && !!box;
  const style: CSSProperties | undefined = flying ? (full
    ? { position: "fixed", left: 0, top: 0, width: "100vw", height: "100vh" }
    : { position: "fixed", ...box }) : undefined;
  const busy = !open || door.kind === "flying" || loaded !== n;
  return (
    <>
      <div className="fr-corridor-box">
        {flying ? <div className="fr-corridor-keep" /> : null}
        <div ref={ref} className="fr-corridor" data-door={door.kind} data-full={full || undefined} data-ready={loaded !== null || undefined}
             style={style}>
          {/* the whole picture is the door's button: the door is small in it, and the corridor is the way in */}
          <button type="button" className="fr-corridor-door" disabled={busy} onClick={press}
                  onPointerEnter={() => lean(true)} onPointerLeave={() => lean(false)} onFocus={() => lean(true)} onBlur={() => lean(false)}
                  aria-label={open ? `Enter ${show!.screen.name} for ${film.title} at ${at}` : "No show open to enter"}>
            <span className="fr-corridor-frame" aria-hidden="true">
              <img className="fr-corridor-shot" src={still(loaded ?? n)} alt="" decoding="async" />
              <span className="fr-corridor-swing" data-peek={peek || undefined}
                    style={{ backgroundPositionX: `${(100 * peek) / (SWING_FRAMES - 1)}%` }} />
            </span>
          </button>
        </div>
      </div>
      {/* the same flight, for anyone who does not think of pushing the door */}
      <button type="button" className="fr-action fr-corridor-book" disabled={busy} onClick={press}>
        {open ? <>Book <span className="fr-mono">· {show!.screen.name} · {at}</span></> : "Choose a showtime below"}
      </button>
    </>
  );
}

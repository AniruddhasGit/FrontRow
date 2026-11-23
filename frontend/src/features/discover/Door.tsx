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

/** Everything the seat page's hall needs, into the browser's cache while the flight plays. Never rejects. */
function prefetchHall(show: DoorShow): Promise<unknown> {
  const n = screenNumber(show.screen.name);
  const files = [...(n ? [`/halls/hall${n}.json`, `/halls/hall${n}.glb`, `/halls/hall${n}_env.hdr`] : []),
    ...["standard", "premium", "recliner"].map((k) => `/models/seat_${k}.glb`)];
  return Promise.all([
    ...files.map((f) => fetch(f).then((r) => r.arrayBuffer()).catch(() => null)),
    import("../hall3d/HallScene").catch(() => null),
  ]);
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
const READY_CAP_MS = 6000; // owner, 2026-11-23: nothing shows or moves before it has loaded - and every wait has an exit

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
    // once the corridor is ready, fetch the show's hall too, so the walk-in starts without waiting for it
    void decoded([still(n), SWING]).then(() => {
      if (!live) return;
      setLoaded(n);
      if (show) void prefetchHall(show);
    });
    return () => {
      live = false;
    };
  }, [n, show?.id]); // eslint-disable-line react-hooks/exhaustive-deps
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
                  aria-label={open ? `Enter ${show!.screen.name} for ${film.title} at ${at}` : "No show open to enter"}>
            <span className="fr-corridor-frame" aria-hidden="true">
              <img className="fr-corridor-shot" src={still(loaded ?? n)} alt="" decoding="async" />
              <span className="fr-corridor-swing" />
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

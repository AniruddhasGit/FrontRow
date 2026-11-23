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
  const files = n ? [`/halls/hall${n}.json`, `/halls/hall${n}.glb`, `/halls/hall${n}_env.hdr`] : [];
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

const LAMPS = [0, 1, 2, 3, 4]; // ceiling lamps, near to far

export function TheatreDoor({ show, film, onFly }: {
  show: DoorShow | null; film: { title: string }; onFly?: (flying: boolean) => void;
}) {
  const [door, setDoor] = useState<Door>({ kind: "closed" });
  const [box, setBox] = useState<{ left: number; top: number; width: number; height: number } | null>(null);
  const [full, setFull] = useState(false); // the corridor has grown to the window
  const ref = useRef<HTMLDivElement>(null);
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
  return (
    <>
      {flying ? <div className="fr-corridor-keep" /> : null}
      <div ref={ref} className="fr-corridor" data-door={door.kind} data-full={full || undefined} style={style}>
        <div className="fr-corridor-zoom">
          <div className="fr-corridor-room" aria-hidden="true">
            <span className="fr-corridor-ceiling" />
            <span className="fr-corridor-wall fr-corridor-left" />
            <span className="fr-corridor-wall fr-corridor-right" />
            <span className="fr-corridor-floor" />
            {LAMPS.map((i) => <span key={i} className="fr-corridor-lamp" style={{ ["--d" as string]: i }} />)}
          </div>
          <div className="fr-corridor-end">
            <p className="fr-corridor-screen" aria-hidden="true">{show ? show.screen.name : "SCREEN"}</p>
            <button type="button" className="fr-corridor-door" disabled={!open || door.kind === "flying"} onClick={press}
                    aria-label={open ? `Enter ${show!.screen.name} for ${film.title} at ${at}` : "No show open to enter"}>
              <span className="fr-corridor-gap" aria-hidden="true" />
              <span className="fr-corridor-leaf" aria-hidden="true"><span className="fr-corridor-pane" /></span>
            </button>
            <p className="fr-corridor-enter" aria-hidden="true"><span>ENTER</span></p>
          </div>
        </div>
        <p className="fr-corridor-plate">
          {open ? <><span className="fr-mono">{show!.screen.name} · {at}</span> · push the door to walk in</> : "Choose a showtime below"}
        </p>
      </div>
    </>
  );
}

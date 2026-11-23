// CR-014: one live 3D hall for the whole app, so it outlives a page change. The owner: "redesign the hall itself with a
// corridor and it loads up in here to make it as smooth as possible". The film page shows the hall from its corridor
// and the seat page shows it from the seats: the SAME scene, never unmounted between them, so nothing reloads, fades
// or freezes on the way in.
//
// How: HallHost (App.tsx, above the router's pages) renders the one HallScene through a portal into a <div> it owns,
// and a page's <HallSlot> moves that <div> into itself (appendChild in a layout effect, so no frame is painted without
// it; a WebGL canvas keeps its context when it moves). A page says what it wants with useHall(): which hall, which
// camera ("corridor" or the seat page's modes), the door's angle, the seats' state and the handlers. The host keeps
// the hall while some page wants it; when no page does (the landing, the account pages), it lets it go.
// A page that does not know its hall yet passes hallNo null: the hall already up stays (Back from the seat page).
import { createContext, lazy, Suspense, useCallback, useContext, useLayoutEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { liveHallShown } from "../../router";
import type { Seat, SeatMap, Visual } from "../seatmap/model";
import { bakedSeatMap } from "../wake/wakeup";
import type { BakedMeta, Mode } from "./hall";
import { Guard } from "./Hall3D";
import type { Film } from "./HallScene";
import { HALL_CAP_MS } from "./readiness";
import { NO_COVER, type Cover, type Pose } from "./walk";
import "./hall3d.css";

const HallScene = lazy(() => import("./HallScene"));
const NONE: ReadonlySet<number> = new Set();
// A page change can leave a moment with no page asking (the film page draws its hero's frame before the door, which
// asks, arrives with the film's details); the hall is kept this long unasked before it is let go.
const GRACE_MS = 5000;

export type DoorPose = "ajar" | "peek" | "wide";
export interface HallWant {
  /** null: keep the hall that is up (the page does not know its show yet) */
  hallNo: number | null;
  /** the film page: a hall file without a corridor cannot serve it (status "failed" for this page) */
  corridor?: boolean;
  /** the seats' live state; null or absent: the bake's own seats, all free (the film page) */
  map?: SeatMap | null;
  /** undefined: the page does not know the film yet - the screen keeps the picture it has */
  film?: Film | null;
  mine?: ReadonlySet<number>;
  mode: Mode | "corridor";
  seatId?: number | null;
  locked?: boolean;
  houseDown?: boolean;
  door?: DoorPose;
  /** the camera follows hallN.json `enter` when the mode leaves "corridor" (else a change to or from it is a cut) */
  walk?: boolean;
  /** the arrival route if the hall FIRST shows on this page (the seat page's intro); null: none */
  intro?: Pose[] | null;
  /** how much of the canvas the page covers (the seat page's panel); the hall is framed in the rest */
  cover?: Cover;
  onTap?: (seat: Seat, visual: Visual) => void;
  onLook?: (seat: Seat) => void;
  onHover?: (seat: Seat | null) => void;
  onMoving?: (moving: boolean) => void;
  onWalked?: () => void;
}
/** none: no hall wanted; loading: on its way (readiness.ts); shown: drawn and visible; failed: it cannot show. */
export type HostStatus = "none" | "loading" | "shown" | "failed";
export interface HostView { hall: number | null; status: HostStatus; meta: BakedMeta | null | undefined }
const NO_VIEW: HostView = { hall: null, status: "none", meta: undefined };

type Ctx = { holder: HTMLDivElement | null; view: HostView; want: (id: symbol, w: HallWant | null) => void };
const HostCtx = createContext<Ctx | null>(null);

type Scene = { hall: number; key: number; since: number; meta: BakedMeta | null | undefined; status: "loading" | "shown" | "failed" };

/** Start everything the hall needs at once, in parallel: its file, the room's parse (preload.ts), the 3D code. */
function startHall(n: number, key: number, done: (key: number, meta: BakedMeta | null) => void) {
  void import("./preload").then((m) => m.loadRoom(n)).catch(() => null);
  void import("./HallScene").catch(() => null);
  // capped like the rest of the hall: a .json that never answers is "no bake" (web-app-pitfalls 2)
  fetch(`/halls/hall${n}.json`, { signal: AbortSignal.timeout(HALL_CAP_MS) }).then((r) => (r.ok ? r.json() : null)).catch(() => null)
    .then((m: BakedMeta | null) => done(key, m?.seats?.length ? m : null));
}

export function HallHost({ children }: { children: ReactNode }) {
  const [holder] = useState(() => {
    if (typeof document === "undefined") return null; // the server-side render harness
    const d = document.createElement("div");
    d.className = "fr-hall-host";
    return d;
  });
  useLayoutEffect(() => liveHallShown(() => !!holder?.isConnected && !!holder.querySelector(".fr-hall-canvas[data-shown]")), [holder]);
  const [want, setWant] = useState<{ id: symbol; w: HallWant } | null>(null);
  const last = useRef<HallWant | null>(null); // what the last page asked, served through the grace period
  const wantFn = useCallback((id: symbol, w: HallWant | null) => {
    setWant((cur) => (w ? { id, w } : cur?.id === id ? null : cur));
  }, []);
  const [scene, setScene] = useState<Scene | null>(null);
  const keys = useRef(0);
  const asked = want?.w.hallNo ?? null;
  const wanted = want !== null;
  useLayoutEffect(() => {
    if (!wanted) { // no page wants a hall: after the grace, let it go (its canvas and GPU memory with it)
      const t = window.setTimeout(() => setScene(null), GRACE_MS);
      return () => clearTimeout(t);
    }
    if (asked === null) return; // keep what is up
    setScene((s) => {
      if (s && s.hall === asked) return s;
      const key = ++keys.current;
      startHall(asked, key, (k, meta) => setScene((c) => (c && c.key === k ? { ...c, meta } : c)));
      return { hall: asked, key, since: performance.now(), meta: undefined, status: "loading" };
    });
  }, [wanted, asked]);

  if (want) last.current = want.w;
  else if (!scene) last.current = null;
  const w = want?.w ?? last.current;
  const ref = useRef(w);
  ref.current = w;
  const film = useRef<{ key: number; film: Film | null | undefined }>({ key: 0, film: undefined });
  if (scene && film.current.key !== scene.key) film.current = { key: scene.key, film: undefined };
  if (scene && w?.film !== undefined) film.current.film = w.film; // a page that does not know the film keeps the picture
  const baked = useMemo(() => (scene?.meta ? bakedSeatMap(scene.meta) : null), [scene?.meta]);
  const map = w?.map ?? baked;
  const meta = scene?.meta;
  const noCorridor = !!w?.corridor && meta !== undefined && !meta?.corridor;
  const mount = !!scene && !!w && meta !== undefined && !!map && !noCorridor && scene.status !== "failed";
  const status: HostStatus = !scene ? "none" : scene.status === "failed" || noCorridor || (meta !== undefined && !map) ? "failed" : scene.status;
  const view = useMemo<HostView>(() => (scene ? { hall: scene.hall, status, meta } : NO_VIEW), [scene?.hall, status, meta]); // eslint-disable-line react-hooks/exhaustive-deps
  const ctx = useMemo<Ctx>(() => ({ holder, view, want: wantFn }), [holder, view, wantFn]);

  const sceneKey = scene?.key;
  const mark = useCallback((s: "shown" | "failed") => setScene((c) => (c && c.key === sceneKey && c.status !== s ? { ...c, status: s } : c)), [sceneKey]);
  const onShown = useCallback(() => mark("shown"), [mark]);
  const onFail = useCallback(() => mark("failed"), [mark]);
  // stable handlers that always reach the current page's
  const h = useMemo(() => ({
    tap: (s: Seat, v: Visual) => ref.current?.onTap?.(s, v),
    look: (s: Seat) => ref.current?.onLook?.(s),
    hover: (s: Seat | null) => ref.current?.onHover?.(s),
    moving: (m: boolean) => ref.current?.onMoving?.(m),
    walked: () => ref.current?.onWalked?.(),
  }), []);
  const d = meta?.corridor?.door;
  const door = d && w?.door ? (d.sign ?? 1) * d[w.door] : undefined;

  return (
    <HostCtx.Provider value={ctx}>
      {children}
      {holder && mount ? createPortal(
        <Guard key={scene.key} onFail={onFail}>
          <Suspense fallback={null}>
            <HallScene map={map} film={film.current.film} mine={w.mine ?? NONE} mode={w.mode} seatId={w.seatId ?? null}
                       onTap={h.tap} onLook={h.look} onHover={h.hover} onMoving={h.moving} onWalked={h.walked} onShown={onShown}
                       meta={meta} hallNo={scene.hall} since={scene.since} locked={!!w.locked} houseDown={!!w.houseDown}
                       door={door} walk={!!w.walk} intro={w.intro} cover={w.cover ?? NO_COVER} />
          </Suspense>
        </Guard>, holder) : null}
    </HostCtx.Provider>
  );
}

/** Say what this page wants of the hall (re-sent on every render; the last page to ask is the one served). */
export function useHall(w: HallWant | null): HostView {
  const ctx = useContext(HostCtx);
  const [id] = useState(() => Symbol("hall-slot"));
  useLayoutEffect(() => ctx?.want(id, w));
  useLayoutEffect(() => () => ctx?.want(id, null), [ctx?.want, id]); // eslint-disable-line react-hooks/exhaustive-deps
  return ctx?.view ?? NO_VIEW;
}

/** The hall that is up now, without asking for one. */
export function useHostView(): HostView {
  return useContext(HostCtx)?.view ?? NO_VIEW;
}

/** Where the hall's canvas sits on this page. */
export function HallSlot({ className }: { className?: string }) {
  const holder = useContext(HostCtx)?.holder ?? null;
  const ref = useRef<HTMLDivElement>(null);
  useLayoutEffect(() => {
    const el = ref.current;
    if (!holder || !el) return;
    el.appendChild(holder);
    return () => {
      if (holder.parentNode === el) el.removeChild(holder);
    };
  }, [holder]);
  return <div ref={ref} className={className ?? "fr-hall-slot"} />;
}

/** CR-014: set by the film page's door just before the URL becomes the seat page, after the walk: that page's panel
 *  and toolbar slide in over the hall that is already there. Good for one page open (2 s), and read without clearing,
 *  so StrictMode's second render reads the same answer. */
let walkedInto: { id: number; at: number } | null = null;
export function walkedTo(showtimeId: number): void {
  walkedInto = { id: showtimeId, at: performance.now() };
}
export function takeWalked(showtimeId: number): boolean {
  return walkedInto?.id === showtimeId && performance.now() - walkedInto.at < 2000;
}

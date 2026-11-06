// SRC-008 WAIT-1: while the free Render API wakes from idle (up to ~90 s), the visitor explores the baked Grand hall,
// whose cinema screen shows a countdown and the reason. The normal site mounts the moment the API answers.
// Readiness is GET /api/auth/me - the call the header makes anyway - never /health/*: a privacy blocker blocks
// health-shaped URLs and the page would wait for ever (web-app-pitfalls 1; /health/* is also outside the /api/*
// rewrite on Render). "Up" is any JSON answer, a 401 included: a waking host answers with its own HTML page.
import { Suspense, lazy, useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { Guard, canDraw } from "../hall3d/Hall3D";
import type { BakedMeta, Mode } from "../hall3d/hall";
import type { Seat } from "../seatmap/model";
import { GIVE_UP_MS, SHOW_AFTER_MS, WAKE_HALL, bakedSeatMap, paintScreen, retryDelay, screenLines, type Ink } from "./wakeup";
import "./wake.css";

const HallScene = lazy(() => import("../hall3d/HallScene"));
const PROBE = "/api/auth/me";
const ATTEMPT_MS = 15_000; // a cold start holds the request open; past this it is retried
const reduced = () => window.matchMedia("(prefers-reduced-motion: reduce)").matches;

async function probe(): Promise<"up" | "down" | "blocked"> {
  const ctl = new AbortController();
  const t = setTimeout(() => ctl.abort(), ATTEMPT_MS);
  try {
    const r = await fetch(PROBE, { credentials: "same-origin", cache: "no-store", signal: ctl.signal });
    return (r.headers.get("content-type") ?? "").includes("json") ? "up" : "down";
  } catch (e) {
    // web-app-pitfalls 2: a timeout is "still coming"; a fast network-level failure may be "never"
    return (e as Error).name === "AbortError" ? "down" : "blocked";
  } finally {
    clearTimeout(t);
  }
}

type Phase = "checking" | "waiting" | "leaving" | "open";

export function Wake({ children }: { children: ReactNode }) {
  const [phase, setPhase] = useState<Phase>("checking");
  const [t0] = useState(() => performance.now());
  useEffect(() => {
    let live = true;
    const slow = setTimeout(() => live && setPhase((p) => (p === "checking" ? "waiting" : p)), SHOW_AFTER_MS);
    const done = () => {
      clearTimeout(slow);
      if (live) setPhase((p) => (p === "checking" || reduced() ? "open" : "leaving"));
    };
    void (async () => {
      let blocked = 0;
      for (let i = 0; live; i++) {
        const r = await probe();
        if (r === "up") return done();
        blocked = r === "blocked" ? blocked + 1 : 0;
        // three fast failures in a row, or the ceiling: let the app load and show its own errors (pitfalls 2)
        if (blocked >= 3 || performance.now() - t0 > GIVE_UP_MS) return done();
        await new Promise((res) => setTimeout(res, retryDelay(i)));
      }
    })();
    return () => {
      live = false;
      clearTimeout(slow);
    };
  }, [t0]);
  useEffect(() => {
    if (phase !== "leaving") return;
    const t = setTimeout(() => setPhase("open"), 700); // the fade in wake.css
    return () => clearTimeout(t);
  }, [phase]);

  if (phase === "checking" || phase === "open") return <>{children}</>;
  // While waiting, the app is not mounted: its own calls would fail against the sleeping API. It mounts fresh after.
  return (
    <>
      {phase === "leaving" ? children : null}
      <WakeScreen t0={t0} leaving={phase === "leaving"} onSkip={() => setPhase("open")} />
    </>
  );
}

const NONE: ReadonlySet<number> = new Set();
const CATEGORY_TIP = (seat: Seat, name: string) => `Row ${seat.row} · Seat ${seat.num} · ${name}`;

function WakeScreen({ t0, leaving, onSkip }: { t0: number; leaving: boolean; onSkip: () => void }) {
  const [sec, setSec] = useState(0);
  const [ink, setInk] = useState<Ink | null>(null);
  const [meta, setMeta] = useState<BakedMeta | null | undefined>(undefined);
  const [able] = useState(canDraw);
  const [failed, setFailed] = useState(false);
  const [mode, setMode] = useState<Mode>("seat"); // the first view faces the screen and its countdown
  const [picked, setPicked] = useState<number | null>(null);
  const [hover, setHover] = useState<Seat | null>(null);
  const [moving, setMoving] = useState(false);
  const tip = useRef<HTMLDivElement>(null);
  const plain = useRef<HTMLCanvasElement>(null);

  // The half-light palette whatever the visitor's theme: the room with the house lights down. Restored on the way out.
  useLayoutEffect(() => {
    const root = document.documentElement;
    const was = root.getAttribute("data-theme");
    root.setAttribute("data-theme", "dark");
    const css = getComputedStyle(root);
    const v = (n: string) => css.getPropertyValue(n).trim();
    setInk({ ground: v("--fr-surface-inset"), glow: v("--fr-screen-glow"), strong: v("--fr-ink-strong"), muted: v("--fr-ink-muted"),
             cyan: v("--fr-screen-ink"), fill: v("--fr-countdown-fill"), rule: v("--fr-rule-quiet") });
    return () => {
      if (was === null) root.removeAttribute("data-theme");
      else root.setAttribute("data-theme", was);
    };
  }, []);
  useEffect(() => {
    const tick = () => setSec(Math.floor((performance.now() - t0) / 1000));
    tick();
    const t = setInterval(tick, 1000); // one repaint, and so one 3D frame, per second
    return () => clearInterval(t);
  }, [t0]);
  useEffect(() => {
    let live = true;
    fetch(`/halls/hall${WAKE_HALL}.json`).then((r) => (r.ok ? r.json() : null)).catch(() => null)
      .then((m: BakedMeta | null) => live && setMeta(m?.seats?.length ? m : null));
    return () => {
      live = false;
    };
  }, []);
  const map = useMemo(() => (meta ? bakedSeatMap(meta) : null), [meta]);

  const paint = useCallback((g: CanvasRenderingContext2D, w: number, h: number) => {
    if (ink) paintScreen(g, w, h, sec * 1000, ink);
  }, [sec, ink]);
  const three = able && !failed && !!meta && !!map;
  // No bake (hall 6 not rendered yet), no WebGL or a scene error: the same picture on a plain canvas, the plain screen.
  useEffect(() => {
    const c = plain.current;
    if (!c || three || meta === undefined) return;
    const box = c.getBoundingClientRect();
    const dpr = Math.min(2, window.devicePixelRatio || 1);
    c.width = Math.round(box.width * dpr);
    c.height = Math.round(box.height * dpr);
    paint(c.getContext("2d")!, c.width, c.height);
  }, [paint, three, meta]);
  const onMoving = useCallback((m: boolean) => {
    setMoving(m);
    if (m) setHover(null);
  }, []);

  const { title, clock } = screenLines(sec * 1000);
  const names = new Map(map?.categories.map((c) => [c.id, c.name]) ?? []);
  const at = map?.seats.find((s) => s.id === picked);
  const tap = window.matchMedia("(hover: none)").matches ? "Tap" : "Click";
  const caption = !three ? "" : mode === "all" ? `Drag to look around. ${tap} a seat to see the screen from it.`
    : at ? `The view from row ${at.row}, seat ${at.num} · ${names.get(at.cat)}.` : `The view from the middle of the hall. ${tap} a seat to sit there.`;

  return (
    <div className="fr-wake" data-leaving={leaving || undefined}>
      <div className="fr-wake-stage" onPointerMove={(e) => {
        tip.current?.style.setProperty("transform", `translate(${e.clientX + 14}px, ${e.clientY + 18}px)`);
      }}>
        {three ? (
          <Guard onFail={() => setFailed(true)}>
            <Suspense fallback={null}>
              <HallScene map={map} film={null} mine={NONE} mode={mode} seatId={mode === "seat" ? picked : null}
                         onTap={() => undefined /* nothing can be held or booked here */}
                         onLook={(s) => { setMode("seat"); setPicked(s.id); }}
                         onHover={setHover} onMoving={onMoving} meta={meta} hallNo={WAKE_HALL} paint={paint} />
            </Suspense>
          </Guard>
        ) : meta === undefined ? null : <canvas ref={plain} className="fr-wake-plain" aria-hidden="true" />}
        <div ref={tip} className="fr-wake-tip" hidden={!three || !hover || moving}>
          {hover ? CATEGORY_TIP(hover, names.get(hover.cat) ?? "") : null}
        </div>
      </div>
      <header className="fr-wake-head">
        <p className="fr-wake-brand">FrontRow</p>
        <h1 className="fr-wake-title" role="status">{title} <span className="fr-mono" aria-hidden="true">{clock}</span></h1>
      </header>
      <footer className="fr-wake-bar">
        {caption ? <p className="fr-wake-caption">{caption}</p> : null}
        <div className="fr-wake-actions">
          {three ? (
            <button type="button" className="fr-action-secondary" onClick={() => { setMode(mode === "all" ? "seat" : "all"); setPicked(null); }}>
              {mode === "all" ? "Back to the screen" : "Look around the hall"}
            </button>
          ) : null}
          <button type="button" className="fr-action-secondary" onClick={onSkip}>Open the site anyway</button>
        </div>
        <p className="fr-wake-note">Booking opens when the site is ready. Nothing here holds a seat.</p>
      </footer>
    </div>
  );
}

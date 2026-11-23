// The 3D hall itself - the lazily loaded chunk (FR-ADR-074 5). It draws the seat-map payload it is handed and holds
// no booking state: a click calls the 2D map's own tap handler, after the 2D map's own selectable() check, so every
// hold, release and refusal goes through the one path the 2D map uses. It makes no request of its own except the
// static seat models and the screen's still, /art/screen_<movieId>.jpg.
import { Canvas, useFrame, useThree, type ThreeEvent } from "@react-three/fiber";
import { OrbitControls } from "@react-three/drei";
import { Bloom, EffectComposer, ToneMapping, Vignette } from "@react-three/postprocessing";
import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import {
  BufferAttribute, CanvasTexture, Color, DataTexture, FloatType, InstancedMesh, MeshBasicMaterial, MeshPhysicalMaterial, MeshStandardMaterial, Object3D,
  PMREMGenerator, RGBAFormat, RingGeometry, SRGBColorSpace, ShaderChunk, TextureLoader, Vector3, type BufferGeometry, type Group, type Material, type Mesh,
  type PerspectiveCamera, type Texture,
} from "three";
import { HDRLoader } from "three/addons/loaders/HDRLoader.js";
import { EXPOSURE, SH_FRAG, SH_FRAG_PARS, SH_TEXELS, SH_VERT, SH_VERT_PARS, packSH } from "./seatLight";
import { AdditiveBlending, BufferGeometry as Geometry, CatmullRomCurve3, DoubleSide, Float32BufferAttribute, ShaderMaterial } from "three";
import { stillPath } from "./still";
import { FLICKER_S, flickerLevel } from "./flicker";
import { DOUBLE_MS, seatAction, type SeatGesture } from "./gestures";
import { hallDrawn } from "./hallReady";
import { loadRoom } from "./preload";
import { HALL_CAP_MS, readiness, settled, type PartState, type Parts } from "./readiness";
import { NO_GLOW, glowOf, type Glow } from "./screenGlow";
import { selectable, visualOf, type Seat, type SeatMap, type Visual } from "../seatmap/model";
import { PITCH_Z, bakedHall, computeHall, modelKind, views, type BakedMeta, type Hall, type Mode, type ModelKind, type Placed, type View } from "./hall";
import { placeholderGeometry, seatGeometry, type SeatGeo } from "./seatModels";

const GLIDE_MS = 900; // --fr-motion-change (CR-001 B.5)
const FLY_MS = 1200; // the first look at the hall: from high over the seats down to the screen-side view of them all
const FLY_FROM = new Vector3(0, 10, 12);
const KINDS: ModelKind[] = ["standard", "premium", "recliner"];
// CR-003 baked hall: each normalised seat (seatModels.ts: 0.57 m wide, facing -z) scaled to its baked Blender size
// (hall1_build.py SEAT_FIT) and turned round to face +z, where the baked screen is.
const BAKED_SCALE: Record<ModelKind, [number, number, number]> = {
  standard: [1.045, 1.007, 1.007], premium: [1.041, 1.021, 1.021], recliner: [1.946, 2.17, 2.17],
};
// A baked hall's free seats are the tan leather the owner approved in the renders (CR-003), not the velvet.
const LEATHER = new Color("#b8743a");
const ROOM_GAIN = 2.2; // the bake is the dim-house render, display-referred; lifted so the room reads on a monitor

// Colours come from the design tokens, read once from the page, so no colour is defined twice (FR-ADR-072).
function tones() {
  const css = getComputedStyle(document.documentElement);
  const t = (name: string) => {
    const v = css.getPropertyValue(name).trim();
    return v ? new Color(v) : new Color().setScalar(0.5);
  };
  return {
    field: t("--fr-surface-inset"), wall: t("--fr-surface-base"), floor: t("--fr-surface-raised"),
    // The velvet itself, not a UI state token: deep ink-blue (DESIGN-SYSTEM "half-light"; CR-001 B). Free seats only.
    free: new Color("#14214a"), other: t("--fr-seat-held-other"), sold: t("--fr-seat-sold").multiplyScalar(0.4),
    mine: t("--fr-seat-mine"), screen: t("--fr-screen-bar"), house: t("--fr-surface-accent"), glow: t("--fr-countdown-fill"),
    haze: t("--fr-screen-glow"), ink: t("--fr-ink-strong"), cyan: t("--fr-screen-ink"),
  };
}
type Tones = ReturnType<typeof tones>;

const ease = (t: number) => 1 - (1 - t) ** 4; // one ease, close to --fr-ease-out
const reducedMotion = () => window.matchMedia("(prefers-reduced-motion: reduce)").matches;

type BakedViews = ((seatId: number | null) => Record<Mode, View>) | null;
type Orbit = { target: Vector3; minAzimuthAngle: number; maxAzimuthAngle: number; minPolarAngle: number; maxPolarAngle: number; update: () => void };
const ARRIVE_MS = 5000; // the baked hall's arrival, flown live along its route (CR-004: screen first, then the seats)
const HOLD_MS = 1400; // the first waypoint is held this long: the film on the screen, before the turn
const PAN_MS = 4200; // a baked hall's turn from a seat to the all-seats view (or back), by the side wall
const TURN = 0.95, UP = 0.4, DOWN = 0.55; // a baked hall: look around ~55 deg either side, 23 deg up, 31 deg down

/** A baked hall's camera never moves when you drag: the orbit pivot sits 1 cm ahead of the eye, so dragging turns the
 *  view on the spot (it cannot pass through a wall or see outside the room), capped around the view's own direction. */
function pin(controls: Orbit | null, camera: PerspectiveCamera, look: Vector3) {
  if (!controls) return;
  const dir = look.clone().sub(camera.position).normalize();
  controls.target.copy(camera.position).addScaledVector(dir, 0.01);
  const theta = Math.atan2(-dir.x, -dir.z), phi = Math.acos(Math.max(-1, Math.min(1, -dir.y)));
  controls.minAzimuthAngle = theta - TURN; controls.maxAzimuthAngle = theta + TURN;
  controls.minPolarAngle = Math.max(0.05, phi - DOWN); controls.maxPolarAngle = Math.min(Math.PI - 0.05, phi + UP);
  controls.update();
}

function Rig({ hall, mode, seatId, onMoving, bakedViews, intro, wall, locked, go }: {
  hall: Hall; mode: Mode; seatId: number | null; onMoving: (moving: boolean) => void; bakedViews: BakedViews;
  intro: { eye: number[]; look: number[] }[] | null; wall: number | null; locked: boolean;
  /** false until the whole hall is in and drawn (readiness.ts): the camera waits on its first pose, nothing flies */
  go: boolean;
}) {
  const camera = useThree((s) => s.camera as PerspectiveCamera);
  const aspect = useThree((s) => s.size.width / Math.max(1, s.size.height));
  const view = useMemo(() => (bakedViews ? bakedViews(seatId) : views(hall, seatId, aspect))[mode], [hall, seatId, aspect, mode, bakedViews]);
  useLayoutEffect(() => {
    if (!bakedViews) return;
    // the entrance clip's lens (90 deg across at 16:9); a wider stage crops top and bottom, as the video does
    // portrait (a phone held upright): as wide as a 95 deg tall lens allows; the clip shows whole, letterboxed
    const deg = (2 * Math.atan(1 / aspect) * 180) / Math.PI;
    camera.fov = aspect >= 16 / 9 ? deg : aspect >= 1 ? 58.72 : Math.min(95, deg);
    camera.updateProjectionMatrix();
  }, [bakedViews, aspect, camera]);
  const controls = useThree((s) => s.controls) as unknown as Orbit | null;
  const gl = useThree((s) => s.gl);
  const invalidate = useThree((s) => s.invalidate);
  const look = useRef(new Vector3(...view.look));
  // where the orbit pivot goes: the look point itself, or (a baked hall) 1 cm ahead of the eye
  const settle = () => (bakedViews ? pin(controls, camera, look.current) : controls?.target.copy(look.current));
  // t0 is stamped on the first frame drawn, so a slow first frame (shader compile) does not eat the move.
  const glide = useRef<{ at0: Vector3; look0: Vector3; t0: number | null; ms: number; hold?: number; route?: [CatmullRomCurve3, CatmullRomCurve3] } | null>(null);
  const shown = useRef<View | null>(null);
  useEffect(() => {
    if (shown.current === view) { // the controls arriving re-runs this; the camera already has its orders
      if (!glide.current) settle();
      return;
    }
    const first = shown.current === null;
    shown.current = view;
    if (first || reducedMotion()) {
      const fly = first && !reducedMotion() && !bakedViews; // reduced motion cuts (CR-001 B.5)
      // a baked hall arrives along the route it is given (Hall3D: screen first, then the seats), flown live (no video)
      const arrive = !!(first && !reducedMotion() && bakedViews && intro && intro.length > 1);
      camera.position.set(...((arrive ? intro![0].eye : view.at) as [number, number, number]));
      if (fly) camera.position.add(FLY_FROM);
      look.current.set(...((arrive ? intro![0].look : view.look) as [number, number, number]));
      camera.lookAt(look.current);
      settle();
      if (fly) {
        glide.current = { at0: camera.position.clone(), look0: look.current.clone(), t0: null, ms: FLY_MS };
        onMoving(true);
      }
      if (arrive) {
        const curve = (k: "eye" | "look") => new CatmullRomCurve3(intro!.map((w) => new Vector3(w[k][0], w[k][1], w[k][2])), false, "centripetal");
        glide.current = { at0: camera.position.clone(), look0: look.current.clone(), t0: null, ms: ARRIVE_MS, hold: HOLD_MS, route: [curve("eye"), curve("look")] };
        onMoving(true);
      }
      invalidate();
      return;
    }
    // a glide starts from where the visitor looks now (a baked hall's pivot is 1 cm away, so read the camera instead)
    const from = bakedViews ? camera.position.clone().add(camera.getWorldDirection(new Vector3()).multiplyScalar(10))
      : (controls?.target ?? look.current).clone();
    // A baked hall's turn that faces the other way (a seat to the all-seats view, or back) is flown like the arrival:
    // up, and round by the side wall, so the look point never passes through the eye.
    const to = new Vector3(...view.at), toLook = new Vector3(...view.look);
    const flips = from.clone().sub(camera.position).dot(toLook.clone().sub(to)) < 0;
    if (bakedViews && wall !== null && flips) {
      const mid = camera.position.clone().add(to).multiplyScalar(0.5);
      mid.y = Math.max(camera.position.y, to.y) + 0.3;
      const c = (pts: Vector3[]) => new CatmullRomCurve3(pts, false, "centripetal");
      glide.current = { at0: camera.position.clone(), look0: from, t0: null, ms: PAN_MS,
                        // the far wall: the turn sweeps across the room, never into the wall beside a corner seat
                        route: [c([camera.position.clone(), mid, to]), c([from, new Vector3(-Math.sign(camera.position.x || 1) * wall, mid.y, mid.z), toLook])] };
    } else glide.current = { at0: camera.position.clone(), look0: from, t0: null, ms: GLIDE_MS };
    onMoving(true);
    invalidate();
  }, [view, camera, controls, invalidate, onMoving]);
  // any tap or drag during the arrival skips it to the all-seats view
  useEffect(() => {
    const skip = () => {
      if (glide.current?.route) glide.current.t0 = -1e9;
      invalidate();
    };
    gl.domElement.addEventListener("pointerdown", skip);
    return () => gl.domElement.removeEventListener("pointerdown", skip);
  }, [gl, invalidate]);
  useEffect(() => void (go && invalidate()), [go, invalidate]);
  useFrame(() => {
    const g = glide.current;
    if (!g || !go) return;
    g.t0 ??= performance.now();
    const k = Math.min(1, Math.max(0, performance.now() - g.t0 - (g.hold ?? 0)) / g.ms);
    const e = ease(k);
    if (g.route && k < 1) {
      camera.position.copy(g.route[0].getPointAt(e));
      look.current.copy(g.route[1].getPointAt(e));
    } else if (g.route) {
      camera.position.set(...view.at);
      look.current.set(...view.look);
    } else {
      camera.position.lerpVectors(g.at0, new Vector3(...view.at), e);
      look.current.lerpVectors(g.look0, new Vector3(...view.look), e);
    }
    camera.lookAt(look.current);
    settle();
    if (k < 1) invalidate();
    else {
      glide.current = null;
      onMoving(false);
    }
  });
  // Procedural hall: orbit the all-seats view only. Baked hall: turn on the spot (pin) in every view, from your seat too.
  return <OrbitControls makeDefault enabled={!locked && (!!bakedViews || mode === "all")} enablePan={false} enableDamping={false}
                        maxPolarAngle={bakedViews ? undefined : Math.PI * 0.49} rotateSpeed={bakedViews ? -0.35 : 1}
                        enableZoom={!bakedViews} minDistance={bakedViews ? 0 : 4} maxDistance={60}
                        onStart={() => onMoving(true)} onEnd={() => onMoving(false)} />;
}

/** CR-010: a baked hall whose seats carry Cycles light probes (hall_probes.py). Each seat instance is lit by its own
 *  two probes (seatLight.ts) instead of the point lights, its reflections come from the hall's Cycles panorama, and its
 *  light then goes through the bake's own curve (AgX at +0.4 EV, x ROOM_GAIN) and the screen glow, as the room does. */
type SeatLit = { glow: GlowU; env: Texture | null };
const ENV_INTENSITY = 0.7; // ponytail: the reflections are there but quiet (brass and the leather's coat); tune here
// The site's flat LEATHER is the light end of the Blender leather (#8d5024..#b87437 x its scan, mean ~0.72 of LEATHER),
// so the probe light is scaled to put the seats at the brightness Cycles renders them (render_truth.py side by side).
const SEAT_GAIN = 0.75;
// The probes already hold the screen's own light, so the live screen glow (tint, spill, sheen) is applied to the seats
// at half strength: they still follow the picture, without the front rows washing pink.
const SEAT_GLOW = 0.5;
// three's AgX (Blender's, via Filament): the canvas is `flat` (no tone mapping), so three leaves it out; borrowed here
const AGX = ShaderChunk.tonemapping_pars_fragment.replace("uniform float toneMappingExposure;", "const float toneMappingExposure = 1.0;");
function lightSeats(m: Material, shU: Record<string, { value: unknown }>, glow: GlowU) {
  m.onBeforeCompile = (sh) => {
    Object.assign(sh.uniforms, glow, shU);
    sh.vertexShader = SH_VERT_PARS + sh.vertexShader.replace("#include <project_vertex>", SH_VERT);
    sh.fragmentShader = AGX + GLOW_FRAG + SH_FRAG_PARS + sh.fragmentShader.replace("#include <lights_fragment_maps>", SH_FRAG)
      .replace("#include <opaque_fragment>", `outgoingLight = ${ROOM_GAIN.toFixed(2)} * AgXToneMapping(outgoingLight * ${EXPOSURE.toFixed(4)});\n  vec3 seatBase = outgoingLight;\n  `
        + GLOW_APPLY.replace("#include <opaque_fragment>", `outgoingLight = mix(seatBase * uHouse, outgoingLight, ${SEAT_GLOW.toFixed(2)});\n  #include <opaque_fragment>`));
  };
  m.customProgramCacheKey = () => "seat-probes";
}

function SeatKind({ kind, items, colourOf, onPick, onHover, baked, lit, mark }: {
  kind: ModelKind; items: Placed[]; colourOf: (seat: Seat) => Color; onPick: (seat: Seat, g: SeatGesture) => void; onHover: (seat: Seat | null) => void;
  baked: boolean; lit: SeatLit | null; mark: Mark;
}) {
  const ref = useRef<InstancedMesh>(null);
  const frameRef = useRef<InstancedMesh>(null);
  const invalidate = useThree((s) => s.invalidate);
  const [geo, setGeo] = useState<SeatGeo>(() => placeholderGeometry(kind));
  const geometry: BufferGeometry = geo.body;
  const glow = lit?.glow ?? null;
  const shU = useMemo(() => ({ uSH: { value: null as DataTexture | null }, uSeatGain: { value: SEAT_GAIN } }), []);
  // Upholstery reads as velvet: matte with a soft sheen. The frame keeps its baked colour (satin black, brass).
  const material = useMemo(() => {
    const m = new MeshPhysicalMaterial({ roughness: 0.85, metalness: 0, sheen: 0.4, sheenRoughness: 0.4, sheenColor: new Color("#3a5596") });
    if (glow) {
      // the leather of the ray-traced seats (hall1_build.py mat_leather): satin, a thin coat that catches the room's
      // lights, no velvet sheen
      Object.assign(m, { sheen: 0, roughness: 0.5, clearcoat: 0.12, clearcoatRoughness: 0.35 });
      lightSeats(m, shU, glow);
    }
    return m;
  }, [glow, shU]);
  const frameMaterial = useMemo(() => {
    const m = new MeshStandardMaterial({ vertexColors: true, roughness: 0.32, metalness: 0.45 });
    if (glow) lightSeats(m, { uSH: shU.uSH, uSeatGain: { value: 1 } }, glow); // the frame keeps its own albedo
    return m;
  }, [glow, shU]);
  // the probes, one texture row per instance (gl_InstanceID), in the same order as the instance matrices below
  useEffect(() => {
    if (!glow) return;
    const t = new DataTexture(packSH(items.map((p) => p.light)), SH_TEXELS, Math.max(1, items.length), RGBAFormat, FloatType);
    t.needsUpdate = true;
    shU.uSH.value = t;
    invalidate();
    return () => t.dispose();
  }, [items, glow, shU, invalidate]);
  const env = lit?.env ?? null;
  useEffect(() => {
    if (!glow) return;
    for (const m of [material, frameMaterial]) {
      m.envMap = env;
      m.envMapIntensity = ENV_INTENSITY;
      m.needsUpdate = true;
    }
    invalidate();
  }, [env, glow, material, frameMaterial, invalidate]);
  useEffect(() => {
    let live = true;
    void seatGeometry(kind).then((g) => {
      if (!live) return void (g.body.dispose(), g.frame?.dispose());
      setGeo(g);
      mark(`seat:${kind}`, "loaded"); // seatGeometry never rejects: a missing file is the stand-in
    });
    return () => {
      live = false;
    };
  }, [kind, mark]);
  useEffect(() => () => { geo.body.dispose(); geo.frame?.dispose(); }, [geo]);
  useEffect(() => () => { material.dispose(); frameMaterial.dispose(); }, [material, frameMaterial]);

  useLayoutEffect(() => {
    const meshes = [ref.current, frameRef.current].filter((m): m is InstancedMesh => !!m);
    if (!meshes.length) return;
    const o = new Object3D();
    items.forEach((p, i) => {
      o.position.set(p.x, p.y, p.z);
      o.rotation.set(0, baked ? Math.PI : 0, 0);
      if (baked) o.scale.set(...BAKED_SCALE[kind]);
      else o.scale.set(p.span, 1, 1);
      o.updateMatrix();
      meshes.forEach((m) => m.setMatrixAt(i, o.matrix));
    });
    meshes.forEach((m) => { m.instanceMatrix.needsUpdate = true; m.computeBoundingSphere(); });
    invalidate();
  }, [items, geo, invalidate, baked, kind]);
  useLayoutEffect(() => {
    const mesh = ref.current;
    if (!mesh) return;
    items.forEach((p, i) => mesh.setColorAt(i, colourOf(p.seat)));
    if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true;
    invalidate();
  }, [items, colourOf, geo, invalidate]);

  const seatAt = (e: ThreeEvent<PointerEvent | MouseEvent>) => (e.instanceId === undefined ? null : items[e.instanceId]?.seat ?? null);
  // gestures.ts: a click waits DOUBLE_MS, so the second click of a double click cancels it and the camera stays put
  const single = useRef(0);
  useEffect(() => () => clearTimeout(single.current), []);
  return (
    <>
    {geo.frame && <instancedMesh key={"f" + items.length} ref={frameRef} args={[geo.frame, frameMaterial, items.length]} raycast={() => null} />}
    <instancedMesh key={items.length} ref={ref} args={[geometry, material, items.length]}
      onClick={(e) => {
        e.stopPropagation();
        const s = seatAt(e);
        clearTimeout(single.current);
        if (!s || e.delta >= 6 || e.nativeEvent.detail >= 2) return; // a drag to look around is not a tap
        single.current = window.setTimeout(() => onPick(s, "click"), DOUBLE_MS);
      }}
      onDoubleClick={(e) => {
        e.stopPropagation();
        clearTimeout(single.current);
        const s = seatAt(e);
        if (s) onPick(s, "double");
      }}
      onContextMenu={(e) => {
        e.stopPropagation();
        const s = seatAt(e);
        if (!s) return;
        e.nativeEvent.preventDefault(); // a right click on a seat is ours, not the browser's menu
        onPick(s, "right");
      }}
      onPointerMove={(e) => {
        e.stopPropagation();
        onHover(seatAt(e));
      }}
      onPointerOut={() => onHover(null)} />
    </>
  );
}

/** A cyan pool of light under each of your seats - "yours" is screen-light (DESIGN-SYSTEM.md 1). */
function Halos({ placed, mine, tone }: { placed: Placed[]; mine: ReadonlySet<number>; tone: Tones }) {
  const ref = useRef<InstancedMesh>(null);
  const invalidate = useThree((s) => s.invalidate);
  const geometry = useMemo(() => new RingGeometry(0.22, 0.42, 32).rotateX(-Math.PI / 2), []);
  const material = useMemo(() => new MeshBasicMaterial({ color: tone.mine.clone().multiplyScalar(3), toneMapped: false }), [tone]);
  useEffect(() => () => { geometry.dispose(); material.dispose(); }, [geometry, material]);
  useLayoutEffect(() => {
    const mesh = ref.current;
    if (!mesh) return;
    const o = new Object3D();
    let n = 0;
    for (const p of placed) {
      if (!mine.has(p.seat.id) || p.seat.state === "sold") continue;
      o.position.set(p.x, p.y + 0.03, p.z + 0.05);
      o.scale.set(p.span, 1, 1);
      o.updateMatrix();
      mesh.setMatrixAt(n++, o.matrix);
    }
    mesh.count = n;
    mesh.instanceMatrix.needsUpdate = true;
    invalidate();
  }, [placed, mine, invalidate]);
  return <instancedMesh ref={ref} args={[geometry, material, Math.max(1, placed.length)]} raycast={() => null} />;
}

export type Film = { id: number; title: string };
/** Reports one part of the hall loaded or failed (readiness.ts). */
type Mark = (part: string, state: PartState) => void;

/** The title card: the film's name in the display face over a dark cinematic gradient, at the screen's 2.39:1. */
function titleCard(title: string, tone: Tones): Texture {
  const c = document.createElement("canvas");
  c.width = 2048;
  c.height = Math.round(2048 / 2.39);
  const g = c.getContext("2d")!;
  const { width: w, height: h } = c;
  const bg = g.createRadialGradient(w / 2, h * 0.45, h * 0.05, w / 2, h / 2, w * 0.6);
  bg.addColorStop(0, tone.haze.getStyle());
  bg.addColorStop(1, tone.field.getStyle());
  g.fillStyle = bg;
  g.fillRect(0, 0, w, h);
  const flare = g.createLinearGradient(0, 0, w, 0); // one anamorphic streak behind the title
  flare.addColorStop(0, "transparent");
  flare.addColorStop(0.5, tone.cyan.getStyle());
  flare.addColorStop(1, "transparent");
  g.globalAlpha = 0.35;
  g.fillStyle = flare;
  g.fillRect(0, h * 0.535, w, 3);
  g.globalAlpha = 1;
  g.textAlign = "center";
  g.textBaseline = "middle";
  if (title) {
    let size = h * 0.22;
    do g.font = `800 ${size}px "Inter Tight", system-ui, sans-serif`;
    while (g.measureText(title).width > w * 0.84 && (size *= 0.92) > h * 0.07);
    g.fillStyle = tone.ink.getStyle();
    g.shadowColor = tone.cyan.getStyle();
    g.shadowBlur = 40;
    g.fillText(title, w / 2, h * 0.5);
    g.shadowBlur = 0;
    g.font = `400 ${h * 0.045}px "JetBrains Mono", monospace`;
    g.fillStyle = tone.cyan.getStyle();
    g.fillText("N O W   S H O W I N G", w / 2, h * 0.29);
  }
  const t = new CanvasTexture(c);
  t.colorSpace = SRGBColorSpace;
  t.anisotropy = 8;
  return t;
}

/** What the screen shows: /art/screen_<movieId>.jpg when that still is deployed, else the title card. */
/** `film` undefined: the page does not know the film yet, so nothing is drawn (and "still" stays loading) until it does.
 *  "still" is reported once the title card is made and the still has loaded or is known to be absent (the card stays). */
function useScreenArt(film: Film | null | undefined, tone: Tones, mark: Mark): Texture | null {
  const invalidate = useThree((s) => s.invalidate);
  const [art, setArt] = useState<Texture | null>(null);
  useEffect(() => {
    let live = true;
    let still = false; // a still that loaded wins over the title card, whichever lands first
    const made: Texture[] = [];
    const show = (t: Texture, isStill: boolean) => {
      if (!live) return t.dispose();
      made.push(t);
      if (still && !isStill) return;
      still ||= isStill;
      setArt(t);
      invalidate();
    };
    if (film === undefined) return;
    const title = film?.title ?? "";
    const card = Promise.all([document.fonts.load(`800 120px "Inter Tight"`), document.fonts.load(`400 40px "JetBrains Mono"`)])
      .catch(() => null).then(() => show(titleCard(title, tone), false));
    // CR-006: a demo film's poster redirects to /art/films/<slug>.webp; its screen still sits beside it as
    // <slug>-still.webp. Any other poster (the bucket's) has no still: the title card stays.
    const pic = !film ? null : stillPath(film.id, (u, init) => fetch(u, init)).then((path) => new Promise<void>((done) => {
      if (!path || !live) return done();
      new TextureLoader().load(path, (t) => {
        t.colorSpace = SRGBColorSpace;
        t.userData.still = true; // the film is on: the house lights may go down
        show(t, true);
        done();
      }, undefined, () => done());
    })).catch(() => null);
    void Promise.all([card, pic]).then(() => live && mark("still", "loaded"));
    return () => {
      live = false;
      made.forEach((t) => t.dispose());
    };
  }, [film === undefined, film?.id, film?.title, tone, invalidate, mark]); // eslint-disable-line react-hooks/exhaustive-deps
  return art;
}

/** A screen picture the caller paints (SRC-008 WAIT-1, the cold-start countdown): one canvas, repainted whenever
 *  `paint` changes - the caller changes it once a second - and one frame drawn per repaint (frameloop "demand"). */
export type Paint = (g: CanvasRenderingContext2D, w: number, h: number) => void;
function usePainted(paint: Paint | null, aspect: number): Texture | null {
  const invalidate = useThree((s) => s.invalidate);
  const on = !!paint;
  const tex = useMemo(() => {
    if (!on) return null;
    const c = document.createElement("canvas");
    c.width = 2048;
    c.height = Math.round(2048 / aspect);
    const t = new CanvasTexture(c);
    t.colorSpace = SRGBColorSpace;
    t.anisotropy = 8;
    return t;
  }, [on, aspect]);
  useEffect(() => () => tex?.dispose(), [tex]);
  useEffect(() => {
    if (!tex || !paint) return;
    const c = tex.image as HTMLCanvasElement;
    paint(c.getContext("2d")!, c.width, c.height);
    tex.needsUpdate = true;
    invalidate();
  }, [tex, paint, invalidate]);
  return tex;
}

/** CR-003: the Blender-baked room, /halls/hallN.glb. bake_* meshes carry their light in the texture and draw unlit;
 *  emit_* (LED strips, step lights, signs) are flat colour above 1 for the bloom; the screen shows the same picture as
 *  the procedural hall. Seats are not in the file - SeatKind draws them, live, lit by the lights below. */
/** The projector beam through the haze, and the dust drifting in it (the demo's, CR-003): a cone from the projector
 *  port to the screen's corners, bright where seen edge-on so it reads as a soft shaft, plus specks that drift. The
 *  dust keeps the canvas drawing every frame; with reduced motion it holds still and nothing redraws. */
const N_DUST = 600; // owner, 2026-11-23: "reduce them a bit" (was 900)
/** Dust sizes (owner, 2026-11-23: "some large and some fine, same size looks weird"): most specks fine, some medium, a
 *  few large and fainter. [share of the specks, size in metres, opacity] */
const DUST_SIZES: [number, number, number][] = [[0.7, 0.008, 0.6], [0.25, 0.016, 0.5], [0.05, 0.03, 0.35]];
/** The light the screen casts right now (BakedRoom eases it toward each new picture); the beam and the dust read it. */
const WHITE = new Color(1, 1, 1);
const WARM_FILL = new Color("#6b4a3a");
const HOUSE_WARM = new Color("#e8a868");
const SCREEN_LIGHT = { color: new Color(0.78, 0.85, 1.0), luma: 0.25, flick: 1 }; // flick: the projector stutter (flicker.ts)
const BEAM = new ShaderMaterial({
  transparent: true, depthWrite: false, side: DoubleSide, blending: AdditiveBlending, vertexColors: true,
  uniforms: { uTint: { value: new Color(0.78, 0.85, 1.0) } },
  // ponytail: the site's bloom lifts it, so it is dimmer than the demo's, and it fades out within 6 m of the eye (seen
  // from under it, a cone face is a flat grey sheet). Tune: the 1.6 and the smoothstep range.
  vertexShader: "varying vec3 vC; varying vec3 vN; varying vec3 vV; varying float vD; void main(){ vC = color; vec4 mv = modelViewMatrix * vec4(position,1.0); vN = normalize(normalMatrix * normal); vV = normalize(-mv.xyz); vD = -mv.z; gl_Position = projectionMatrix * mv; }",
  fragmentShader: "uniform vec3 uTint; varying vec3 vC; varying vec3 vN; varying vec3 vV; varying float vD; void main(){ float edge = 1.0 - abs(dot(vN, vV)); float a = pow(edge, 4.0) * vC.r * 1.6 * smoothstep(1.5, 6.0, vD); gl_FragColor = vec4(uTint * a, 1.0); }",
});
function Haze({ meta }: { meta: BakedMeta }) {
  const invalidate = useThree((s) => s.invalidate);
  const { beam, groups } = useMemo(() => {
    const port = new Vector3(...(meta.port ?? [0, meta.screen.zc + 1.8, meta.allseats.look[2] - 6]) as [number, number, number]);
    const { w, h, zc } = meta.screen, z = meta.screen.z - 0.03, bottom = zc - h / 2;
    const corner = ([sx, sy]: number[]) => new Vector3((sx * w) / 2, bottom + sy * h, z);
    const cs = [[-1, 0], [1, 0], [1, 1], [-1, 1]].map(corner);
    const pos: number[] = [], col: number[] = [];
    for (let i = 0; i < 4; i++) {
      pos.push(...port.toArray(), ...cs[i].toArray(), ...cs[(i + 1) % 4].toArray());
      col.push(0.05, 0.05, 0.05, 0, 0, 0, 0, 0, 0); // bright at the lens, fading to nothing at the screen
    }
    const beam = new Geometry();
    beam.setAttribute("position", new Float32BufferAttribute(pos, 3));
    beam.setAttribute("color", new Float32BufferAttribute(col, 3));
    beam.computeVertexNormals();
    // a fixed scatter: the booking key is the only randomness allowed in frontend/src (S-PAY-12, checkout.test)
    const r = (n: number) => { const x = Math.sin(n * 12.9898) * 43758.5453; return x - Math.floor(x); };
    const seeds = Array.from({ length: N_DUST }, (_, i) => {
      const target = new Vector3((r(5 * i) - 0.5) * w, bottom + r(5 * i + 1) * h, z);
      return { base: port.clone().lerp(target, 0.08 + r(5 * i + 2) * 0.85), ph: r(5 * i + 3) * 6.28, sp: 0.15 + r(5 * i + 4) * 0.35 };
    });
    // each speck's size class from its own fixed draw, so the classes are mixed through the whole beam
    let from = 0;
    const groups = DUST_SIZES.map(([share, size, opacity], k) => {
      const to = k === DUST_SIZES.length - 1 ? 1 : from + share;
      const mine = seeds.filter((_, i) => { const u = r(7 * i + 11); return u >= from && u < to; });
      from = to;
      const dust = new Geometry();
      dust.setAttribute("position", new Float32BufferAttribute(mine.flatMap((s) => s.base.toArray()), 3));
      return { dust, seeds: mine, size, opacity };
    });
    return { beam, groups };
  }, [meta]);
  const dot = useMemo(() => {
    const c = document.createElement("canvas");
    c.width = c.height = 32;
    const x = c.getContext("2d")!, g = x.createRadialGradient(16, 16, 0, 16, 16, 16);
    g.addColorStop(0, "rgba(255,255,255,1)");
    g.addColorStop(1, "rgba(255,255,255,0)");
    x.fillStyle = g;
    x.fillRect(0, 0, 32, 32);
    return new CanvasTexture(c);
  }, []);
  const still = useMemo(reducedMotion, []);
  // The dust is the only thing moving in an idle hall, so it sets the redraw rate: ~24 frames a second, not every
  // display frame (owner, 2026-11-22: "lightweight"). Slow drifting specks read the same at 24.
  const next = useRef(0);
  useEffect(() => () => clearTimeout(next.current), []);
  const specks = useRef<({ color: Color } | null)[]>([]);
  useFrame(({ clock }) => {
    // the beam and its dust carry the picture's light: whiter than the picture (a projector beam is mostly white
    // light), brighter for a bright frame
    BEAM.uniforms.uTint.value.copy(SCREEN_LIGHT.color).lerp(WHITE, 0.45).multiplyScalar((0.55 + 0.9 * SCREEN_LIGHT.luma) * SCREEN_LIGHT.flick);
    // the specks are only seen in the beam's light, so they flicker with the projector (flicker.ts) like the beam does
    for (const m of specks.current) m?.color.copy(SCREEN_LIGHT.color).lerp(WHITE, 0.55).multiplyScalar(SCREEN_LIGHT.flick);
    if (still) return;
    const t = clock.getElapsedTime();
    for (const { dust, seeds } of groups) {
      const a = dust.attributes.position as BufferAttribute;
      seeds.forEach((s, i) => a.setXYZ(i, s.base.x + Math.sin(t * s.sp + s.ph) * 0.05, s.base.y + Math.sin(t * s.sp * 0.7 + s.ph * 2) * 0.06,
        s.base.z + Math.cos(t * s.sp * 0.5 + s.ph) * 0.05));
      a.needsUpdate = true;
    }
    clearTimeout(next.current);
    next.current = window.setTimeout(invalidate, 42);
  });
  return (
    <>
      <mesh geometry={beam} material={BEAM} renderOrder={2} />
      {groups.map((g, k) => (
        <points key={k} geometry={g.dust} renderOrder={3}>
          <pointsMaterial ref={(m) => void (specks.current[k] = m)} size={g.size} map={dot} transparent depthWrite={false}
                          blending={AdditiveBlending} color="#d9e4ff" opacity={g.opacity} toneMapped={false} />
        </points>
      ))}
    </>
  );
}

/** The screen's picture, averaged into the light it casts (screenGlow.ts). */
function sampleGlow(t: Texture | null): Glow {
  const img = t?.image as (CanvasImageSource & { width: number; height: number }) | undefined;
  if (!img?.width) return NO_GLOW;
  try {
    const c = document.createElement("canvas");
    c.width = 64;
    c.height = 27;
    const g = c.getContext("2d", { willReadFrequently: true })!;
    g.imageSmoothingQuality = "high";
    g.drawImage(img, 0, 0, 64, 27);
    return glowOf(g.getImageData(0, 0, 64, 27).data, 64, 27);
  } catch {
    return NO_GLOW;
  }
}

/** The baked room lit by the screen (owner, 2026-11-22: "if there is something bright on the screen the whole theatre
 *  colors do change ... I want the light to make sense and feel real"). The bake is fixed light, so this adds what the
 *  picture casts, per pixel, on top of it:
 *   - the surface takes the picture's hue, strongest near the screen and falling off with distance like a lamp
 *     (1 / (1 + 0.015 d^2) over the metres d from the screen plane);
 *   - the picture's left half lights the side of the room it is on (the picture is mirrored onto +x), the right half
 *     the other side, blended across the room;
 *   - the whole room lifts for a bright frame and sinks for a dark one;
 *   - more of the picture's colour is reflected where the light falls hardest (the spill on the front rows). Every term
 *     scales the surface's own baked light, as real reflected light scales with albedo: a black seat stays black,
 *     and nothing is added as a flat wash (that read as fog).
 *  The uniforms ease toward each new picture over about a second (a cut on a real screen re-lights the room; it does
 *  not flicker). Tune: 0.015 (reach), 0.22 + 0.38 (tint), 0.74 + 0.56 (brightness swing), 0.55 (spill), 0.6 + 0.8 (sheen). */
const GLOW_VERT = "#include <begin_vertex>\n  vRoomW = (modelMatrix * vec4(transformed, 1.0)).xyz;";
const GLOW_FRAG = "uniform float uHouse; uniform vec3 uGlowPos; uniform vec3 uGlowNeg; uniform float uLuma; uniform float uScreenZ; uniform float uHalfW;\nvarying vec3 vRoomW;\n";
const GLOW_APPLY = `outgoingLight *= uHouse;
  float glowD = max(0.0, uScreenZ - vRoomW.z);
  float glowNear = 1.0 / (1.0 + 0.015 * glowD * glowD);
  vec3 glow = mix(uGlowNeg, uGlowPos, smoothstep(-uHalfW, uHalfW, vRoomW.x));
  vec3 glowHue = glow / max(max(glow.r, glow.g), max(glow.b, 0.05));
  outgoingLight *= mix(vec3(1.0), glowHue, 0.22 + 0.38 * glowNear) * (0.74 + 0.56 * uLuma * (0.35 + 0.65 * glowNear))
    + glow * glowNear * 0.55;
  // the sheen: every surface reflects some of the screen's own colour in proportion to how lit it already is (its
  // luminance, not its paint colour), so a cyan frame turns even the orange panels cool and a red frame warms them
  outgoingLight += glowHue * glowNear * dot(outgoingLight, vec3(0.2126, 0.7152, 0.0722)) * (0.6 + 0.8 * uLuma);
  #include <opaque_fragment>`;

/** House lights (owner, 2026-11-22): up while seats are being chosen, down once the film's still is on the screen.
 *  "down" is the level the room's baked light, the downlights and the wall strips sink to; the exit and entry signs, the
 *  step lights and the projector port stay lit, as they do in a real cinema. Eased over ~1 s, like a dimmer; also down while you sit in a seat on the seat page. */
const HOUSE_DOWN = 0.55;
const DIMMED = /^emit_(dl|led_strip)/;

/** The light on the room now (BakedRoom eases it toward the light the current picture casts); the probe-lit seats
 *  (CR-010) take the same uniforms, so they dim and tint with the room. */
function glowUniforms(meta: BakedMeta) {
  return {
    uHouse: { value: 1 },
    uGlowPos: { value: new Color(...NO_GLOW.left) }, uGlowNeg: { value: new Color(...NO_GLOW.right) },
    uLuma: { value: NO_GLOW.luma }, uScreenZ: { value: meta.screen.z },
    uHalfW: { value: Math.max(...meta.seats.map((s) => Math.abs(s.pos[0]))) + 2 },
  };
}
type GlowU = ReturnType<typeof glowUniforms>;

/** CR-010 L2: the hall's Cycles panorama (/halls/hallN_env.hdr), pre-filtered for the seats' reflections. */
function useHallEnv(file: string | undefined, mark: Mark): Texture | null {
  const gl = useThree((s) => s.gl);
  const [env, setEnv] = useState<Texture | null>(null);
  useEffect(() => {
    if (!file) return;
    let live = true, made: Texture | null = null;
    new HDRLoader().load(`/halls/${file}`, (t) => {
      const pm = new PMREMGenerator(gl);
      made = pm.fromEquirectangular(t).texture;
      pm.dispose();
      t.dispose();
      if (!live) return made.dispose();
      setEnv(made);
      mark("env", "loaded");
    }, undefined, () => live && mark("env", "failed")); // no panorama: the seats keep their probe light, without reflections
    return () => {
      live = false;
      made?.dispose();
    };
  }, [file, gl, mark]);
  return env;
}

function BakedRoom({ n, film, tone, meta, paint, houseDown, glowU, mark }: {
  n: number; film: Film | null | undefined; tone: Tones; meta: BakedMeta; paint: Paint | null; houseDown: boolean; glowU: GlowU; mark: Mark;
}) {
  const invalidate = useThree((s) => s.invalidate);
  const painted = usePainted(paint, meta.screen.w / meta.screen.h);
  const still = useScreenArt(film, tone, mark);
  const art = painted ?? still;
  const [room, setRoom] = useState<Group | null>(null);
  const screen = useRef<Mesh | null>(null);
  const shown = useRef<{ material: MeshBasicMaterial; base: Color } | null>(null);
  const flickFrom = useRef(-1); // performance.now() of the film change; -1 when no flicker is running
  const target = useRef<Glow>(NO_GLOW);
  const lamps = useRef<{ material: MeshBasicMaterial; full: Color }[]>([]);
  const seatLight = useRef<{ color: Color; intensity: number } | null>(null);
  const fill = useRef<{ color: Color; intensity: number } | null>(null);
  const house = useRef<{ color: Color; intensity: number } | null>(null);
  useEffect(() => {
    let live = true;
    // the parse may already be done: the film page starts it (preload.ts); the clone keeps the cached scene untouched
    loadRoom(n).then((gl) => {
      if (!live) return;
      const g = { scene: gl.scene.clone(true) };
      g.scene.traverse((o) => {
        const m = o as Mesh;
        if (!m.isMesh) return;
        const was = m.material as MeshStandardMaterial;
        if (m.name.startsWith("bake_")) {
          const lit = new MeshBasicMaterial({ map: was.map, color: new Color(ROOM_GAIN, ROOM_GAIN, ROOM_GAIN), toneMapped: false });
          lit.onBeforeCompile = (sh) => {
            Object.assign(sh.uniforms, glowU);
            sh.vertexShader = "varying vec3 vRoomW;\n" + sh.vertexShader.replace("#include <begin_vertex>", GLOW_VERT);
            sh.fragmentShader = GLOW_FRAG + sh.fragmentShader.replace("#include <opaque_fragment>", GLOW_APPLY);
          };
          m.material = lit;
        } else if (m.name.includes("screen")) {
          const geo = m.geometry;
          geo.computeBoundingBox();
          const bb = geo.boundingBox!, pos = geo.attributes.position, uv = new Float32Array(pos.count * 2);
          for (let i = 0; i < pos.count; i++) {
            // the seats look along -z at a screen facing +z, so the picture's left is the mesh's +x (unmirrored)
            uv[2 * i] = (bb.max.x - pos.getX(i)) / (bb.max.x - bb.min.x);
            uv[2 * i + 1] = (pos.getY(i) - bb.min.y) / (bb.max.y - bb.min.y);
          }
          geo.setAttribute("uv", new BufferAttribute(uv, 2));
          screen.current = m;
        } else if (m.name.startsWith("emit_")) {
          const full = was.emissive.clone().multiplyScalar(Math.min(was.emissiveIntensity * 0.6, 6));
          m.material = new MeshBasicMaterial({ color: full.clone(), toneMapped: false });
          if (DIMMED.test(m.name)) lamps.current.push({ material: m.material as MeshBasicMaterial, full });
        }
      });
      setRoom(g.scene);
      mark("room", "loaded"); // GLTFLoader answers once the room's textures are in too
      invalidate();
    }, () => live && mark("room", "failed")); // no room file: the page's fallback (readiness.ts)
    return () => {
      live = false;
    };
  }, [n, invalidate, glowU, mark]);
  useEffect(() => {
    target.current = sampleGlow(art);
    invalidate();
  }, [art, invalidate]);
  const down = houseDown && !!art?.userData.still;
  useEffect(() => invalidate(), [down, invalidate]);
  useFrame((_, delta) => {
    const k = 1 - Math.exp(-Math.min(delta, 0.1) * 3); // ~1 s to settle on a new picture
    const level = down ? HOUSE_DOWN : 1;
    const dimming = Math.abs(glowU.uHouse.value - level) > 1e-3;
    // ~1 s to settle (owner, 2026-11-23: "slowly dim the lighting in 1 second"), eased like a dimmer: 97% by 1 s
    glowU.uHouse.value += (level - glowU.uHouse.value) * (1 - Math.exp(-Math.min(delta, 0.1) * 3.5));
    for (const l of lamps.current) l.material.color.copy(l.full).multiplyScalar(glowU.uHouse.value);
    const t = target.current;
    const off = (c: Color, v: Glow["left"]) => Math.abs(c.r - v[0]) + Math.abs(c.g - v[1]) + Math.abs(c.b - v[2]);
    const settling = Math.abs(t.luma - glowU.uLuma.value) > 1e-3 || off(glowU.uGlowPos.value, t.left) > 3e-3
      || off(glowU.uGlowNeg.value, t.right) > 3e-3; // redraw only while the light is still moving
    glowU.uGlowPos.value.lerp(new Color(...t.left), k);
    glowU.uGlowNeg.value.lerp(new Color(...t.right), k);
    glowU.uLuma.value += (t.luma - glowU.uLuma.value) * k;
    SCREEN_LIGHT.color.copy(glowU.uGlowPos.value).add(glowU.uGlowNeg.value).multiplyScalar(0.5);
    SCREEN_LIGHT.luma = glowU.uLuma.value;
    // the live seats (lit, not baked) take the same light from the screen
    if (seatLight.current) {
      const c = SCREEN_LIGHT.color;
      seatLight.current.color.copy(c).multiplyScalar(1 / Math.max(c.r, c.g, c.b, 0.05));
      seatLight.current.intensity = 30 * (0.45 + 1.1 * SCREEN_LIGHT.luma);
    }
    // the room's soft fill is mostly light reflected off the screen: half house-warm, half the picture's hue
    if (fill.current) {
      fill.current.color.copy(WARM_FILL).lerp(seatLight.current?.color ?? WARM_FILL, 0.5);
      fill.current.intensity = 0.35 * (0.6 + 0.9 * SCREEN_LIGHT.luma) * (0.5 + 0.5 * glowU.uHouse.value);
    }
    // the house light over the seat backs is partly screen light off the ceiling and walls
    if (house.current && seatLight.current) {
      house.current.color.copy(HOUSE_WARM).lerp(seatLight.current.color, 0.35);
      house.current.intensity = 12 * glowU.uHouse.value;
    }
    let flickering = false;
    if (flickFrom.current >= 0) {
      const e = (performance.now() - flickFrom.current) / 1000;
      SCREEN_LIGHT.flick = flickerLevel(e);
      if (shown.current) shown.current.material.color.copy(shown.current.base).multiplyScalar(SCREEN_LIGHT.flick);
      flickering = e < FLICKER_S;
      if (!flickering) flickFrom.current = -1;
    }
    if (settling || dimming || flickering) invalidate();
  });
  // leaving mid-flicker must not leave the next hall's screen, beam and dust dimmed (SCREEN_LIGHT is shared)
  useEffect(() => () => void (SCREEN_LIGHT.flick = 1), []);
  // a new film: the projector stutters back on (not with reduced motion)
  useEffect(() => {
    if (!film || reducedMotion()) return;
    flickFrom.current = performance.now();
    invalidate();
  }, [film?.id, invalidate]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (!screen.current) return;
    const base = art ? new Color(1.2, 1.2, 1.2) : new Color(tone.screen);
    const material = new MeshBasicMaterial({ map: art, color: base.clone().multiplyScalar(SCREEN_LIGHT.flick), toneMapped: false });
    screen.current.material = material;
    shown.current = { material, base };
    invalidate();
  }, [art, room, tone, invalidate]);
  const look = meta.allseats.look;
  return (
    <group>
      {room && <primitive object={room} />}
      {room && <Haze meta={meta} />}
      {/* a hall without Cycles probes (an older file) lights its seats the old way */}
      {!meta.probe && <>
        <pointLight ref={seatLight} position={[0, meta.screen.zc, -1.5]} color={tone.screen} intensity={30} distance={40} decay={1.2} />
        <pointLight ref={house} position={[look[0], look[1] + 4, look[2]]} color="#e8a868" intensity={12} distance={30} decay={1.4} />
        <ambientLight ref={fill} intensity={0.35} color="#6b4a3a" />
      </>}
    </group>
  );
}

/** Floor tiers on the rake, the stage floor, dark walls, the glowing screen, brass step lights in every aisle. */
function Room({ hall, tone, film, paint, mark }: { hall: Hall; tone: Tones; film: Film | null | undefined; paint: Paint | null; mark: Mark }) {
  const ref = useRef<InstancedMesh>(null);
  const painted = usePainted(paint, 2.39);
  const still = useScreenArt(film, tone, mark);
  const art = painted ?? still;
  const w = hall.halfWidth + 1.8;
  const { screen, depth, top } = hall;
  const height = screen.y + screen.height / 2 + 2.5;
  const front = screen.z - 0.4;
  const back = depth + 11; // deep enough that the overview camera (hall.ts) stands inside the room
  const lights = useMemo(() => {
    const xs = [...hall.aisles, -(hall.halfWidth + 0.5), hall.halfWidth + 0.5];
    return hall.tiers.flatMap((t) => xs.map((x) => [x, t.y + 0.05, t.z - PITCH_Z / 2 + 0.06] as const));
  }, [hall]);
  useLayoutEffect(() => {
    const mesh = ref.current;
    if (!mesh) return;
    const o = new Object3D();
    lights.forEach(([x, y, z], i) => {
      o.position.set(x, y, z);
      o.updateMatrix();
      mesh.setMatrixAt(i, o.matrix);
    });
    mesh.instanceMatrix.needsUpdate = true;
  }, [lights]);
  return (
    <group>
      {hall.tiers.map((t) => (
        <mesh key={t.gr} position={[0, (t.y + 0.05) / 2, t.z]}>
          <boxGeometry args={[w * 2, t.y + 0.05, PITCH_Z]} />
          <meshStandardMaterial color={tone.floor} roughness={0.9} />
        </mesh>
      ))}
      <mesh position={[0, 0.02, (front + -PITCH_Z / 2) / 2]}>
        <boxGeometry args={[w * 2, 0.04, -PITCH_Z / 2 - front]} />
        <meshStandardMaterial color={tone.floor} roughness={0.9} />
      </mesh>
      <mesh position={[0, top + 0.02, back - (back - depth - PITCH_Z / 2) / 2]}>
        <boxGeometry args={[w * 2, 0.04, back - depth - PITCH_Z / 2]} />
        <meshStandardMaterial color={tone.floor} roughness={0.9} />
      </mesh>
      {[-1, 1].map((side) => (
        <mesh key={side} position={[side * (w + 0.15), height / 2, (front + back) / 2]}>
          <boxGeometry args={[0.3, height + top, back - front]} />
          <meshStandardMaterial color={tone.wall} roughness={0.95} />
        </mesh>
      ))}
      <mesh position={[0, height / 2, back + 0.15]}>
        <boxGeometry args={[w * 2 + 0.6, height + top, 0.3]} />
        <meshStandardMaterial color={tone.wall} roughness={0.95} />
      </mesh>
      <mesh position={[0, height / 2, front - 0.15]}>
        <boxGeometry args={[w * 2 + 0.6, height, 0.3]} />
        <meshStandardMaterial color={tone.wall} roughness={0.95} />
      </mesh>
      <mesh position={[0, screen.y, screen.z]} raycast={() => null}>
        <planeGeometry args={[screen.width, screen.height]} />
        {/* Keyed on the picture: a map arriving changes the shader, which a live material would not recompile. A
            little over 1, so the title's brightest strokes catch the bloom. */}
        <meshBasicMaterial key={art?.uuid ?? "bare"} map={art} color={art ? [1.2, 1.2, 1.2] : tone.screen.clone().multiplyScalar(1.1)}
                           toneMapped={false} />
      </mesh>
      <instancedMesh ref={ref} args={[undefined, undefined, lights.length]} raycast={() => null}>
        <boxGeometry args={[0.4, 0.05, 0.08]} />
        <meshBasicMaterial color={tone.house.clone().multiplyScalar(3)} toneMapped={false} />
      </instancedMesh>
      <pointLight position={[0, screen.y, screen.z + 2]} color={tone.screen} intensity={55} distance={depth + 30} decay={1.4} />
      <pointLight position={[0, top + 4, back - 1]} color={tone.house} intensity={18} distance={30} decay={1.6} />
      {/* House lights at half: brass from over the back wall, so the overview (behind the seats) sees lit seat backs
          and steps, not black shapes. Its target is the default, the front row's centre. */}
      <directionalLight position={[0, top + 6, back + 4]} color={tone.house} intensity={4} />
      {[-1, 1].map((side) => (
        <pointLight key={side} position={[side * (w - 0.4), top + 2.6, depth * 0.55]} color={tone.house} intensity={10} distance={16} decay={1.5} />
      ))}
      <ambientLight intensity={0.45} />
      <hemisphereLight args={[tone.glow, tone.wall, 0.35]} />
    </group>
  );
}

/** Every seat model's instances; a probe-lit hall (CR-010) also loads its reflection panorama here, once. */
function Seats({ byKind, colourOf, onPick, onHover, baked, glow, env, mark }: {
  byKind: Record<ModelKind, Placed[]>; colourOf: (seat: Seat) => Color; onPick: (seat: Seat, g: SeatGesture) => void; onHover: (seat: Seat | null) => void;
  baked: boolean; glow: GlowU | null; env: string | undefined; mark: Mark;
}) {
  const map = useHallEnv(glow ? env : undefined, mark);
  const lit = useMemo(() => (glow ? { glow, env: map } : null), [glow, map]);
  return <>{KINDS.map((k) => (byKind[k].length ? (
    <SeatKind key={k} kind={k} items={byKind[k]} colourOf={colourOf} onPick={onPick} onHover={onHover} baked={baked} lit={lit} mark={mark} />
  ) : null))}</>;
}

/** Readiness, step two: once every part is in (readiness.ts), the GPU is warmed while the canvas is still invisible -
 *  every texture uploaded and every shader compiled (gl.compileAsync), then two frames drawn, so the post-processing
 *  passes compile too - and only then `onShown`: the canvas fades in and the camera may move. The warm-up is capped
 *  (WARM_CAP_MS) in case compileAsync never answers. */
const WARM_CAP_MS = 1500;
function Warm({ on, onShown }: { on: boolean; onShown: () => void }) {
  const { gl, scene, camera, invalidate } = useThree();
  const stage = useRef<"wait" | "compiling" | "drawing" | "done">("wait");
  const frames = useRef(0);
  useEffect(() => {
    if (!on || stage.current !== "wait") return;
    stage.current = "compiling";
    const draw = () => {
      if (stage.current !== "compiling") return;
      stage.current = "drawing";
      invalidate();
    };
    scene.traverse((o) => {
      for (const m of [(o as Mesh).material].flat() as (Material & { map?: Texture | null; envMap?: Texture | null })[]) {
        for (const t of [m?.map, m?.envMap]) if (t?.isTexture) gl.initTexture(t);
      }
    });
    gl.compileAsync(scene, camera).then(draw, draw);
    const cap = setTimeout(draw, WARM_CAP_MS);
    return () => {
      clearTimeout(cap);
      if (stage.current === "compiling") stage.current = "wait"; // StrictMode's second run starts it again
    };
  }, [on, gl, scene, camera, invalidate]);
  useFrame(() => {
    if (stage.current !== "drawing") return;
    if (++frames.current < 2) return void invalidate();
    stage.current = "done";
    onShown();
  });
  return null;
}

export default function HallScene({ map, film, mine, mode, seatId, onTap, onLook, onHover, onMoving, meta = null, hallNo = null, paint = null, locked = false, houseDown = false, since }: {
  /** `film` undefined: not known yet (the page is still asking); the hall waits for it before it shows (readiness.ts) */
  map: SeatMap; film: Film | null | undefined; mine: ReadonlySet<number>; mode: Mode; seatId: number | null;
  onTap: (seat: Seat, visual: Visual) => void; onLook: (seat: Seat) => void; onHover: (seat: Seat | null) => void;
  onMoving: (moving: boolean) => void; meta?: BakedMeta | null; hallNo?: number | null; paint?: Paint | null;
  /** CR-005: the landing's seat - no seat to click, no hover, no dragging; the camera moves only when told to. */
  locked?: boolean;
  /** The house lights go down once the film's still is on the screen (the landing); up while choosing seats. */
  houseDown?: boolean;
  /** performance.now() when the page started loading this hall (its .json fetch); the cap counts from here. */
  since?: number;
}) {
  const [tone] = useState(tones);
  const [hover, setHover] = useState<number | null>(null);
  // The room's shape changes only when the seats themselves move, not on every poll.
  const shape = map.seats.map((s) => `${s.id}:${s.gr}:${s.gc}`).join();
  const hall = useMemo(() => computeHall(map.seats), [shape]);
  const baked = useMemo(() => (meta && hallNo ? bakedHall(map.seats, meta) : null), [shape, meta, hallNo]);
  const glowU = useMemo(() => (baked ? glowUniforms(baked.meta) : null), [baked?.meta]);
  const placed = baked?.placed ?? hall.placed;
  const byKind = useMemo(() => {
    const name = new Map(map.categories.map((c) => [c.id, c.name]));
    const out: Record<ModelKind, Placed[]> = { standard: [], premium: [], recliner: [] };
    for (const p of placed) out[modelKind(name.get(p.seat.cat) ?? "")].push(p);
    return out;
  }, [placed, map.categories]);
  // The live state of each seat, from this poll's payload.
  const live = useMemo(() => new Map(map.seats.map((s) => [s.id, s])), [map]);
  const closed = map.showtime.sales_closed;

  const colourOf = useMemo(() => {
    const lit = new Color(1, 1, 1);
    return (stale: Seat) => {
      const seat = live.get(stale.id) ?? stale;
      const v = visualOf(seat, mine);
      const base = !seat.is_active ? tone.sold.clone().multiplyScalar(0.5)
        : v === "held_by_me" ? tone.mine.clone().multiplyScalar(1.6) : v === "held_by_other" ? tone.other.clone() : v === "sold" ? tone.sold.clone() : baked ? LEATHER.clone() : tone.free.clone();
      return hover === seat.id && selectable(seat, v, closed) ? base.lerp(lit, 0.35) : base;
    };
  }, [live, mine, hover, tone, closed, baked]);

  // owner, 2026-11-23: click = go to the seat's view; double click = choose it (stay put); right click = take it back
  const pick = (stale: Seat, g: SeatGesture) => {
    const seat = live.get(stale.id) ?? stale;
    const v = visualOf(seat, mine);
    const act = seatAction(g, v, selectable(seat, v, closed));
    if (act === "look") onLook(seat);
    else if (act !== "none") onTap(seat, v); // the 2D map's own handler: adds a free seat, gives back one of yours
  };
  const hoverSeat = (s: Seat | null) => {
    const seat = s ? live.get(s.id) ?? s : null;
    setHover(seat?.id ?? null);
    onHover(seat);
    document.body.style.cursor = seat ? "pointer" : ""; // every seat can be looked from
  };
  useEffect(() => () => {
    document.body.style.cursor = "";
  }, []);

  // Owner, 2026-11-23: nothing of the hall shows and no camera moves until every part of it is in (readiness.ts).
  // The parts are fixed at mount: a later film change on the landing swaps the still in a shown hall (the flicker).
  const [t0] = useState(() => since ?? performance.now());
  const [parts, setParts] = useState<Parts>(() => {
    const p: Parts = { still: "loading" };
    if (baked) p.room = "loading";
    if (baked?.meta.probe?.env?.file) p.env = "loading";
    for (const k of KINDS) if (byKind[k].length) p[`seat:${k}`] = "loading";
    return p;
  });
  const mark = useCallback<Mark>((part, state) => setParts((p) => (p[part] === "loading" ? { ...p, [part]: state } : p)), []);
  const [, setCapped] = useState(false); // a render at the cap, so the status below is read again then
  useEffect(() => {
    const t = setTimeout(() => setCapped(true), Math.max(0, t0 + HALL_CAP_MS - performance.now())); // a timer, not rAF
    return () => clearTimeout(t);
  }, [t0]);
  const status = readiness(parts, performance.now() - t0, baked ? ["room"] : []);
  const [shown, setShown] = useState(false);
  const onShown = useCallback(() => {
    setShown(true);
    requestAnimationFrame(hallDrawn); // a waiting page change may show this page now (hallReady.ts)
  }, []);
  useEffect(() => {
    if (status === "failed") hallDrawn(); // nothing to wait for: the page shows its fallback
  }, [status]);
  // the Guard around this scene renders the page's fallback (the 2D map, the landing's empty stage)
  if (status === "failed" && !shown) throw new Error(`hall ${hallNo ?? "procedural"}: a required part did not load`);

  return (
    <Canvas frameloop="demand" dpr={[1, 1.25]} camera={{ fov: 50, near: 0.05, far: 200 }} flat={!!baked}
            className="fr-hall-canvas" data-shown={shown || undefined}
            gl={{ antialias: false, powerPreference: "high-performance" }} onPointerMissed={() => hoverSeat(null)}>
      <Warm on={settled(status)} onShown={onShown} />
      <color attach="background" args={[baked ? "#000000" : tone.field]} />
      {baked ? null : <fog attach="fog" args={[tone.field, 22, 70]} />}
      {baked ? <BakedRoom n={hallNo!} film={film} tone={tone} meta={baked.meta} paint={paint} houseDown={houseDown} glowU={glowU!} mark={mark} />
        : <Room hall={hall} tone={tone} film={film} paint={paint} mark={mark} />}
      <Seats byKind={byKind} colourOf={colourOf} onPick={locked ? () => undefined : pick} onHover={locked ? () => undefined : hoverSeat}
             baked={!!baked} glow={baked?.meta.probe ? glowU : null} env={baked?.meta.probe?.env?.file} mark={mark} />
      <Halos placed={placed} mine={mine} tone={tone} />
      <Rig hall={hall} mode={mode} seatId={seatId} onMoving={onMoving} bakedViews={baked?.views ?? null} intro={baked?.meta.intro ?? null}
           wall={baked ? Math.max(...baked.meta.seats.map((s) => Math.abs(s.pos[0]))) + 2 : null} locked={locked} go={shown} />
      <EffectComposer multisampling={0}>
        <Bloom mipmapBlur luminanceThreshold={1} intensity={baked ? 0.6 : 0.9} />
        <Vignette offset={0.3} darkness={0.55} />
        {/* a baked room is display-referred already: tone mapping it again would grey it */}
        {baked ? <></> : <ToneMapping />}
      </EffectComposer>
    </Canvas>
  );
}

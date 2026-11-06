// The 3D hall itself - the lazily loaded chunk (FR-ADR-074 5). It draws the seat-map payload it is handed and holds
// no booking state: a click calls the 2D map's own tap handler, after the 2D map's own selectable() check, so every
// hold, release and refusal goes through the one path the 2D map uses. It makes no request of its own except the
// static seat models and the screen's still, /art/screen_<movieId>.jpg.
import { Canvas, useFrame, useThree, type ThreeEvent } from "@react-three/fiber";
import { OrbitControls } from "@react-three/drei";
import { Bloom, EffectComposer, ToneMapping, Vignette } from "@react-three/postprocessing";
import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import {
  BufferAttribute, CanvasTexture, Color, InstancedMesh, MeshBasicMaterial, MeshPhysicalMaterial, MeshStandardMaterial, Object3D, RingGeometry,
  SRGBColorSpace, TextureLoader, Vector3, type BufferGeometry, type Group, type Mesh, type PerspectiveCamera, type Texture,
} from "three";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
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
  standard: [1.045, 1.007, 1.007], premium: [1.041, 1.021, 1.021], recliner: [1.946, 1.677, 1.676],
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
function Rig({ hall, mode, seatId, onMoving, bakedViews }: {
  hall: Hall; mode: Mode; seatId: number | null; onMoving: (moving: boolean) => void; bakedViews: BakedViews;
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
  const controls = useThree((s) => s.controls) as unknown as { target: Vector3 } | null;
  const invalidate = useThree((s) => s.invalidate);
  const look = useRef(new Vector3(...view.look));
  // t0 is stamped on the first frame drawn, so a slow first frame (shader compile) does not eat the move.
  const glide = useRef<{ at0: Vector3; look0: Vector3; t0: number | null; ms: number } | null>(null);
  const shown = useRef<View | null>(null);
  useEffect(() => {
    if (shown.current === view) { // the controls arriving re-runs this; the camera already has its orders
      if (!glide.current) controls?.target.copy(look.current);
      return;
    }
    const first = shown.current === null;
    shown.current = view;
    if (first || reducedMotion()) {
      const fly = first && !reducedMotion() && !bakedViews; // reduced motion cuts (CR-001 B.5); a baked hall arrives by its clip
      camera.position.set(...view.at);
      if (fly) camera.position.add(FLY_FROM);
      look.current.set(...view.look);
      camera.lookAt(look.current);
      controls?.target.copy(look.current);
      if (fly) {
        glide.current = { at0: camera.position.clone(), look0: look.current.clone(), t0: null, ms: FLY_MS };
        onMoving(true);
      }
      invalidate();
      return;
    }
    glide.current = { at0: camera.position.clone(), look0: (controls?.target ?? look.current).clone(), t0: null, ms: GLIDE_MS };
    onMoving(true);
    invalidate();
  }, [view, camera, controls, invalidate, onMoving]);
  useFrame(() => {
    const g = glide.current;
    if (!g) return;
    g.t0 ??= performance.now();
    const k = Math.min(1, (performance.now() - g.t0) / g.ms);
    const e = ease(k);
    camera.position.lerpVectors(g.at0, new Vector3(...view.at), e);
    look.current.lerpVectors(g.look0, new Vector3(...view.look), e);
    camera.lookAt(look.current);
    controls?.target.copy(look.current);
    if (k < 1) invalidate();
    else {
      glide.current = null;
      onMoving(false);
    }
  });
  // Looking around is the all-seats view's; a seat's view stays put at that seat's eyes.
  return <OrbitControls makeDefault enabled={mode === "all"} enablePan={false} enableDamping={false} maxPolarAngle={Math.PI * 0.49}
                        enableZoom={!bakedViews} minDistance={bakedViews ? 0 : 4} maxDistance={60} onStart={() => onMoving(true)} onEnd={() => onMoving(false)} />;
}

function SeatKind({ kind, items, colourOf, onPick, onHover, baked }: {
  kind: ModelKind; items: Placed[]; colourOf: (seat: Seat) => Color; onPick: (seat: Seat) => void; onHover: (seat: Seat | null) => void;
  baked: boolean;
}) {
  const ref = useRef<InstancedMesh>(null);
  const frameRef = useRef<InstancedMesh>(null);
  const invalidate = useThree((s) => s.invalidate);
  const [geo, setGeo] = useState<SeatGeo>(() => placeholderGeometry(kind));
  const geometry: BufferGeometry = geo.body;
  // Upholstery reads as velvet: matte with a soft sheen. The frame keeps its baked colour (satin black, brass).
  const material = useMemo(() => new MeshPhysicalMaterial({ roughness: 0.85, metalness: 0, sheen: 0.4, sheenRoughness: 0.4, sheenColor: new Color("#3a5596") }), []);
  const frameMaterial = useMemo(() => new MeshStandardMaterial({ vertexColors: true, roughness: 0.32, metalness: 0.45 }), []);
  useEffect(() => {
    let live = true;
    void seatGeometry(kind).then((g) => {
      if (live) setGeo(g);
      else { g.body.dispose(); g.frame?.dispose(); }
    });
    return () => {
      live = false;
    };
  }, [kind]);
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
  return (
    <>
    {geo.frame && <instancedMesh key={"f" + items.length} ref={frameRef} args={[geo.frame, frameMaterial, items.length]} raycast={() => null} />}
    <instancedMesh key={items.length} ref={ref} args={[geometry, material, items.length]}
      onClick={(e) => {
        e.stopPropagation();
        const s = seatAt(e);
        if (s && e.delta < 6) onPick(s); // a drag to look around is not a tap
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
function useScreenArt(film: Film | null, tone: Tones): Texture | null {
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
    const title = film?.title ?? "";
    void Promise.all([document.fonts.load(`800 120px "Inter Tight"`), document.fonts.load(`400 40px "JetBrains Mono"`)])
      .catch(() => null).then(() => show(titleCard(title, tone), false));
    if (film) {
      new TextureLoader().load(`/art/screen_${film.id}.jpg`, (t) => {
        t.colorSpace = SRGBColorSpace;
        show(t, true);
      }, undefined, () => null); // no still deployed: the title card stays
    }
    return () => {
      live = false;
      made.forEach((t) => t.dispose());
    };
  }, [film?.id, film?.title, tone, invalidate]);
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
function BakedRoom({ n, film, tone, meta, paint }: { n: number; film: Film | null; tone: Tones; meta: BakedMeta; paint: Paint | null }) {
  const invalidate = useThree((s) => s.invalidate);
  const painted = usePainted(paint, meta.screen.w / meta.screen.h);
  const still = useScreenArt(film, tone);
  const art = painted ?? still;
  const [room, setRoom] = useState<Group | null>(null);
  const screen = useRef<Mesh | null>(null);
  useEffect(() => {
    let live = true;
    new GLTFLoader().load(`/halls/hall${n}.glb`, (g) => {
      if (!live) return;
      g.scene.traverse((o) => {
        const m = o as Mesh;
        if (!m.isMesh) return;
        const was = m.material as MeshStandardMaterial;
        if (m.name.startsWith("bake_")) {
          m.material = new MeshBasicMaterial({ map: was.map, color: new Color(ROOM_GAIN, ROOM_GAIN, ROOM_GAIN), toneMapped: false });
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
          m.material = new MeshBasicMaterial({ color: was.emissive.clone().multiplyScalar(Math.min(was.emissiveIntensity * 0.6, 6)), toneMapped: false });
        }
      });
      setRoom(g.scene);
      invalidate();
    }, undefined, () => null); // no room file: the seats still draw
    return () => {
      live = false;
    };
  }, [n, invalidate]);
  useEffect(() => {
    if (!screen.current) return;
    screen.current.material = new MeshBasicMaterial({ map: art, color: art ? new Color(1.2, 1.2, 1.2) : tone.screen, toneMapped: false });
    invalidate();
  }, [art, room, tone, invalidate]);
  const look = meta.allseats.look;
  return (
    <group>
      {room && <primitive object={room} />}
      <pointLight position={[0, meta.screen.zc, -1.5]} color={tone.screen} intensity={30} distance={40} decay={1.2} />
      <pointLight position={[look[0], look[1] + 4, look[2]]} color="#e8a868" intensity={12} distance={30} decay={1.4} />
      <ambientLight intensity={0.35} color="#6b4a3a" />
    </group>
  );
}

/** Floor tiers on the rake, the stage floor, dark walls, the glowing screen, brass step lights in every aisle. */
function Room({ hall, tone, film, paint }: { hall: Hall; tone: Tones; film: Film | null; paint: Paint | null }) {
  const ref = useRef<InstancedMesh>(null);
  const painted = usePainted(paint, 2.39);
  const still = useScreenArt(film, tone);
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

export default function HallScene({ map, film, mine, mode, seatId, onTap, onLook, onHover, onMoving, meta = null, hallNo = null, paint = null }: {
  map: SeatMap; film: Film | null; mine: ReadonlySet<number>; mode: Mode; seatId: number | null;
  onTap: (seat: Seat, visual: Visual) => void; onLook: (seat: Seat) => void; onHover: (seat: Seat | null) => void;
  onMoving: (moving: boolean) => void; meta?: BakedMeta | null; hallNo?: number | null; paint?: Paint | null;
}) {
  const [tone] = useState(tones);
  const [hover, setHover] = useState<number | null>(null);
  // The room's shape changes only when the seats themselves move, not on every poll.
  const shape = map.seats.map((s) => `${s.id}:${s.gr}:${s.gc}`).join();
  const hall = useMemo(() => computeHall(map.seats), [shape]);
  const baked = useMemo(() => (meta && hallNo ? bakedHall(map.seats, meta) : null), [shape, meta, hallNo]);
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

  const pick = (stale: Seat) => {
    const seat = live.get(stale.id) ?? stale;
    const v = visualOf(seat, mine);
    if (selectable(seat, v, closed)) onTap(seat, v); // the 2D map's own guard, then its own handler
    onLook(seat); // any seat, choosable or not, can be previewed from
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

  return (
    <Canvas frameloop="demand" dpr={[1, 1.75]} camera={{ fov: 50, near: 0.05, far: 200 }} flat={!!baked}
            gl={{ antialias: false, powerPreference: "high-performance" }} onPointerMissed={() => hoverSeat(null)}>
      <color attach="background" args={[baked ? "#000000" : tone.field]} />
      {baked ? null : <fog attach="fog" args={[tone.field, 22, 70]} />}
      {baked ? <BakedRoom n={hallNo!} film={film} tone={tone} meta={baked.meta} paint={paint} /> : <Room hall={hall} tone={tone} film={film} paint={paint} />}
      {KINDS.map((k) => (byKind[k].length ? (
        <SeatKind key={k} kind={k} items={byKind[k]} colourOf={colourOf} onPick={pick} onHover={hoverSeat} baked={!!baked} />
      ) : null))}
      <Halos placed={placed} mine={mine} tone={tone} />
      <Rig hall={hall} mode={mode} seatId={seatId} onMoving={onMoving} bakedViews={baked?.views ?? null} />
      <EffectComposer multisampling={4}>
        <Bloom mipmapBlur luminanceThreshold={1} intensity={baked ? 0.6 : 0.9} />
        <Vignette offset={0.3} darkness={0.55} />
        {/* a baked room is display-referred already: tone mapping it again would grey it */}
        {baked ? <></> : <ToneMapping />}
      </EffectComposer>
    </Canvas>
  );
}

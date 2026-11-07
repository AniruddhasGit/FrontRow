// CR-005: the stage curtain as real cloth. A Verlet cloth (particles + distance constraints, gravity, damping), hung
// from a rail by its top row. The rail is narrower than the cloth (fullness 1.4) and its pins zig-zag front and back,
// so the cloth falls into deep vertical pleats on its own. Velvet: MeshPhysicalMaterial with sheen (three's velvet
// model) and a woven-fabric normal map (ambientCG Fabric084, CC0), lit by a raking key so every fold reads.
//   down  - the rail falls from above the box like a dropped fly; when it stops, the hem swings on and settles
//   drawn - the pins run along the rail to the box's right edge; the cloth bunches into folds as it goes
// Loaded lazily (Curtain.tsx); three.js is already in the page wherever a hall is.
import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { useEffect, useMemo, useRef } from "react";
import {
  BufferAttribute, BufferGeometry, CatmullRomCurve3, Color, DoubleSide, MeshPhysicalMaterial, MeshStandardMaterial, PlaneGeometry,
  RepeatWrapping, TextureLoader, TubeGeometry, Vector2, Vector3, type OrthographicCamera,
} from "three";
import type { CurtainPhase } from "./Curtain";

const NX = 121, NY = 44; // particles across, down
const PLEAT = 5; // particles per pleat: a smooth fold needs several, or the shading averages away
const DEPTH = 0.55; // pleat depth, as a share of the pleat's width
const H = 4; // world units for the box's height
const G = 10; // gravity, world units / s^2 (the box is 4 units tall)
// heavy, sturdy velvet (owner: "minimal wavyness"): strong damping and a stiff solve, so it swings once and stops
const DAMP = 0.965, ITER = 12, STEP = 1 / 120;
const CARRY = 0.9; // share of the rail's own drop the whole sheet is carried by: the rest is left to the physics
const FOLLOW = 0.02; // per step, each particle eases toward the spot under its pin: the weighted hem of a real drape
const DRAW_MS = 900;
const BRAKE = 0.7 * G; // the fly falls freely, then brakes gently to its trim (harder, and the hem piles up)
const SETTLE_MS = 450; // after the rail stops: the hem's swing, before the move counts as done

const easeInOut = (k: number) => (k < 0.5 ? 4 * k * k * k : 1 - (-2 * k + 2) ** 3 / 2);
const token = (name: string) => new Color(getComputedStyle(document.documentElement).getPropertyValue(name).trim() || "#800000");

function Cloth({ phase, onDone }: { phase: CurtainPhase; onDone: () => void }) {
  const size = useThree((s) => s.size);
  const invalidate = useThree((s) => s.invalidate);
  const gl = useThree((s) => s.gl);
  const W = (H * size.width) / Math.max(1, size.height);
  const top = H / 2 + 0.06, left = -W / 2;
  const sim = useMemo(() => {
    const n = NX * NY;
    const pos = new Float32Array(n * 3), prev = new Float32Array(n * 3);
    const sx = W / (NX - 1); // rail spacing between pins
    const dy = (H * 1.03) / (NY - 1); // cloth rest length down
    const amp = (DEPTH * PLEAT * sx) / 2; // each pleat a smooth wave across PLEAT particles
    // each pleat a little different, as real ones are (a fixed scatter: S-PAY-12 keeps randomness out of frontend/src)
    const vary = (i: number) => 0.8 + 0.4 * (((Math.sin(i * 78.233) * 43758.5453) % 1 + 1) % 1);
    const zig = (i: number) => amp * Math.sin((2 * Math.PI * i) / PLEAT) * vary(Math.floor(i / PLEAT));
    const pinX = Array.from({ length: NX }, (_, i) => left + i * sx);
    const lift = H + 0.4; // the cloth starts flown out, wholly above the box
    for (let j = 0; j < NY; j++) for (let i = 0; i < NX; i++) {
      const k = 3 * (j * NX + i);
      pos[k] = pinX[i]; pos[k + 1] = top + lift - j * dy; pos[k + 2] = zig(i); // the pleats run the full drop
    }
    prev.set(pos);
    // constraints: [a, b, rest, bend] - structural across and down, and skip-one across and down for body (bend)
    const cons: number[] = [];
    const add = (a: number, b: number, r: number, bend = 0) => cons.push(a, b, r, bend);
    for (let j = 0; j < NY; j++) for (let i = 0; i < NX; i++) {
      const p = j * NX + i;
      const gap = (q: number) => Math.hypot(pos[3 * q] - pos[3 * p], pos[3 * q + 2] - pos[3 * p + 2]);
      if (i + 1 < NX) add(p, p + 1, gap(p + 1));
      if (j + 1 < NY) add(p, p + NX, dy);
      // across two pleat faces: no longer than the rail spacing, so a pleat can bunch (drawn) but never flatten out
      if (i + 2 < NX) add(p, p + 2, gap(p + 2), 1);
      if (j + 2 < NY) add(p, p + 2 * NX, dy * 2); // heavy velvet hangs straight: down the drop it neither stretches nor buckles
    }
    // the fly's fall: free fall at G, then braking at BRAKE, landing at the trim (rail 0) with no speed left
    const vPeak = Math.sqrt((2 * lift) / (1 / G + 1 / BRAKE)), tFall = vPeak / G, tBrake = vPeak / BRAKE;
    const railAt = (t: number) => (t < tFall ? lift - 0.5 * G * t * t
      : t < tFall + tBrake ? lift - 0.5 * G * tFall * tFall - vPeak * (t - tFall) + 0.5 * BRAKE * (t - tFall) ** 2 : 0);
    return { pos, prev, cons: new Float32Array(cons), pinX, zig, lift, railAt, dropMs: 1000 * (tFall + tBrake), acc: 0, t: 0 };
  }, [W, top, left]);

  const geo = useMemo(() => {
    const g = new BufferGeometry();
    g.setAttribute("position", new BufferAttribute(sim.pos, 3));
    const uv = new Float32Array(NX * NY * 2), idx: number[] = [];
    for (let j = 0; j < NY; j++) for (let i = 0; i < NX; i++) {
      uv[2 * (j * NX + i)] = (i / (NX - 1)) * 9;
      uv[2 * (j * NX + i) + 1] = (1 - j / (NY - 1)) * 6;
      if (i + 1 < NX && j + 1 < NY) {
        const a = j * NX + i;
        idx.push(a, a + NX, a + 1, a + 1, a + NX, a + NX + 1);
      }
    }
    g.setAttribute("uv", new BufferAttribute(uv, 2));
    g.setIndex(idx);
    g.computeVertexNormals();
    return g;
  }, [sim]);

  const mat = useMemo(() => {
    const normal = new TextureLoader().load("/art/velvet_normal.jpg", () => invalidate());
    normal.wrapS = normal.wrapT = RepeatWrapping;
    return new MeshPhysicalMaterial({
      color: token("--fr-velvet"), roughness: 0.82, sheen: 1, sheenColor: token("--fr-velvet-lit"), sheenRoughness: 0.32,
      normalMap: normal, normalScale: new Vector2(0.55, 0.55), side: DoubleSide,
    });
  }, [invalidate]);

  // The valance: a short, stiff, pleated pelmet with scalloped swags along its hem and a gold cord on it. Not cloth -
  // a real one is boxed and barely moves - so it rides the rail as one piece.
  const valance = useMemo(() => {
    const depth = 0.55, g = new PlaneGeometry(W * 1.02, depth, 240, 12), p = g.attributes.position as BufferAttribute;
    const swag = W / Math.max(4, Math.round(W / 1.1));
    for (let v = 0; v < p.count; v++) {
      const x = p.getX(v), y = p.getY(v), t = (depth / 2 - y) / depth; // 0 at the top, 1 at the hem
      const sc = Math.abs(Math.sin((Math.PI * (x - left)) / swag)); // 0 at each swag's join, 1 mid-swag
      p.setY(v, depth / 2 - t * (depth * 0.55 + depth * 0.45 * sc));
      p.setZ(v, 0.06 * Math.sin((x - left) * 22) + 0.05 * t * sc);
    }
    g.computeVertexNormals();
    const pts = Array.from({ length: 241 }, (_, s) => {
      const x = left + (s / 240) * W, sc = Math.abs(Math.sin((Math.PI * (x - left)) / swag));
      return new Vector3(x, depth / 2 - (depth * 0.55 + depth * 0.45 * sc), 0.08);
    });
    const cord = new TubeGeometry(new CatmullRomCurve3(pts), 480, 0.018, 6, false);
    return { g, cord, depth };
  }, [W, left]);
  const gold = useMemo(() => new MeshStandardMaterial({ color: token("--fr-velvet-gold"), metalness: 1, roughness: 0.35 }), []);

  const told = useRef(false);
  const shown = useRef(phase);
  const rail = useRef(sim.lift);
  const valY = useRef<{ y: number } | null>(null);
  useEffect(() => {
    sim.t = 0;
    told.current = false;
    shown.current = phase;
    invalidate();
  }, [phase, invalidate, sim]);

  useFrame((_, delta) => {
    // Parked (up): nothing moves and nothing is redrawn. It was drawn once, so the velvet's shaders are compiled
    // before the first drop - the drop starts on the click, without a first-frame stall.
    if (shown.current === "up") return;
    // Everything runs on the simulation's own clock: a slow device plays the same motion, slower, never torn.
    const el = sim.t * 1000;
    // the move is done when the cloth has done it - timed from its own first frame, so a slow load never cuts it short
    if (!told.current && el > (shown.current === "down" ? sim.dropMs + SETTLE_MS : DRAW_MS + 150)) {
      told.current = true;
      onDone();
    }
    const { pos, prev, cons, pinX, zig } = sim;
    sim.acc += Math.min(delta, 1 / 20);
    let drawK = 0;
    while (sim.acc >= STEP) {
      sim.acc -= STEP;
      sim.t += STEP;
      drawK = shown.current === "drawn" ? easeInOut(Math.min(1, (sim.t * 1000) / DRAW_MS)) : 0;
      const was = rail.current;
      rail.current = shown.current === "down" ? sim.railAt(sim.t) : 0;
      // The sheet rides down with its rail (moved, not pushed: no speed is added), so when the rail brakes nothing piles
      // up under the valance; the small remainder lags and settles, which is all the swing a heavy drape has.
      const carry = (rail.current - was) * CARRY;
      if (carry) for (let p = NX; p < NX * NY; p++) {
        pos[3 * p + 1] += carry;
        prev[3 * p + 1] += carry;
      }
      for (let p = NX; p < NX * NY; p++) { // Verlet: gravity, damped
        const k = 3 * p;
        for (let c = 0; c < 3; c++) {
          const v = (pos[k + c] - prev[k + c]) * DAMP;
          prev[k + c] = pos[k + c];
          pos[k + c] += v + (c === 1 ? -G * STEP * STEP : 0);
        }
      }
      // Weighted drape: every column eases sideways toward the x of its own pin, so the cloth follows the rail as one
      // sturdy sheet instead of billowing out behind it (the owner: "minimal wavyness").
      for (let p = NX; p < NX * NY; p++) pos[3 * p] += (pos[3 * (p % NX)] - pos[3 * p]) * FOLLOW;
      for (let i = 0; i < NX; i++) { // the pins: along the rail, gathered toward the right edge when drawn
        const k = 3 * i;
        // opened from left to right: the pins run to the box's RIGHT edge (owner, 2026-11-07)
        pos[k] = prev[k] = -left - (-left - pinX[i]) * (1 - 0.965 * drawK);
        pos[k + 1] = prev[k + 1] = top + rail.current;
        pos[k + 2] = prev[k + 2] = zig(i) * (1 + 1.2 * drawK); // bunching deepens the folds a little, not enough to cross
      }
      for (let it = 0; it < ITER; it++) {
        for (let c = 0; c < cons.length; c += 4) {
          const a = 3 * cons[c], b = 3 * cons[c + 1], r = cons[c + 2];
          const ex = pos[b] - pos[a], ey = pos[b + 1] - pos[a + 1], ez = pos[b + 2] - pos[a + 2];
          const d = Math.hypot(ex, ey, ez) || 1e-6;
          // the bend links let the pleats bunch only while the curtain is being drawn; hanging, they hold their shape both
          // ways, so no two folds ever cross (crossed folds render as dark slits)
          if (cons[c + 3] && d < r && shown.current === "drawn") continue;
          const f = ((d - r) / d) * 0.5;
          const pa = cons[c] >= NX, pb = cons[c + 1] >= NX; // free (not pinned): the top row never moves here
          const wa = pa && pb ? f : pa ? 2 * f : 0, wb = pa && pb ? f : pb ? 2 * f : 0;
          pos[a] += ex * wa; pos[a + 1] += ey * wa; pos[a + 2] += ez * wa;
          pos[b] -= ex * wb; pos[b + 1] -= ey * wb; pos[b + 2] -= ez * wb;
        }
      }
    }
    gl.domElement.closest(".fr-curtain")?.parentElement?.style.setProperty("--fr-curtain-open", String(shown.current === "drawn" ? 0.965 * easeInOut(Math.min(1, (sim.t * 1000) / DRAW_MS)) : 0));
    geo.attributes.position.needsUpdate = true;
    geo.computeVertexNormals();
    if (valY.current) valY.current.y = top + rail.current + (shown.current === "drawn" ? H * 0.4 * easeInOut(Math.max(0, Math.min(1, (el - 300) / 700))) : 0);
    invalidate();
  });

  return (
    <>
      <mesh geometry={geo} material={mat} />
      <group ref={(g) => { valY.current = g ? g.position : null; }} position={[0, top + sim.lift, 0.15]}>
        <mesh geometry={valance.g} material={mat} position={[0, -valance.depth / 2, 0]} />
        <mesh geometry={valance.cord} material={gold} position={[0, -valance.depth / 2, 0]} />
      </group>
    </>
  );
}

function Lens() {
  const camera = useThree((s) => s.camera as OrthographicCamera);
  const size = useThree((s) => s.size);
  useEffect(() => {
    const w = (H * size.width) / Math.max(1, size.height);
    Object.assign(camera, { left: -w / 2, right: w / 2, top: H / 2, bottom: -H / 2, near: 0.1, far: 50 });
    camera.position.set(0, 0, 10);
    camera.updateProjectionMatrix();
  }, [camera, size]);
  return null;
}

export default function CurtainScene({ phase, onDone }: { phase: CurtainPhase; onDone: () => void }) {
  return (
    <Canvas orthographic frameloop="demand" dpr={[1, 1.75]} gl={{ alpha: true, antialias: true }} style={{ position: "absolute", inset: 0 }}>
      <Lens />
      {/* a warm raking key from high left so every pleat reads, a cool fill, and footlights from below the stage */}
      <directionalLight position={[-7, 4, 2.5]} intensity={2.8} color="#ffd9b0" />
      <directionalLight position={[5, 1, 3]} intensity={0.5} color="#9fb8ff" />
      <pointLight position={[0, -2.6, 2.2]} intensity={6} distance={9} decay={1.6} color="#ffb070" />
      <ambientLight intensity={0.18} />
      <Cloth phase={phase} onDone={onDone} />
    </Canvas>
  );
}

// One seat geometry per category model (CR-001 B.2): the static .glb under /models/ when it is there, else a
// procedural stand-in drawn here, so a missing or broken file never blanks the hall.
// Every geometry is normalised the same way: one grid column wide, standing on y = 0, centred on x and z, facing -z
// (the screen). glTF faces +z, so the model is turned round.
// A .glb's meshes are split by material name: "fr_upholstery*" becomes the body, which carries the seat-state colour
// through instanceColor; everything else (fr_frame, fr_trim) becomes the frame, drawn with its own baked vertex colour
// (satin black, brass) and never tinted. Textures are dropped.
import { BufferGeometry, Color, Float32BufferAttribute, Mesh, MeshStandardMaterial } from "three";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import { RoundedBoxGeometry } from "three/addons/geometries/RoundedBoxGeometry.js";
import { mergeGeometries } from "three/addons/utils/BufferGeometryUtils.js";
import { MODEL_URL, PITCH_X, type ModelKind } from "./hall";

type Part = [w: number, h: number, d: number, x: number, y: number, z: number, tilt?: number];

// Front is +z here (glTF's convention); normalise() turns it round. Metres.
const PARTS: Record<ModelKind, Part[]> = {
  // A classic fold-up seat: pedestal, cushion, back, two arms.
  standard: [
    [0.34, 0.36, 0.3, 0, 0.18, -0.02], [0.5, 0.11, 0.46, 0, 0.42, 0.04], [0.5, 0.56, 0.08, 0, 0.74, -0.2, -0.12],
    [0.06, 0.24, 0.5, -0.28, 0.56, 0], [0.06, 0.24, 0.5, 0.28, 0.56, 0],
  ],
  // Wider, deeper padding, a taller back with a headrest.
  premium: [
    [0.4, 0.34, 0.34, 0, 0.17, -0.02], [0.54, 0.17, 0.52, 0, 0.42, 0.04], [0.54, 0.74, 0.13, 0, 0.86, -0.24, -0.14],
    [0.34, 0.15, 0.13, 0, 1.3, -0.3, -0.14], [0.09, 0.3, 0.56, -0.31, 0.58, 0], [0.09, 0.3, 0.56, 0.31, 0.58, 0],
  ],
  // A full recliner: a deep seat, a reclined back, a footrest, broad arms.
  recliner: [
    [0.54, 0.3, 0.6, 0, 0.15, 0], [0.56, 0.2, 0.62, 0, 0.38, 0.02], [0.56, 0.76, 0.2, 0, 0.82, -0.34, -0.3],
    [0.5, 0.1, 0.36, 0, 0.26, 0.5, 0.35], [0.12, 0.36, 0.8, -0.34, 0.5, 0], [0.12, 0.36, 0.8, 0.34, 0.5, 0],
  ],
};

function placeholder(kind: ModelKind): BufferGeometry {
  const parts = PARTS[kind].map(([w, h, d, x, y, z, tilt]) => {
    const g = new RoundedBoxGeometry(w, h, d, 2, Math.min(w, h, d) * 0.35);
    if (tilt) g.rotateX(tilt);
    return g.translate(x, y, z);
  });
  const merged = mergeGeometries(parts)!;
  parts.forEach((g) => g.dispose());
  return merged;
}

/** body takes the seat-state colour; frame (may be null) keeps its baked vertex colours. */
export interface SeatGeo { body: BufferGeometry; frame: BufferGeometry | null }

/** Turn round, stand on y = 0, centre and scale body and frame by ONE transform so they stay registered. */
function normalise(geo: SeatGeo): SeatGeo {
  const all = [geo.body, geo.frame].filter((g): g is BufferGeometry => !!g);
  all.forEach((g) => g.rotateY(Math.PI));
  all.forEach((g) => g.computeBoundingBox());
  const box = all[0].boundingBox!.clone();
  all.slice(1).forEach((g) => box.union(g.boundingBox!));
  const scale = (PITCH_X * 0.92) / Math.max(1e-6, box.max.x - box.min.x);
  for (const g of all) {
    g.translate(-(box.min.x + box.max.x) / 2, -box.min.y, -(box.min.z + box.max.z) / 2).scale(scale, scale, scale);
    g.computeBoundingSphere();
  }
  return geo;
}

async function fromFile(kind: ModelKind): Promise<SeatGeo> {
  const gltf = await new GLTFLoader().loadAsync(MODEL_URL[kind]);
  gltf.scene.updateMatrixWorld(true);
  const body: BufferGeometry[] = [];
  const frame: BufferGeometry[] = [];
  gltf.scene.traverse((o) => {
    const m = o as Mesh;
    if (!m.isMesh) return;
    const mat = [m.material].flat()[0] as MeshStandardMaterial | undefined;
    const src = m.geometry;
    const g = new BufferGeometry();
    g.setAttribute("position", src.getAttribute("position"));
    if (src.getAttribute("normal")) g.setAttribute("normal", src.getAttribute("normal"));
    if (src.index) g.setIndex(src.index);
    const flat = (g.index ? g.toNonIndexed() : g).applyMatrix4(o.matrixWorld);
    if (!flat.getAttribute("normal")) flat.computeVertexNormals();
    if ((mat?.name ?? "").startsWith("fr_upholstery")) {
      body.push(flat);
    } else {
      const c = mat?.color ?? new Color(0x101012);
      const n = flat.getAttribute("position").count;
      const rgb = new Float32Array(n * 3);
      for (let i = 0; i < n; i++) rgb.set([c.r, c.g, c.b], i * 3);
      flat.setAttribute("color", new Float32BufferAttribute(rgb, 3));
      frame.push(flat);
    }
  });
  gltf.scene.traverse((o) => {
    const m = o as Mesh;
    if (!m.isMesh) return;
    m.geometry.dispose();
    for (const mat of [m.material].flat()) mat.dispose();
  });
  const merge = (parts: BufferGeometry[]) => {
    const merged = parts.length ? mergeGeometries(parts) : null;
    parts.forEach((g) => g.dispose());
    return merged;
  };
  const b = merge(body);
  if (!b) throw new Error(`${MODEL_URL[kind]} holds no fr_upholstery mesh`);
  return { body: b, frame: merge(frame) };
}

/** The geometry for one model: the file's, else the stand-in. Never rejects. */
export async function seatGeometry(kind: ModelKind): Promise<SeatGeo> {
  try {
    return normalise(await fromFile(kind));
  } catch {
    // No file (a 404, or the SPA fallback's index.html), or a file three cannot read: draw the stand-in.
    return normalise({ body: placeholder(kind), frame: null });
  }
}

/** Synchronous stand-in, so the hall draws at once while the files load. */
export function placeholderGeometry(kind: ModelKind): SeatGeo {
  return normalise({ body: placeholder(kind), frame: null });
}

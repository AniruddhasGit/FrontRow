// Start a hall's heavy work before its page opens (owner, 2026-11-23: "start the loading as soon as I come on the page
// where I can see the screens and timings ... as early as possible to lower the delay"). The baked room is fetched AND
// parsed here, once, and the hall reuses that parse (HallScene BakedRoom clones the scene, so each use gets its own
// materials and the cached original stays untouched). Kept for the two halls used last; a failed load is forgotten,
// so the hall itself tries again.
import { GLTFLoader, type GLTF } from "three/addons/loaders/GLTFLoader.js";

const rooms = new Map<number, Promise<GLTF>>();
const KEEP = 2;

/** Drop a hall's parse (one that came back incomplete), so the next loadRoom fetches it again. */
export function forgetRoom(n: number): void {
  rooms.delete(n);
}

export function loadRoom(n: number): Promise<GLTF> {
  let p = rooms.get(n);
  if (p) {
    rooms.delete(n); // most recently used goes last
    rooms.set(n, p);
    return p;
  }
  p = new GLTFLoader().loadAsync(`/halls/hall${n}.glb`);
  rooms.set(n, p);
  p.catch(() => rooms.delete(n));
  while (rooms.size > KEEP) rooms.delete(rooms.keys().next().value!);
  return p;
}
